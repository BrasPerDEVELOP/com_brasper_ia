"""Expediente IA de una operación (plan de campañas y usuarios §F).

Cuando el cliente acepta una cotización vigente y pasa al pago se abre un expediente con
el snapshot de la cotización (ruta, montos, tasa, comisión, promoción y su estado). Los
comprobantes que envía se enlazan ahí. El asesor verifica el dinero y genera la transacción
en Brasper (fuera de IA) y luego registra aquí la referencia oficial.

Nunca: confirmar pagos, crear transacciones financieras ni extraer una confirmación de la
imagen del comprobante. Cerrar o reabrir el chat no cambia el expediente ni libera reservas.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from . import db, observability, util

STATES = ("accepted", "proof_received", "registered", "closed", "cancelled")


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS sales_cases (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
                    "status TEXT NOT NULL, quote TEXT NOT NULL, campaign TEXT, accepted_at TEXT NOT NULL, "
                    "quote_expires_at TEXT, operation_ref TEXT, proofs TEXT NOT NULL DEFAULT '[]', "
                    "updated_at TEXT NOT NULL, updated_by TEXT)")
        con.execute("CREATE INDEX IF NOT EXISTS sales_cases_conversation ON sales_cases(conversation_id, status)")


def _validity_minutes() -> int:
    from . import quotes
    return quotes._tc_validity_minutes()


def quote_snapshot(lead: dict) -> dict | None:
    """Cotización vigente guardada por el cotizador determinista; None si no hay o venció."""
    required = ("ruta", "monto_enviar", "monto_recibir", "tasa", "cotizado_en")
    if any(lead.get(k) in (None, "") for k in required):
        return None
    try:
        quoted_at = datetime.fromisoformat(str(lead["cotizado_en"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    expires = quoted_at + timedelta(minutes=_validity_minutes())
    if expires <= datetime.now(timezone.utc):
        return None
    return {"ruta": lead["ruta"], "modo": lead.get("modo"), "monto_enviar": lead["monto_enviar"],
            "monto_recibir": lead["monto_recibir"], "tasa": lead["tasa"],
            # Desglose oficial de la cotización (comisión antes y después del cupón público).
            "comision_bruta": lead.get("comision_bruta"), "comision_tasa": lead.get("comision_tasa"),
            "comision": lead.get("comision"),
            "coupon_code": lead.get("coupon_code"), "coupon_savings_amount": lead.get("coupon_savings_amount"),
            "cotizado_en": lead["cotizado_en"], "expires_at": expires.isoformat(timespec="seconds")}


def _lock(con, conversation_id: str) -> None:
    """Serializa aceptaciones y adjuntos de una conversación: dos mensajes simultáneos no crean
    expedientes duplicados ni pierden comprobantes."""
    if db.is_postgres():
        con.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"case:{conversation_id}",))
    elif not con.in_transaction:
        con.execute("BEGIN IMMEDIATE")


def _active(con, conversation_id: str) -> dict | None:
    row = con.execute("SELECT * FROM sales_cases WHERE conversation_id=? AND status IN "
                      "('accepted','proof_received','registered') ORDER BY accepted_at DESC LIMIT 1",
                      (conversation_id,)).fetchone()
    return dict(row) if row else None


def open_case(conversation_id: str) -> dict:
    """Aceptación explícita (el cliente pide pagar/continuar). Solo sobre snapshot vigente."""
    lead = db.get_lead_data(conversation_id)
    snapshot = quote_snapshot(lead)
    if snapshot is None:
        return {"status": "quote_expired"}
    now = util.now_iso()
    case_id = uuid.uuid4().hex
    campaign = lead.get("campaign_estimate") or None
    with db.connect() as con:
        _lock(con, conversation_id)
        current = _active(con, conversation_id)
        if current and json.loads(current["quote"]) == snapshot:
            return {"status": "existing", "case": current}
        if current and current["status"] in ("proof_received", "registered"):
            # Ya hay comprobante u operación: una cotización nueva no lo reemplaza en silencio.
            return {"status": "case_in_progress", "case": current}
        if current and current["status"] == "accepted":
            # Nueva cotización aceptada sustituye a la anterior aún sin comprobante.
            con.execute("UPDATE sales_cases SET status='cancelled', updated_at=?, updated_by='bot' WHERE id=?",
                        (now, current["id"]))
        con.execute("INSERT INTO sales_cases (id, conversation_id, status, quote, campaign, accepted_at, "
                    "quote_expires_at, operation_ref, proofs, updated_at, updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (case_id, conversation_id, "accepted", json.dumps(snapshot), json.dumps(campaign) if campaign else None,
                     now, snapshot["expires_at"], None, "[]", now, "bot"))
    observability.event("case.accepted", conversation_id=conversation_id, case_id=case_id)
    return {"status": "created", "case": get(case_id)}


def get(case_id: str) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM sales_cases WHERE id=?", (case_id,)).fetchone()
    return dict(row) if row else None


def active_case(conversation_id: str) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM sales_cases WHERE conversation_id=? AND status IN "
                          "('accepted','proof_received','registered') ORDER BY accepted_at DESC LIMIT 1",
                          (conversation_id,)).fetchone()
    return dict(row) if row else None


def attach_proof(conversation_id: str, media: dict) -> dict | None:
    """Enlaza un comprobante al expediente abierto. Es evidencia para el asesor, no un pago."""
    with db.connect() as con:
        _lock(con, conversation_id)
        case = _active(con, conversation_id)
        if not case:
            return None
        proofs = json.loads(case["proofs"] or "[]")
        ref = {k: media.get(k) for k in ("provider", "ref", "kind", "mime_type", "filename") if media.get(k)}
        seen = {(p.get("provider"), p.get("ref")) for p in proofs}
        if ref.get("ref") and (ref.get("provider"), ref["ref"]) not in seen:  # reintentos del webhook no duplican
            proofs.append({**ref, "received_at": util.now_iso()})
        status = "proof_received" if case["status"] == "accepted" else case["status"]
        con.execute("UPDATE sales_cases SET proofs=?, status=?, updated_at=? WHERE id=?",
                    (json.dumps(proofs), status, util.now_iso(), case["id"]))
    return get(case["id"])


def register(case_id: str, operation_ref: str, actor: str) -> dict:
    """El asesor ya verificó el dinero y generó la transacción en Brasper: guarda la referencia."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,80}", operation_ref or ""):
        raise ValueError("Indica la referencia oficial de la operación en Brasper")
    with db.connect() as con:
        if not con.execute("UPDATE sales_cases SET operation_ref=?, status='registered', updated_at=?, updated_by=? "
                           "WHERE id=? AND status IN ('accepted','proof_received')",
                           (operation_ref, util.now_iso(), actor, case_id)).rowcount:
            raise ValueError("El expediente no está pendiente de registro")
    return get(case_id)


def close(case_id: str, actor: str, cancelled: bool = False) -> dict:
    with db.connect() as con:
        if not con.execute("UPDATE sales_cases SET status=?, updated_at=?, updated_by=? WHERE id=? AND status IN "
                           "('accepted','proof_received','registered')",
                           ("cancelled" if cancelled else "closed", util.now_iso(), actor, case_id)).rowcount:
            raise ValueError("El expediente ya está cerrado")
    return get(case_id)


def view(case: dict | None) -> dict | None:
    if not case:
        return None
    out = dict(case)
    out["quote"] = json.loads(case["quote"])
    out["campaign"] = json.loads(case["campaign"]) if case.get("campaign") else None
    out["proofs"] = json.loads(case["proofs"] or "[]")
    pending = []
    if case["status"] == "accepted":
        pending.append("Esperando comprobante del cliente")
    if case["status"] in ("accepted", "proof_received"):
        pending.append("Verificar el depósito en Brasper y generar la transacción; luego registrar la referencia")
    if out["campaign"] and out["campaign"].get("state") != "reserved":
        pending.append("Promoción: confirmar si se aplica y reservar el beneficio con la referencia")
    out["pending"] = pending
    return out
