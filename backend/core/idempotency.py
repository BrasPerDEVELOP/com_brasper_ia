"""Idempotencia y deduplicación (etapa 2 del plan de atención autónoma).

- `seen_event(scope, event_id)`: deduplica webhooks (WhatsApp `messages[].id`,
  Telegram `update_id`). La primera vez devuelve False y registra; después True.
- `remember(key, result)` / `recall(key)`: claves de idempotencia para escrituras
  (p. ej. alta de cliente): una petición repetida devuelve el resultado guardado en
  vez de volver a ejecutar la acción.
"""
from __future__ import annotations

import hashlib
import json
import os

from . import db
from .util import now_iso


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS idempotency_keys ("
            "key TEXT PRIMARY KEY, scope TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL)"
        )


def make_key(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _insert_ignore(con, key: str, scope: str, result: str | None) -> bool:
    """True si insertó (clave nueva), False si ya existía."""
    if db.is_postgres():
        cur = con.execute(
            "INSERT INTO idempotency_keys (key, scope, result, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT (key) DO NOTHING", (key, scope, result, now_iso()))
    else:
        cur = con.execute(
            "INSERT OR IGNORE INTO idempotency_keys (key, scope, result, created_at) VALUES (?,?,?,?)",
            (key, scope, result, now_iso()))
    return bool(cur.rowcount)


def seen_event(scope: str, event_id: str | None) -> bool:
    """Deduplicación de eventos externos. Sin id no se puede deduplicar -> False."""
    if not event_id:
        return False
    key = make_key("event", scope, event_id)
    try:
        with db.connect() as con:
            return not _insert_ignore(con, key, f"event:{scope}", None)
    except Exception:  # noqa: BLE001 - nunca bloquear el webhook por la tabla de dedup
        return False


def recall(key: str) -> dict | None:
    try:
        with db.connect() as con:
            row = con.execute("SELECT result FROM idempotency_keys WHERE key=?", (key,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row or not row["result"]:
        return None
    try:
        return json.loads(row["result"])
    except (ValueError, TypeError):
        return None


def remember(key: str, result: dict, scope: str = "write") -> None:
    payload = json.dumps(result, ensure_ascii=False)
    try:
        with db.connect() as con:
            if not _insert_ignore(con, key, scope, payload):
                con.execute("UPDATE idempotency_keys SET result=? WHERE key=?", (payload, key))
    except Exception:  # noqa: BLE001
        pass


def purge(older_than_hours: int | None = None) -> int:
    hours = older_than_hours or int(os.getenv("IDEMPOTENCY_TTL_HOURS", "72"))
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with db.connect() as con:
        cur = con.execute("DELETE FROM idempotency_keys WHERE created_at < ?", (cutoff,))
        return int(cur.rowcount or 0)
