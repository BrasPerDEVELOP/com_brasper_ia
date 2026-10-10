"""Oferta de campaña durante la bienvenida / primer envío (plan de campañas §2–§3).

- Solo presentación: la campaña se muestra como beneficio **sujeto a comprobación**. La
  elegibilidad, los cupos y la reserva se controlan en `core.campaigns` (persistencia IA)
  con datos de Brasper; el cobro final lo registra Brasper.
- Idioma: texto e imagen del mismo idioma (es/pt). Si el idioma de la conversación no
  tiene evidencia, se pregunta una vez en vez de adivinar.
- Cada contacto recibe cada versión publicada como máximo una vez (también tras reabrir
  la conversación o reintentar el webhook). Publicar una campaña no envía nada por sí
  solo: la oferta solo acompaña una respuesta a un mensaje del cliente.
"""
from __future__ import annotations

from . import campaigns, db, features, idempotency, media_library, observability, util

DISCLAIMER = {
    "es": ("Beneficio sujeto a comprobación: se aplica solo si tu identidad y tu historial de envíos lo "
           "confirman al cotizar con tu cuenta Brasper."),
    "pt": ("Benefício sujeito a verificação: só se aplica se a sua identidade e o seu histórico de envios "
           "o confirmarem ao cotar com a sua conta Brasper."),
}
ASK_LANGUAGE = "¿Prefieres que sigamos en español o em português? / Prefere continuar em português ou español?"


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS campaign_offers (subject TEXT NOT NULL, coupon_id TEXT NOT NULL, "
                    "version INTEGER NOT NULL, conversation_id TEXT NOT NULL, language TEXT NOT NULL, "
                    "asset_id TEXT, asset_version INTEGER, offered_at TEXT NOT NULL, delivery_key TEXT, "
                    "state TEXT NOT NULL DEFAULT 'prepared', updated_at TEXT, "
                    "PRIMARY KEY(subject, coupon_id, version))")
        # Tabla del diseño anterior (8 columnas): agregar lo que falte sin perder ofertas (= migración 0014).
        existing = _columns(con)
        for name, ddl in (("delivery_key", "TEXT"), ("state", "TEXT NOT NULL DEFAULT 'legacy_unverified'"),
                          ("updated_at", "TEXT")):
            if name not in existing:
                con.execute(f"ALTER TABLE campaign_offers ADD COLUMN {name} {ddl}")
        rows = [dict(r) for r in con.execute("SELECT subject, coupon_id, version, language, offered_at "
                                             "FROM campaign_offers WHERE delivery_key IS NULL").fetchall()]
        for r in rows:
            con.execute("UPDATE campaign_offers SET delivery_key=?, updated_at=COALESCE(updated_at, ?) "
                        "WHERE subject=? AND coupon_id=? AND version=?",
                        (idempotency.make_key("campaign_offer", r["subject"], r["coupon_id"], r["version"], r["language"]),
                         r["offered_at"], r["subject"], r["coupon_id"], r["version"]))


