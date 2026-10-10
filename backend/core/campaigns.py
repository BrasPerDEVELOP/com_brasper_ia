"""Campañas de Brasper IA con persistencia propia (plan de campañas y usuarios, 10 oct).

Toda la administración vive en la plataforma IA: campañas, versiones, reglas, cupos y el
registro de beneficios (reservado → consumido | liberado). La API financiera de Brasper solo
se CONSULTA (tasas/rutas, comisiones, cliente e historial cuando existe el contrato).

Límites honestos (ver docs/plans/PLAN-CAMPANAS-Y-USUARIOS-2026-10-10.md, «Estado»):
- El bot no registra operaciones en Brasper. El ahorro que muestra es informativo: la
  operación se registra en el backoffice/portal y un cálculo de IA no cambia por sí mismo
  el cobro financiero. Por eso la reserva/consumo los marca el asesor (o la sincronización
  de estado cuando la API la expone).
- El primer envío se controla entre los canales atendidos por IA, por cliente Brasper,
  contacto y documento. Un beneficio usado fuera de IA solo se detecta si Brasper lo refleja
  en el historial; sin ese dato no se confirma elegibilidad.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import brasper_api, db, media_library, observability, tenants, util

ROUTE_RE = re.compile(r"^(ALL|[A-Z]{3}_[A-Z]{3})$")


class CampaignCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    media_id: str | None = Field(default=None, max_length=60)


class CampaignRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment: Literal["all", "first_transfer", "returning"]
    timezone: str = "America/Lima"
    minimum_amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    maximum_amount: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    maximum_discount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    priority: int = Field(default=0, ge=0, le=100)
    combination: Literal["exclusive"] = "exclusive"
    messages: dict[Literal["es", "pt"], CampaignCopy]

    @model_validator(mode="after")
    def check(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Zona horaria no válida") from exc
        if self.maximum_amount is not None and self.maximum_amount < self.minimum_amount:
            raise ValueError("El máximo debe ser mayor o igual al mínimo")
        if set(self.messages) != {"es", "pt"}:
            raise ValueError("La campaña requiere mensaje en español y portugués")
        return self


class CampaignDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    discount_percentage: float = Field(ge=1, le=100, allow_inf_nan=False)
    max_uses: int | None = Field(default=None, gt=0)  # cupo total; None = sin límite global
    per_user_limit: int = Field(default=1, gt=0)  # beneficios por persona
    routes: list[str] = Field(default_factory=list, max_length=20)
    origin_currency: str | None = None
    destination_currency: str | None = None
    start_date: datetime
    end_date: datetime
    campaign_rules: CampaignRules

    @model_validator(mode="after")
    def check(self):
        if self.start_date.tzinfo is None or self.end_date.tzinfo is None or self.end_date <= self.start_date:
            raise ValueError("Inicio y fin deben incluir zona horaria, con fin posterior al inicio")
        if not self.routes and self.origin_currency and self.destination_currency:
            self.routes = [f"{self.origin_currency}_{self.destination_currency}".upper()]
        routes = sorted({r.upper() for r in self.routes})
        if not routes:
            raise ValueError("Elige al menos una ruta o todas las rutas")
        if any(not ROUTE_RE.fullmatch(r) or (r != "ALL" and r[:3] == r[4:]) for r in routes):
            raise ValueError("Ruta no válida; usa ALL o pares distintos como PEN_BRL")
        self.routes = ["ALL"] if "ALL" in routes else routes
        self.origin_currency = self.destination_currency = None
        if self.campaign_rules.segment == "first_transfer" and self.per_user_limit != 1:
            raise ValueError("Primer envío admite un único beneficio por persona")
        if Decimal(str(self.discount_percentage)) != Decimal(str(self.discount_percentage)).quantize(Decimal("0.01")):
            raise ValueError("El porcentaje admite como máximo dos decimales")
        rules = self.campaign_rules
        if ("ALL" in self.routes or len(self.origin_currencies()) != 1) and (rules.minimum_amount or rules.maximum_amount is not None
                                                     or rules.maximum_discount is not None):
            # Una misma cifra no significa lo mismo en PEN, BRL o USD.
            raise ValueError("Con varias monedas de origen deja vacíos mínimo, máximo y tope, o elige una sola moneda de origen")
        return self

    def origin_currencies(self) -> set[str]:
        return {"*"} if "ALL" in self.routes else {r[:3] for r in self.routes}


class Conflict(ValueError):
    pass


class BenefitRejected(ValueError):
    pass


# ---------------------------------------------------------------- esquema
def ensure_schema() -> None:
    with db.connect() as con:
        for sql in DDL:
            con.execute(sql)


DDL = [
    "CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, "
    "latest_version INTEGER NOT NULL, published_version INTEGER, active INTEGER NOT NULL DEFAULT 0, "
    "used_count INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS campaign_versions (campaign_id TEXT NOT NULL, version INTEGER NOT NULL, "
    "payload TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(campaign_id, version))",
    "CREATE TABLE IF NOT EXISTS campaign_benefits (id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, "
    "campaign_version INTEGER NOT NULL, person_key TEXT NOT NULL, conversation_id TEXT, operation_ref TEXT, "
    "state TEXT NOT NULL, eligibility_source TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, closed_by TEXT)",
    "CREATE INDEX IF NOT EXISTS campaign_benefits_campaign ON campaign_benefits(campaign_id, state)",
    "CREATE TABLE IF NOT EXISTS campaign_person_uses (campaign_id TEXT NOT NULL, person_key TEXT NOT NULL, "
    "used INTEGER NOT NULL, PRIMARY KEY(campaign_id, person_key))",
    "CREATE TABLE IF NOT EXISTS first_transfer_claims (identity_key TEXT PRIMARY KEY, benefit_id TEXT NOT NULL, "
    "created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS campaign_benefit_events (benefit_id TEXT NOT NULL, from_state TEXT, "
    "to_state TEXT NOT NULL, actor TEXT, note TEXT, at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS campaign_benefit_events_benefit ON campaign_benefit_events(benefit_id)",
]


def _tx(con) -> None:
    """Serializa la sección crítica: BEGIN IMMEDIATE en SQLite; en PostgreSQL las
    actualizaciones condicionales y claves únicas dan la exclusión."""
    if not db.is_postgres() and not con.in_transaction:
        con.execute("BEGIN IMMEDIATE")


# ---------------------------------------------------------------- rutas
def available_routes() -> list[str]:
    """Rutas con tipo de cambio publicado por Brasper; no se asume ninguna combinación."""
    rows = brasper_api.live_rates(tenants.get_config() or {})
    return sorted({f"{r['origin']}_{r['destination']}" for r in rows if r["origin"] != r["destination"]})


# ---------------------------------------------------------------- administración
def _row(con, campaign_id: str, lock: bool = False):
    if lock:
        _tx(con)
    row = con.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if not row:
        raise KeyError("Campaña no encontrada")
    return dict(row)


def save(draft: CampaignDraft, actor: str, campaign_id: str | None = None, expected_version: int = 0) -> dict:
    now = util.now_iso()
    with db.connect() as con:
        if campaign_id:
            row = _row(con, campaign_id, lock=True)
            if row["latest_version"] != expected_version:
                raise Conflict("La campaña cambió; recarga antes de guardar")
            if draft.code and draft.code != row["code"]:
                raise ValueError("El identificador de una campaña existente no puede cambiar")
            draft.code = row["code"]
            version = row["latest_version"] + 1
            if not con.execute("UPDATE campaigns SET latest_version=?, updated_at=? WHERE id=? AND latest_version=?",
                               (version, now, campaign_id, expected_version)).rowcount:
                raise Conflict("La campaña cambió; recarga antes de guardar")
        else:
            if expected_version != 0:
                raise Conflict("Una campaña nueva comienza en versión cero")
            campaign_id, version = uuid.uuid4().hex, 1
            draft.code = draft.code or "CAMP-" + uuid.uuid4().hex[:10].upper()
            if con.execute("SELECT 1 FROM campaigns WHERE code=?", (draft.code,)).fetchone():
                raise Conflict("Ya existe una campaña con ese identificador")
            con.execute("INSERT INTO campaigns (id, code, latest_version, published_version, active, used_count, "
                        "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (campaign_id, draft.code, 1, None, 0, 0, actor, now, now))
        con.execute("INSERT INTO campaign_versions VALUES (?,?,?,?,?)",
                    (campaign_id, version, draft.model_dump_json(), actor, now))
    return {"id": campaign_id, "version": version, "code": draft.code}


def _draft(con, campaign_id: str, version: int) -> CampaignDraft:
    row = con.execute("SELECT payload FROM campaign_versions WHERE campaign_id=? AND version=?",
                      (campaign_id, version)).fetchone()
    if not row:
        raise KeyError("Versión no encontrada")
    return CampaignDraft.model_validate_json(dict(row)["payload"])


def publish(campaign_id: str, version: int, actor: str, *, routes_available: list[str] | None = None) -> dict:
    routes_available = available_routes() if routes_available is None else routes_available
    with db.connect() as con:
        row = _row(con, campaign_id, lock=True)
        draft = _draft(con, campaign_id, version)
        if draft.end_date <= datetime.now(timezone.utc):
            raise ValueError("La campaña ya venció")
        if draft.max_uses is not None and draft.max_uses < row["used_count"]:
            raise ValueError("El cupo no puede ser menor que los beneficios ya reservados o consumidos")
        if not routes_available:
            raise ValueError("No se pudieron verificar las rutas habilitadas en Brasper; intenta de nuevo")
        missing = [r for r in draft.routes if r != "ALL" and r not in routes_available]
        if missing:
            raise ValueError(f"Rutas sin tipo de cambio habilitado en Brasper: {', '.join(missing)}")
        for language, copy in draft.campaign_rules.messages.items():
            if copy.media_id and not media_library.approved(copy.media_id, language):
                raise ValueError(f"La imagen de {language} debe estar aprobada para promociones en ese idioma")
        con.execute("UPDATE campaigns SET published_version=?, active=1, updated_at=? WHERE id=?",
                    (version, util.now_iso(), campaign_id))
    observability.event("campaign.published", campaign_id=campaign_id, version=version)
    return {"ok": True, "published_version": version}


def disable(campaign_id: str) -> dict:
    with db.connect() as con:
        _row(con, campaign_id, lock=True)
        con.execute("UPDATE campaigns SET active=0, updated_at=? WHERE id=?", (util.now_iso(), campaign_id))
    return {"ok": True}


def inventory() -> list[dict]:
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()]
        out = []
        for row in rows:
            draft = _draft(con, row["id"], row["latest_version"])
            out.append({"id": row["id"], "code": row["code"], "version": row["latest_version"],
                        "published_version": row["published_version"], "active": bool(row["active"]),
                        "used_count": row["used_count"], "draft": json.loads(draft.model_dump_json())})
    return out


def history(campaign_id: str) -> list[dict]:
    with db.connect() as con:
        _row(con, campaign_id)
        rows = con.execute("SELECT * FROM campaign_versions WHERE campaign_id=? ORDER BY version DESC",
                           (campaign_id,)).fetchall()
    return [{"version": r["version"], "draft": json.loads(r["payload"]), "author": r["author"],
             "created_at": r["created_at"]} for r in rows]


def published_active(now: datetime | None = None) -> list[dict]:
    """Versiones publicadas, activas, dentro de vigencia y con cupo. Nunca borradores."""
    now = now or datetime.now(timezone.utc)
    out = []
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM campaigns WHERE active=1 AND published_version IS NOT NULL").fetchall()]
        for row in rows:
            try:
                draft = _draft(con, row["id"], row["published_version"])
            except (KeyError, ValidationError):
                continue
            if draft.start_date > now or draft.end_date < now or (
                    draft.max_uses is not None and row["used_count"] >= draft.max_uses):
                continue
            out.append({"campaign_id": row["id"], "code": row["code"], "version": row["published_version"],
                        "draft": draft})
    out.sort(key=lambda c: (-c["draft"].campaign_rules.priority, -c["draft"].discount_percentage, c["campaign_id"]))
    return out


# ---------------------------------------------------------------- elegibilidad
def eligibility(lead: dict) -> dict:
    """Solo con identidad verificada por el canal y dato de Brasper. None = no confirmable."""
    verified_identity = lead.get("identity_source") == "channel_phone_match" and bool(lead.get("brasper_user_id"))
    first = returning = None
    source = "insufficient"
    if verified_identity and lead.get("history_status") == "verified":
        first = lead.get("first_transfer_eligible") is True
        returning = (lead.get("completed_transfers") or 0) > 0
        source = "brasper_history"
    elif verified_identity and lead.get("is_first_transfer") is True:
        # «Sin ninguna transacción» en Brasper: suficiente para primer envío, no para recurrente.
        first, source = True, "brasper_no_transactions"
    return {"first_transfer": first, "returning": returning, "source": source}


def _segment_ok(segment: str, elig: dict) -> bool | None:
    if segment == "first_transfer":
        return elig["first_transfer"]
    if segment == "returning":
        return elig["returning"]
    return True if elig["source"] != "insufficient" else None


def _route_ok(draft: CampaignDraft, origin: str, destination: str) -> bool:
    return "ALL" in draft.routes or f"{origin}_{destination}" in draft.routes


def estimated_saving(draft: CampaignDraft, amount: float, commission: float) -> float:
    if amount < draft.campaign_rules.minimum_amount or (
            draft.campaign_rules.maximum_amount is not None and amount > draft.campaign_rules.maximum_amount):
        return 0.0
    cents = Decimal("0.01")
    saving = (Decimal(str(commission)) * Decimal(str(draft.discount_percentage)) / 100).quantize(cents, ROUND_HALF_UP)
    cap = draft.campaign_rules.maximum_discount
    if cap is not None:
        saving = min(saving, Decimal(str(cap)).quantize(cents, ROUND_HALF_UP))
    return float(saving)


def first_transfer_claimed(lead: dict, contact_id: str | None = None) -> bool:
    keys = _identity_keys(lead, contact_id)
    if not keys:
        return False
    with db.connect() as con:
        return bool(con.execute(f"SELECT 1 FROM first_transfer_claims WHERE identity_key IN ({','.join('?' * len(keys))})",
                                tuple(keys)).fetchone())


def for_quote(lead: dict, origin: str, destination: str, amount: float, commission: float,
              contact_id: str | None = None) -> dict | None:
    """Campaña aplicable a una cotización de un cliente con elegibilidad confirmada.
    Informativo: no reserva y no cambia el cobro registrado en Brasper."""
    elig = eligibility(lead)
    claimed = first_transfer_claimed(lead, contact_id)
    for item in published_active():
        draft = item["draft"]
        if not _route_ok(draft, origin, destination) or _segment_ok(draft.campaign_rules.segment, elig) is not True:
            continue
        if draft.campaign_rules.segment == "first_transfer" and claimed:
            continue
        saving = estimated_saving(draft, amount, commission)
        if saving > 0:
            return {**item, "saving": saving, "eligibility_source": elig["source"]}
    return None


# ---------------------------------------------------------------- beneficios
def _identity_keys(lead: dict, contact_id: str | None) -> list[str]:
    keys = []
    if lead.get("brasper_user_id"):
        keys.append(f"user:{lead['brasper_user_id']}")
    if contact_id:
        keys.append(f"contact:{contact_id}")
    if lead.get("numero_documento"):
        doc = f"{(lead.get('tipo_documento') or '').lower()}:{str(lead['numero_documento']).strip().upper()}"
        keys.append("doc:" + hashlib.sha256(doc.encode()).hexdigest())
    return keys


def reserve(campaign_id: str, conversation_id: str, operation_ref: str, actor: str,
            advisor_verified: bool = False) -> dict:
    """Reserva al registrar la operación pendiente en Brasper. Atómico: cupo total, límite por
    persona y primer envío único por identidad (cliente, contacto, documento) entre campañas."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,80}", operation_ref or ""):
        raise BenefitRejected("Indica la referencia de la operación registrada en Brasper")
    conv = db.get_conversation(conversation_id) or {}
    lead = conv.get("lead_data") or {}
    keys = _identity_keys(lead, conv.get("contact_id"))
    if not keys:
        raise BenefitRejected("El cliente no está identificado")
    now = util.now_iso()
    benefit_id = uuid.uuid4().hex
    with db.connect() as con:
        row = _row(con, campaign_id, lock=True)
        if not row["active"] or not row["published_version"]:
            raise BenefitRejected("La campaña no está publicada")
        draft = _draft(con, campaign_id, row["published_version"])
        current = datetime.now(timezone.utc)
        if draft.start_date > current or draft.end_date < current:
            raise BenefitRejected("La campaña está fuera de vigencia")
        elig = eligibility(lead)
        ok = _segment_ok(draft.campaign_rules.segment, elig)
        source = elig["source"]
        if ok is False:
            raise BenefitRejected("El cliente no cumple la condición de la campaña según Brasper")
        if ok is None:
            if not advisor_verified:
                raise BenefitRejected("No se pudo confirmar la elegibilidad con Brasper; verifica el historial antes de reservar")
            source = "advisor_verified"
        if con.execute("SELECT 1 FROM campaign_benefits WHERE campaign_id=? AND operation_ref=? AND state!='released'",
                       (campaign_id, operation_ref)).fetchone():
            raise BenefitRejected("Esa operación ya tiene este beneficio")
        cap = draft.max_uses if draft.max_uses is not None else 2 ** 62
        if not con.execute("UPDATE campaigns SET used_count=used_count+1, updated_at=? WHERE id=? AND used_count < ?",
                           (now, campaign_id, cap)).rowcount:
            raise BenefitRejected("La campaña alcanzó su cupo total")
        person = keys[0]
        con.execute("INSERT INTO campaign_person_uses VALUES (?,?,0) ON CONFLICT(campaign_id, person_key) DO NOTHING",
                    (campaign_id, person))
        if not con.execute("UPDATE campaign_person_uses SET used=used+1 WHERE campaign_id=? AND person_key=? AND used < ?",
                           (campaign_id, person, draft.per_user_limit)).rowcount:
            raise BenefitRejected("El cliente ya usó todos sus beneficios de esta campaña")
        if draft.campaign_rules.segment == "first_transfer":
            for key in keys:
                if not con.execute("INSERT INTO first_transfer_claims VALUES (?,?,?) ON CONFLICT(identity_key) DO NOTHING",
                                   (key, benefit_id, now)).rowcount:
                    raise BenefitRejected("El beneficio de primer envío ya fue reservado o usado por este cliente")
        con.execute("INSERT INTO campaign_benefits VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (benefit_id, campaign_id, row["published_version"], person, conversation_id, operation_ref,
                     "reserved", source, actor, now, now, None))
        con.execute("INSERT INTO campaign_benefit_events VALUES (?,?,?,?,?,?)",
                    (benefit_id, None, "reserved", actor, f"operación {operation_ref}; elegibilidad {source}", now))
    observability.event("campaign.benefit_reserved", campaign_id=campaign_id, benefit_id=benefit_id, source=source)
    return {"id": benefit_id, "state": "reserved", "eligibility_source": source}


