"""Resumen determinista de derivación (etapa 4): motivo, datos verificados, pasos
realizados y pendiente. Se guarda en `lead_data.handoff` para que el asesor reciba
contexto completo en el panel. Sin LLM.
"""
from __future__ import annotations

from . import db
from .util import now_iso

REASON_LABELS = {
    "keyword": "El cliente pidió un asesor",
    "checkout": "Quiere proceder con el envío",
    "llm_error": "Fallo del modelo de IA",
    "media": "Envió un comprobante / adjunto",
    "deposit_accounts_unavailable": "Cuentas de depósito no disponibles",
    "status_lookup_unavailable": "Consulta de estado de envío (sin API)",
    "info_unavailable": "Pregunta sin respuesta aprobada",
    "repetition": "El bot se estaba repitiendo",
    "audio_unreadable": "Audio no transcribible",
    "sync_error": "No se pudo sincronizar el cliente con Brasper",
    "no_advisor_available": "Sin asesores disponibles (en cola)",
    "high_amount": "Monto alto: requiere asesor",
    "coex_human": "Intervención humana desde el celular",
    "manual": "Tomada manualmente desde el panel",
}

_LEAD_FIELDS = (("nombre", "Nombre"), ("nombres", "Nombres"), ("apellidos", "Apellidos"),
                ("tipo_documento", "Documento"), ("numero_documento", "Nº documento"),
                ("telefono", "Teléfono"), ("ruta", "Ruta"), ("monto_enviar", "Monto a enviar"),
                ("monto_recibir", "Monto a recibir"), ("tasa", "Tasa"), ("aplica_promo", "Promo"),
                ("brasper_user_id", "ID cliente Brasper"), ("commercial_stage", "Etapa"))

_STAGE_PENDING = {
    "awaiting_name": "Pedir nombre completo",
    "collecting_identity": "Completar identificación (documento / teléfono)",
    "identified": "Cotizar y confirmar monto",
    "client_synced": "Mostrar cuentas y esperar depósito",
    "awaiting_deposit": "Esperar comprobante de depósito",
    "proof_received": "Validar el comprobante en el sistema Brasper y registrar la operación",
    "sync_error": "Reintentar alta del cliente en Brasper",
}


def build(cid: str, reason: str, *, extra: str | None = None, store: bool = True) -> dict:
    lead = db.get_lead_data(cid) or {}
    msgs = db.get_messages(cid)
    user_msgs = [m for m in msgs if m.get("role") == "user"][-3:]
    verified = [f"{label}: {lead[k]}" for k, label in _LEAD_FIELDS if lead.get(k) not in (None, "", False)]
    steps: list[str] = []
    if lead.get("client_lookup_done"):
        steps.append("Búsqueda del cliente en Brasper realizada")
    if lead.get("monto_enviar"):
        steps.append("Cotización entregada")
    if lead.get("brasper_user_id"):
        steps.append("Cliente sincronizado con Brasper")
    if lead.get("deposit_accounts_shown"):
        steps.append("Cuentas de depósito mostradas")
    if lead.get("commercial_stage") == "proof_received":
        steps.append("Comprobante recibido (NO validado)")
    pending = _STAGE_PENDING.get(str(lead.get("commercial_stage") or ""), "Atender la consulta del cliente")
    if reason == "status_lookup_unavailable":
        pending = "Verificar el estado del envío en el sistema Brasper y responder"
    if reason == "info_unavailable":
        pending = "Responder la pregunta con información aprobada"
    last = [f"«{(m.get('content') or '').strip()[:160]}»" for m in user_msgs]
    lines = [f"Motivo: {REASON_LABELS.get(reason, reason)}" + (f" — {extra}" if extra else "")]
    if verified:
        lines.append("Datos verificados: " + "; ".join(verified))
    if steps:
        lines.append("Pasos realizados: " + "; ".join(steps))
    lines.append("Pendiente: " + pending)
    if last:
        lines.append("Últimos mensajes del cliente: " + " · ".join(last))
    summary = {"reason": reason, "reason_label": REASON_LABELS.get(reason, reason), "extra": extra,
               "pending": pending, "steps": steps, "verified": verified, "text": "\n".join(lines), "at": now_iso()}
    if store:
        db.merge_lead_data(cid, {"handoff": summary})
    return summary