def _columns(con) -> set[str]:
    if db.is_postgres():
        return {r["column_name"] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='campaign_offers'").fetchall()}
    return {r[1] for r in con.execute("PRAGMA table_info(campaign_offers)").fetchall()}


def active() -> list[dict]:
    """Campañas publicadas y vigentes de la plataforma IA (nunca borradores)."""
    out = []
    for item in campaigns.published_active():
        draft = item["draft"]
        out.append({"coupon_id": item["campaign_id"], "published_version": item["version"],
                    "segment": draft.campaign_rules.segment, "priority": draft.campaign_rules.priority,
                    "discount_percentage": draft.discount_percentage, "routes": list(draft.routes),
                    "messages": {lang: {"text": copy.text, "media_id": copy.media_id}
                                 for lang, copy in draft.campaign_rules.messages.items()}})
    return out


def _subject(cid: str) -> str:
    conv = db.get_conversation(cid) or {}
    return conv.get("contact_id") or f"{conv.get('channel')}:{conv.get('user_ref')}"


def _eligible_segments(lead: dict) -> set[str]:
    # Brasper confirma que ya no es primer envío: no se le ofrece. Sin dato suficiente: se
    # muestra como sujeto a comprobación (nunca se afirma elegibilidad).
    elig = campaigns.eligibility(lead)
    segments = {"all"}
    if elig["first_transfer"] is not False:
        segments.add("first_transfer")
    if elig["returning"] is True:
        segments.add("returning")
    return segments


def welcome_offer(cid: str, lead: dict, language: str, language_known: bool) -> dict:
    """{} sin oferta; {"ask_language": True} para preguntar el idioma; {"banner": {...}} con la
    oferta a anexar (texto) y a entregar (imagen aprobada del mismo idioma, una sola vez)."""
    if not features.enabled("campaigns"):
        return {}
    segments = _eligible_segments(lead)
    offers = [o for o in active() if o["segment"] in segments]
    if not offers:
        return {}
    if not language_known or language not in {"es", "pt"}:
        if lead.get("offer_language_asked"):
            return {}
        db.merge_lead_data(cid, {"offer_language_asked": True})
        return {"ask_language": True}
    for offer in offers:
        banner = _record(cid, offer, language, with_disclaimer=True)
        if banner:
            return {"banner": banner}
    return {}


def _record(cid: str, offer: dict, language: str, *, with_disclaimer: bool) -> dict | None:
    """Registra la versión ofrecida a este contacto (una sola vez) y arma el banner."""
    subject = _subject(cid)
    copy = offer["messages"][language]
    asset = media_library.approved(copy.get("media_id"), language) if copy.get("media_id") else None
    key = idempotency.make_key("campaign_offer", subject, offer["coupon_id"], offer["published_version"], language)
    now = util.now_iso()
    with db.connect() as con:
        # «prepared» = registrada antes de enviar; la entrega real la actualiza mark_delivery.
        inserted = con.execute(
            "INSERT INTO campaign_offers (subject, coupon_id, version, conversation_id, language, asset_id, "
            "asset_version, offered_at, delivery_key, state, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(subject, coupon_id, version) DO NOTHING",
            (subject, offer["coupon_id"], int(offer["published_version"]), cid, language,
             asset["asset_id"] if asset else None, asset["version"] if asset else None,
             now, key, "prepared", now)).rowcount
    if not inserted:
        return None  # ya ofrecida a este contacto: no se repite
    observability.event("campaign.offered", conversation_id=cid, coupon_id=offer["coupon_id"],
                        version=offer["published_version"], language=language, image=bool(asset))
    text = copy["text"].strip() + (f"\n{DISCLAIMER[language]}" if with_disclaimer else "")
    return {"text": text, "asset_id": asset["asset_id"] if asset else None,
            "asset_version": asset["version"] if asset else None,
            "delivery_key": key, "campaign": True}


PENDING_NOTE = {
    "es": ("La promoción «{name}» está vigente para esta ruta. Un asesor confirmará si puede aplicarse a tu "
           "operación al registrarla; esta cotización no incluye el descuento."),
    "pt": ("A promoção «{name}» está vigente para esta rota. Um atendente confirmará se pode ser aplicada à sua "
           "operação ao registrá-la; esta cotação não inclui o desconto."),
}

QUOTE_NOTE = {
    "es": ("Con la promoción «{name}» el ahorro estimado es de {saving} {currency} sobre la comisión. "
           "Se confirma al registrar tu operación con un asesor; esta cotización no reserva el beneficio."),
    "pt": ("Com a promoção «{name}» a economia estimada é de {saving} {currency} sobre a comissão. "
           "É confirmada ao registrar a sua operação com um atendente; esta cotação não reserva o benefício."),
}


def quote_offer(cid: str, match: dict, language: str, currency: str,
                applicable: bool = False) -> tuple[str, dict | None]:
    """Nota de la promoción + imagen/texto de la campaña solo la primera vez. Sin confirmar que el
    procedimiento humano en Brasper respeta el importe, no se promete un ahorro aplicable."""
    language = language if language in {"es", "pt"} else "es"
    draft = match["draft"]
    if applicable:
        note = QUOTE_NOTE[language].format(name=draft.name, saving=f"{match['saving']:.2f}", currency=currency)
    else:
        note = PENDING_NOTE[language].format(name=draft.name)
        observability.event("campaign.discount_not_applicable", conversation_id=cid,
                            campaign_id=match["campaign_id"], reason="registration_procedure_unverified")
    offer = {"coupon_id": match["campaign_id"], "published_version": match["version"],
             "messages": {lang: {"text": c.text, "media_id": c.media_id}
                          for lang, c in draft.campaign_rules.messages.items()}}
    banner = _record(cid, offer, language, with_disclaimer=False)
    if banner:
        note = f"{banner['text']}\n{note}"
    return note, banner


def mark_delivery(delivery_key: str, result: dict) -> None:
    """Estado de la imagen de la oferta: sent | text_only | failed | uncertain (nunca se reenvía sola)."""
    reason = result.get("reason")
    if result.get("sent"):
        state = "sent"
    elif reason == "text_only":
        state = "text_only"
    elif reason in {"approval_changed"} or result.get("status") in range(400, 500):
        state = "failed"
    else:
        state = "uncertain"
    with db.connect() as con:
        con.execute("UPDATE campaign_offers SET state=?, updated_at=? WHERE delivery_key=? AND state='prepared'",
                    (state, util.now_iso(), delivery_key))


def offered(cid: str) -> list[dict]:
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM campaign_offers WHERE conversation_id=? "
                                             "ORDER BY offered_at", (cid,)).fetchall()]
