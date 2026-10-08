"""Flujo compartido de audios (etapa 3): transcripción -> revisión de ambigüedad ->
grafo. Lo usan el webhook de WhatsApp (fallback en línea), el worker y Telegram, para
que las tres rutas conserven la evidencia (audio original + transcripción) y pidan
confirmación de cifras ambiguas de la misma manera.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from . import audio_review, auth, db, engine, features, handoff_summary, observability, policies

SendFn = Callable[[str], Awaitable[dict]]


async def process_transcript(*, channel: str, user_ref: str, text: str, media: dict | None,
                             send: SendFn, conversation_id: str | None = None) -> dict:
    """Procesa una transcripción ya obtenida.

    - Guarda SIEMPRE el mensaje del usuario con el audio original como media (evidencia).
    - Si la cifra es ambigua y la flag `audio_confirmation` está activa, responde con
      una confirmación puntual y NO ejecuta acciones (el siguiente mensaje del cliente
      sigue el flujo normal con la transcripción ya en el historial).
    - Si es legible, continúa con la IA (grafo) como texto normal.
    """
    text = (text or "").strip()
    cid = db.get_or_create_conversation(user_ref, channel, conversation_id)
    if db.conversation_status(cid) == "handoff":
        # Un asesor atiende: solo se registra la evidencia; el bot no responde.
        db.add_message(cid, "user", f"🎤 {text}" if text else "🎤 Audio", media=media)
        return {"conversation_id": cid, "paused": True, "transcribed": bool(text), "sent": False}
    review = audio_review.review_transcript(text)
    if features.enabled("audio_confirmation") and review["ambiguous"]:
        lang = policies.detect_language(text) if text else "es"
        db.add_message(cid, "user", f"🎤 {text}" if text else "🎤 Audio (no legible)", media=media)
        reply = audio_review.confirmation_reply(review, lang)
        db.add_message(cid, "assistant", reply)
        db.merge_lead_data(cid, {"audio_pending_confirmation": review.get("reason")})
        observability.event("audio.ambiguous", conversation_id=cid, reason=review.get("reason"),
                            amounts=review.get("amounts"))
        r = await send(reply)
        return {"conversation_id": cid, "ambiguous": True, "transcribed": True,
                "sent": bool(r.get("sent") or r.get("ok"))}
    out = await engine.handle_message(user_ref, text, channel=channel, conversation_id=cid,
                                      user_media={**(media or {}), "caption": text} if media else None)
    db.merge_lead_data(cid, {"audio_pending_confirmation": False})  # merge ignora None: False = resuelto
    if out.get("paused") or not (out.get("response") or "").strip():
        return {**out, "transcribed": True, "sent": False}
    r = await send(out["response"])
    return {**out, "transcribed": True, "sent": bool(r.get("sent") or r.get("ok"))}


_UNREADABLE_ACK = ("Recibí tu audio pero no pude entenderlo con claridad 🎤. "
                   "¿Me lo escribes en texto? Mientras tanto un asesor también puede escucharlo aquí mismo.")


async def unreadable(*, channel: str, user_ref: str, media: dict | None, send: SendFn,
                     error: str | None = None, conversation_id: str | None = None) -> dict:
    """Audio que no se pudo transcribir tras los reintentos: se conserva como evidencia
    (el asesor puede reproducirlo en el panel) y la conversación pasa a un asesor."""
    cid = db.get_or_create_conversation(user_ref, channel, conversation_id)
    db.add_message(cid, "user", "🎤 Audio (no transcrito)", media=media)
    db.merge_lead_data(cid, {"audio_state": "transcription_failed"})
    observability.event("audio.transcription_failed", conversation_id=cid, error=(error or "")[:120])
    sent = False
    if db.conversation_status(cid) != "handoff":
        db.set_conversation_status(cid, "handoff")
        auth.derive_to_advisor(cid)
        handoff_summary.build(cid, "audio_unreadable")
        db.add_message(cid, "assistant", _UNREADABLE_ACK)
        r = await send(_UNREADABLE_ACK)
        sent = bool(r.get("sent") or r.get("ok"))
    return {"conversation_id": cid, "transcribed": False, "sent": sent, "handoff": True}
