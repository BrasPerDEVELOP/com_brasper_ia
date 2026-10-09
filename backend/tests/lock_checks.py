"""Exclusión por conversación sin depender del estado de Redis (R1), sin red."""
import asyncio
from unittest.mock import patch

from core import db, db_lock, engine, redis_runtime


class _FakeRedis:
    """Redis sano que concede su propio lock: no debe saltarse el lock común en la base."""
    def __init__(self):
        self.keys = {}

    def set(self, name, value, nx=False, ex=None):
        if nx and name in self.keys:
            return False
        self.keys[name] = value
        return True

    def eval(self, script, n, name, token):
        if self.keys.get(name) == token:
            del self.keys[name]


class _DownRedis:
    def set(self, *a, **k):
        import redis
        raise redis.ConnectionError("down")


def lock_checks():
    # 1) Base sin respuesta: no hay exclusión -> no se procesa (antes devolvía un token falso).
    with patch.object(db_lock, "acquire", side_effect=RuntimeError("db down")):
        assert redis_runtime.acquire_lock("r1:dbdown", wait_seconds=0) is None
        try:
            asyncio.new_event_loop().run_until_complete(engine.handle_message("r1-user", "hola"))
            raise AssertionError("debía rechazarse sin lock")
        except engine.ConversationBusyError:
            pass

    # 2) Recuperación parcial: A ve Redis caído (solo base), B ve Redis sano -> B igual queda bloqueado.
    with patch.object(redis_runtime, "client", return_value=_DownRedis()):
        a = redis_runtime.acquire_lock("r1:mixed", wait_seconds=0)
    assert a
    healthy = _FakeRedis()
    with patch.object(redis_runtime, "client", return_value=healthy):
        assert redis_runtime.acquire_lock("r1:mixed", wait_seconds=0.1) is None, "lock común en la base"
        assert "r1:mixed" not in healthy.keys, "no deja un lock Redis huérfano al ceder"
        redis_runtime.release_lock("r1:mixed", a)
        b = redis_runtime.acquire_lock("r1:mixed", wait_seconds=0.1)
        assert b and healthy.keys.get("r1:mixed")
        redis_runtime.release_lock("r1:mixed", b)
        assert "r1:mixed" not in healthy.keys

    # 3) Lease vencido durante el procesamiento: la respuesta no se entrega.
    with patch.object(redis_runtime, "still_held", return_value=False):
        out = asyncio.new_event_loop().run_until_complete(engine.handle_message("r1-lease", "hola"))
    assert out["paused"] and out["response"] == ""
    token = redis_runtime.acquire_lock("r1:lease", ttl_seconds=30, wait_seconds=0)
    assert redis_runtime.still_held("r1:lease", token)
    with db.connect() as con:
        con.execute("UPDATE conversation_locks SET expires_at='2000-01-01' WHERE name='r1:lease'")
    assert not redis_runtime.still_held("r1:lease", token)
    other = redis_runtime.acquire_lock("r1:lease", wait_seconds=0)
    assert other and not redis_runtime.still_held("r1:lease", token)

    _long_processing_checks()


def _long_processing_checks():
    """Procesamiento más largo que el TTL con dos workers: la renovación mantiene la exclusión;
    si la renovación falla, el trabajo se cancela y no hay respuesta."""
    import threading
    import time
    from core import agent_graph

    def run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    cid = db.get_or_create_conversation("lease-long", "webchat")
    real = agent_graph.handle_message

    spans = []

    async def slow(user_ref, text, channel, conversation_id, user_media=None, link_token=None):
        start = time.monotonic()
        if text == "bloqueante":
            time.sleep(1.6)          # nodo síncrono que bloquea el event loop (> TTL)
        else:
            await asyncio.sleep(1.6)  # LLM lento
        spans.append((start, time.monotonic()))
        return await real(user_ref, text, channel, conversation_id, user_media=user_media, link_token=link_token)

    for mode in ("lento", "bloqueante"):
        results = {}
        spans.clear()

        def worker_a():
            results["a"] = run(engine.handle_message("lease-long", mode, conversation_id=cid))

        with patch.object(engine, "LOCK_TTL_SECONDS", 0.6), patch.object(agent_graph, "handle_message", slow):
            t = threading.Thread(target=worker_a)
            t.start()
            time.sleep(1.0)  # A ya superó el TTL original: sin renovación, B entraría
            try:
                run(engine.handle_message("lease-long", "segundo worker", conversation_id=cid))
                results["b"] = "processed"
            except engine.ConversationBusyError:
                results["b"] = "busy"
            t.join(10)
        assert "a" in results and not results["a"].get("paused"), (mode, results)
        # B esperó o se rechazó, pero nunca procesó a la vez que A (que duró más que el TTL).
        if results["b"] == "processed":
            assert len(spans) == 2 and spans[1][0] >= spans[0][1], (mode, spans)

    # Renovación imposible (base caída o lease tomado): el trabajo se cancela sin responder.
    finished = {}

    async def very_slow(user_ref, text, channel, conversation_id, user_media=None, link_token=None):
        await asyncio.sleep(2)
        finished["done"] = True
        return await real(user_ref, text, channel, conversation_id, user_media=user_media, link_token=link_token)

    with patch.object(engine, "LOCK_TTL_SECONDS", 0.3), patch.object(agent_graph, "handle_message", very_slow), \
         patch.object(redis_runtime, "renew_lock", return_value=False):
        try:
            run(engine.handle_message("lease-long", "hola", conversation_id=cid))
            raise AssertionError("debía cancelarse al perder el lease")
        except engine.ConversationBusyError:
            pass
    assert "done" not in finished, "el trabajo no continúa tras perder la exclusión"
    # La conversación queda libre para el siguiente mensaje.
    assert redis_runtime.acquire_lock(redis_runtime.key("lock", "conversation", "webchat", cid), wait_seconds=0.5)
