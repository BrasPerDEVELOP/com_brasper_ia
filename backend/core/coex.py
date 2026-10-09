"""Actividad humana desde la app WhatsApp Business (coexistencia)."""
from __future__ import annotations

from . import db, handoff_summary, observability


def apply_human_echo(connection_id: str, msg: dict) -> str:
    """Un eco humano pausa el bot (takeover), invalida respuestas en curso y queda como
    mensaje del asesor en la conversación del destinatario. Nunca genera respuesta."""
    cid = db.get_or_create_conversation(f"wa:{msg['to']}", "whatsapp", connection_id=connection_id)
    db.set_connection(cid, connection_id)
    text = (msg.get("text") or "").strip() or f"📱 {msg.get('kind') or 'mensaje'} enviado desde el celular"
    db.invalidate_ai(cid)
    db.add_message(cid, "assistant", text, sender="agent", agent_email="whatsapp-app")
    handoff_summary.build(cid, "coex_human")
    observability.event("conversation.handoff", conversation_id=cid, reason="coex_human")
    db.merge_lead_data(cid, {"last_human_source": "whatsapp-app"})
    return cid
