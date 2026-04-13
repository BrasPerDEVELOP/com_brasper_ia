import os

import redis
from dotenv import load_dotenv
from redis.backoff import NoBackoff
from redis.retry import Retry

load_dotenv()


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def redis_from_env() -> redis.Redis:
    """Cliente Redis según REDIS_* en `.env` (por defecto localhost:6379)."""
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db = int(os.getenv("REDIS_DB", "0"))
    password = os.getenv("REDIS_PASSWORD")
    if password is not None and password.strip() == "":
        password = None
    username = os.getenv("REDIS_USERNAME")
    if username is not None and username.strip() == "":
        username = None
    ssl = _truthy(os.getenv("REDIS_SSL"))
    # Sin timeouts, un Redis caído puede bloquear el hilo del chat durante minutos.
    connect_timeout = _float_env("REDIS_SOCKET_CONNECT_TIMEOUT", 5.0)
    socket_timeout = _float_env("REDIS_SOCKET_TIMEOUT", 5.0)
    # redis-py 5 reintenta conexiones 3× con backoff exponencial por defecto;
    # sin esto, un Redis caído puede tardar decenas de segundos antes de fallar.
    retry = Retry(NoBackoff(), 0)

    kwargs: dict = {
        "host": host,
        "port": port,
        "db": db,
        "decode_responses": True,
        "ssl": ssl,
        "socket_connect_timeout": connect_timeout,
        "socket_timeout": socket_timeout,
        "retry": retry,
    }
    if password is not None:
        kwargs["password"] = password
    if username is not None:
        kwargs["username"] = username
    return redis.Redis(**kwargs)