def _close(benefit_id: str, state: str, actor: str, note: str | None = None) -> dict:
    now = util.now_iso()
    with db.connect() as con:
        _tx(con)
        row = con.execute("SELECT * FROM campaign_benefits WHERE id=?", (benefit_id,)).fetchone()
        if not row:
            raise KeyError("Beneficio no encontrado")
        row = dict(row)
        if not con.execute("UPDATE campaign_benefits SET state=?, updated_at=?, closed_by=? WHERE id=? AND state='reserved'",
                           (state, now, actor, benefit_id)).rowcount:
            raise BenefitRejected(f"El beneficio ya está {row['state']}; no se cambia otra vez")
        con.execute("INSERT INTO campaign_benefit_events VALUES (?,?,?,?,?,?)",
                    (benefit_id, "reserved", state, actor, note, now))
        if state in {"released", "expired"}:
            con.execute("UPDATE campaigns SET used_count=used_count-1, updated_at=? WHERE id=? AND used_count > 0",
                        (now, row["campaign_id"]))
            con.execute("UPDATE campaign_person_uses SET used=used-1 WHERE campaign_id=? AND person_key=? AND used > 0",
                        (row["campaign_id"], row["person_key"]))
            con.execute("DELETE FROM first_transfer_claims WHERE benefit_id=?", (benefit_id,))
    observability.event(f"campaign.benefit_{state}", benefit_id=benefit_id)
    return {"id": benefit_id, "state": state}


