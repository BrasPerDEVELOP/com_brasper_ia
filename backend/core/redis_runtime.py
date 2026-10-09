"""Conexion Redis de runtime para health, locks y colas livianas."""
import os
import secrets
import time

import redis

_CLIENT = None
_RENEW_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("expire", KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
end
return 0
"""


def redis_url() -> str | None:
    value = (os.getenv("REDIS_URL") or "").strip()
    return value or None


def configured() -> bool:
    return bool(redis_url())


def client():
    global _CLIENT
    url = redis_url()
    if not url:
        return None
    if _CLIENT is None:
        _CLIENT = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=2, decode_responses=True)
    return _CLIENT


def ping() -> bool:
    r = client()
    if r is None:
        return False
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False


def key(*parts: str) -> str:
    return ":".join(str(p).strip().replace(":", "_") for p in parts if str(p).strip())


def acquire_lock(name: str, ttl_seconds: int = 30, wait_seconds: float = 2.0) -> str | None:
    """Lock por conversación. La base de datos es SIEMPRE la exclusión común: así un worker
    que ve Redis caído y otro que lo ve disponible no procesan a la vez. Redis, si responde,
    se toma además (compatibilidad con despliegues que lo vigilan). None = no se obtuvo
    exclusión (contención o base no disponible): el llamador no debe procesar."""
    from . import db_lock
    try:
        db_token = db_lock.acquire(name, ttl_seconds, wait_seconds)
    except Exception:  # noqa: BLE001 - sin base no hay exclusión verificable
        return None
    if not db_token:
        return None
    redis_token = ""
    r = client()
    if r is not None:
        candidate = secrets.token_urlsafe(18)
        try:
            if not r.set(name, candidate, nx=True, ex=ttl_seconds):
                db_lock.release(name, db_token)
                return None
            redis_token = candidate
        except (redis.RedisError, OSError):
            redis_token = ""  # Redis caído: la base ya da la exclusión
    return f"{db_token}|{redis_token}"


def renew_lock(name: str, token: str | None, ttl_seconds: int) -> bool:
    """Renueva el lease común en base (obligatorio) y el de Redis si lo hay (best-effort)."""
    if not token:
        return False
    db_token, _, redis_token = token.partition("|")
    try:
        from . import db_lock
        if not db_lock.renew(name, db_token, ttl_seconds):
            return False
    except Exception:  # noqa: BLE001 - sin base no se puede afirmar la propiedad
        return False
    r = client()
    if r is not None and redis_token:
        try:
            r.eval(_RENEW_LOCK, 1, name, redis_token, ttl_seconds)
        except redis.RedisError:
            pass
    return True


def still_held(name: str, token: str | None) -> bool:
    """El lease sigue siendo nuestro (no venció ni lo tomó otro proceso)."""
    if not token:
        return False
    try:
        from . import db_lock
        return db_lock.owned(name, token.split("|", 1)[0])
    except Exception:  # noqa: BLE001
        return False


def release_lock(name: str, token: str | None) -> None:
    if not token:
        return
    db_token, _, redis_token = token.partition("|")
    try:
        from . import db_lock
        db_lock.release(name, db_token)
    except Exception:  # noqa: BLE001 - expira por TTL
        pass
    r = client()
    if r is None or not redis_token:
        return
    try:
        r.eval(_RELEASE_LOCK, 1, name, redis_token)
    except redis.RedisError:
        return
