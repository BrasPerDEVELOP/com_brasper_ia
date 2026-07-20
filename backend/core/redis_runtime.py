"""Conexion Redis de runtime para health, locks y colas livianas."""
import os
import secrets
import time

import redis

_CLIENT = None
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
    r = client()
    if r is None:
        return "local-no-redis"
    token = secrets.token_urlsafe(18)
    deadline = time.time() + wait_seconds
    while True:
        try:
            if r.set(name, token, nx=True, ex=ttl_seconds):
                return token
        except (redis.RedisError, OSError):
            # Redis caído/inalcanzable: el lock es opcional -> degradar a "sin lock"
            # (procesar el mensaje) en vez de bloquear la conversación como "ocupada".
            return "local-no-redis"
        if time.time() >= deadline:
            return None  # lock realmente en contención (otro proceso lo tiene)
        time.sleep(0.05)


def release_lock(name: str, token: str | None) -> None:
    if not token or token == "local-no-redis":
        return
    r = client()
    if r is None:
        return
    try:
        r.eval(_RELEASE_LOCK, 1, name, token)
    except redis.RedisError:
        return
