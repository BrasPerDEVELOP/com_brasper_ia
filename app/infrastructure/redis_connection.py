import os

import redis
from dotenv import load_dotenv

load_dotenv()


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


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

    kwargs: dict = {
        "host": host,
        "port": port,
        "db": db,
        "decode_responses": True,
        "ssl": ssl,
    }
    if password is not None:
        kwargs["password"] = password
    if username is not None:
        kwargs["username"] = username
    return redis.Redis(**kwargs)
