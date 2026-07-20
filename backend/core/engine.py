"""Compatibilidad publica del motor de conversacion.

La orquestacion principal vive en `core.agent_graph` con LangGraph.
"""
from . import agent_graph, llm, redis_runtime


class ConversationBusyError(Exception):
    pass


async def handle_message(tenant: dict, user_ref: str, text: str,
                         channel: str = "webchat",
                         conversation_id: str | None = None,
                         user_media: dict | None = None) -> dict:
    lock_name = redis_runtime.key(
        tenant["id"], "lock", "conversation", channel, conversation_id or user_ref
    )
    token = redis_runtime.acquire_lock(lock_name, ttl_seconds=45, wait_seconds=2)
    if not token:
        raise ConversationBusyError("Conversacion ocupada; intenta de nuevo en unos segundos")
    try:
        return await agent_graph.handle_message(tenant, user_ref, text, channel,
                                                conversation_id, user_media=user_media)
    finally:
        redis_runtime.release_lock(lock_name, token)
