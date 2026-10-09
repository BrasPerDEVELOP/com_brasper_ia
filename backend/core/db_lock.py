"""Lock por conversación en la base de datos cuando Redis no está disponible.

Sin este respaldo, una caída de Redis dejaba procesar en paralelo dos mensajes de la
misma conversación (respuestas duplicadas o cruzadas). El lock expira solo (TTL) por si
el proceso que lo tenía muere.
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone

from . import db

PREFIX = "db:"


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS conversation_locks (name TEXT PRIMARY KEY, token TEXT NOT NULL, "
                    "expires_at TEXT NOT NULL)")


def acquire(name: str, ttl_seconds: int = 30, wait_seconds: float = 2.0) -> str | None:
    token = secrets.token_urlsafe(18)
    deadline = time.time() + wait_seconds
    while True:
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(seconds=ttl_seconds)).isoformat()
        with db.connect() as con:
            taken = con.execute(
                "INSERT INTO conversation_locks(name, token, expires_at) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET token=excluded.token, expires_at=excluded.expires_at "
                "WHERE conversation_locks.expires_at < ?", (name, token, expiry, now.isoformat())).rowcount
        if taken:
            return PREFIX + token
        if time.time() >= deadline:
            return None
        time.sleep(0.05)


def release(name: str, token: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM conversation_locks WHERE name=? AND token=?", (name, token[len(PREFIX):]))


def owned(name: str, token: str) -> bool:
    if not token.startswith(PREFIX):
        return False
    with db.connect() as con:
        row = con.execute("SELECT expires_at FROM conversation_locks WHERE name=? AND token=?",
                          (name, token[len(PREFIX):])).fetchone()
    return bool(row) and dict(row)["expires_at"] > datetime.now(timezone.utc).isoformat()


def renew(name: str, token: str, ttl_seconds: int) -> bool:
    """Extiende el lease solo si sigue siendo nuestro y no venció (nadie pudo tomarlo)."""
    if not token.startswith(PREFIX):
        return False
    now = datetime.now(timezone.utc)
    with db.connect() as con:
        return bool(con.execute(
            "UPDATE conversation_locks SET expires_at=? WHERE name=? AND token=? AND expires_at > ?",
            ((now + timedelta(seconds=ttl_seconds)).isoformat(), name, token[len(PREFIX):], now.isoformat())).rowcount)