def consume(benefit_id: str, actor: str) -> dict:
    """Operación completada: el beneficio queda consumido (no se libera nunca)."""
    return _close(benefit_id, "consumed", actor)


def release(benefit_id: str, actor: str) -> dict:
    """Operación fallida o cancelada: libera exactamente una vez."""
    return _close(benefit_id, "released", actor)


def expire(benefit_id: str, actor: str, note: str) -> dict:
    """Vencimiento tras conciliación humana (la operación no llegó a registrarse). Nunca automático:
    una reserva pendiente no se libera por cerrar o reabrir el chat."""
    if not (note or "").strip():
        raise BenefitRejected("Indica cómo se concilió el vencimiento")
    return _close(benefit_id, "expired", actor, note.strip()[:500])


def transitions(benefit_id: str) -> list[dict]:
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM campaign_benefit_events WHERE benefit_id=? ORDER BY at, rowid",
                                             (benefit_id,)).fetchall()]


def discount_applicable() -> bool:
    """¿El procedimiento humano en Brasper puede respetar el importe con descuento IA? Hasta que el
    responsable lo verifique (`campaigns.discount_applicable` en tenants.json), el bot no promete un
    descuento aplicable: presenta la promoción y deriva su confirmación al asesor."""
    cfg = (tenants.get_config() or {}).get("campaigns") or {}
    return cfg.get("discount_applicable") is True


