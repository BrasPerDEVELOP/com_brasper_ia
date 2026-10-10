"""Compatibilidad publica del motor de conversacion.

La orquestacion principal vive en `core.agent_graph` con LangGraph.
"""
from . import agent_graph, db, identity_link, llm, redis_runtime


class ConversationBusyError(Exception):
    pass


def delivery_allowed(out: dict) -> bool:
    """Check immediately before each automatic send, including after media awaits."""
    conv = db.get_conversation(out.get("conversation_id", ""))
    if not conv or conv.get("status") == "closed" or out.get("paused"):
        return False
    expected = out.get("human_revision")
    return expected is not None and int(conv.get("human_revision", 0)) == expected


# Lease por conversación; se renueva cada TTL/3 mientras dura el procesamiento (core.lease).
LOCK_TTL_SECONDS = 45


async def _process(user_ref, text, channel, conversation_id, user_media) -> dict:
    from . import engagement
    # El token de vinculación se separa antes de guardar el mensaje, de la encuesta y del LLM.
    text, link_token = identity_link.extract_token(text)
    out = None if link_token else engagement.receive(user_ref, channel, text, conversation_id)
    if out is None:
        out = await agent_graph.handle_message(user_ref, text, channel, conversation_id,
                                               user_media=user_media, link_token=link_token)
    conv = db.get_conversation(out["conversation_id"]) or {}
    if out.get("flow") != "satisfaction":
        if conv.get("status") == "handoff" and not conv.get("assigned_to"):
            engagement.schedule(out["conversation_id"], "waiting")
        elif conv.get("status") == "active":
            engagement.schedule(out["conversation_id"], "inactivity")
    return out


async def handle_message(user_ref: str, text: str,
                         channel: str = "webchat",
                         conversation_id: str | None = None,
                         user_media: dict | None = None) -> dict:
    import asyncio
    from .lease import Lease
    lock_name = redis_runtime.key(
        "lock", "conversation", channel, conversation_id or user_ref
    )
    token = redis_runtime.acquire_lock(lock_name, ttl_seconds=LOCK_TTL_SECONDS, wait_seconds=2)
    if not token:
        raise ConversationBusyError("Conversacion ocupada; intenta de nuevo en unos segundos")
    from .lease import LeaseLost, activate, deactivate
    loop = asyncio.get_running_loop()
    lease = Lease(lock_name, token, LOCK_TTL_SECONDS)
    # El lease viaja en el contexto: la tarea y los hilos de herramientas lo heredan y cada
    # escritura lo comprueba (lease.guard). Un nodo síncrono que siga corriendo tras perderlo
    # no puede escribir; la cancelación cubre además los puntos de espera asíncronos.
    ctx_token = activate(lease)
    try:
        task = asyncio.ensure_future(_process(user_ref, text, channel, conversation_id, user_media))
    finally:
        deactivate(ctx_token)
    lease.on_lost = lambda: loop.call_soon_threadsafe(task.cancel)
    lease.start()
    try:
        try:
            out = await task
        except (asyncio.CancelledError, LeaseLost):
            if lease.lost:
                raise ConversationBusyError("Se perdió la exclusión de la conversación; no se responde")
            raise
        if not lease.held():
            # Propiedad perdida justo al terminar: la respuesta no está protegida.
            from . import observability
            observability.event("conversation.lock_lost", conversation_id=out.get("conversation_id"))
            return {**out, "response": "", "banner": None, "paused": True}
        if not delivery_allowed(out):
            return {**out, "response": "", "banner": None, "paused": True}
        if out.get("banner"):
            out["banner"]["human_revision"] = out["human_revision"]
        return out
    finally:
        lease.stop()
        redis_runtime.release_lock(lock_name, token)