def benefit(benefit_id: str) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM campaign_benefits WHERE id=?", (benefit_id,)).fetchone()
    return dict(row) if row else None


def benefits(campaign_id: str | None = None, conversation_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM campaign_benefits WHERE 1=1", []
    if campaign_id:
        sql += " AND campaign_id=?"
        args.append(campaign_id)
    if conversation_id:
        sql += " AND conversation_id=?"
        args.append(conversation_id)
    with db.connect() as con:
        return [dict(r) for r in con.execute(sql + " ORDER BY created_at DESC LIMIT 500", tuple(args)).fetchall()]


# ---------------------------------------------------------------- migración de datos
def import_legacy(rows: list[dict], actor: str) -> dict:
    """Importa campañas del diseño anterior (API financiera) conservando identificador,
    textos/imágenes ES/PT y reglas. Quedan como BORRADOR: se revisan y publican en IA."""
    imported, skipped = [], []
    for item in rows:
        known = set(CampaignDraft.model_fields)
        payload = {k: v for k, v in dict(item.get("draft") or {}).items() if k in known}
        payload.setdefault("name", payload.get("code") or "Campaña importada")
        try:
            draft = CampaignDraft.model_validate(payload)
        except ValidationError as exc:
            skipped.append({"code": payload.get("code"), "error": str(exc.errors()[0].get("msg"))})
            continue
        with db.connect() as con:
            exists = draft.code and con.execute("SELECT 1 FROM campaigns WHERE code=?", (draft.code,)).fetchone()
        if exists:
            skipped.append({"code": draft.code, "error": "ya importada"})
            continue
        imported.append(save(draft, actor)["code"])
    return {"imported": imported, "skipped": skipped}
