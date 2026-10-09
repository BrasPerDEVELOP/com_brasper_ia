"""Almacén de eventos de canal para replay y reconciliación de ecos Coex (C5).

- `history` / `state_sync` (sincronización Coex) se guardan íntegros con estado `stored`:
  el mapeo de esos payloads depende del contrato Meta aún no confirmado (plan externo),
  así que NO se procesan; `replay()` los entrega a un mapeador cuando exista.
- Un eco (`smb_message_echoes`) que llega mientras un envío nuestro al mismo destinatario
  está en vuelo se difiere (`deferred`): al completarse el envío se compara el id del
  proveedor. Mismo id = eco propio; otro id, envío incierto o fallido = actividad humana.
  Igual texto nunca prueba que sea nuestro.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import db, util

STALE_SECONDS = 60


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS channel_events (provider TEXT NOT NULL, connection_id TEXT NOT NULL DEFAULT '', "
                    "event_id TEXT NOT NULL, kind TEXT NOT NULL, recipient TEXT, payload TEXT NOT NULL, state TEXT NOT NULL, "
                    "received_at TEXT NOT NULL, processed_at TEXT, PRIMARY KEY(provider, connection_id, event_id))")
        con.execute("CREATE INDEX IF NOT EXISTS channel_events_state ON channel_events(kind, state)")


def _event_id(payload) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def record(provider: str, connection_id: str | None, kind: str, payload: dict, *, event_id: str | None = None,
           recipient: str | None = None, state: str = "stored") -> bool:
    """Guarda el evento una sola vez; False si ya existía (reintento del proveedor)."""
    with db.connect() as con:
        return bool(con.execute(
            "INSERT INTO channel_events VALUES (?,?,?,?,?,?,?,?,NULL) "
            "ON CONFLICT(provider, connection_id, event_id) DO NOTHING",
            (provider, connection_id or "", event_id or _event_id(payload), kind, recipient,
             json.dumps(payload, ensure_ascii=False, default=str), state, util.now_iso())).rowcount)


def mark(provider: str, connection_id: str | None, event_id: str, state: str) -> None:
    with db.connect() as con:
        con.execute("UPDATE channel_events SET state=?, processed_at=? WHERE provider=? AND connection_id=? AND event_id=?",
                    (state, util.now_iso(), provider, connection_id or "", event_id))


def replay(kind: str, handler: Callable[[dict], str], limit: int = 100) -> dict:
    """Entrega eventos `stored` de un tipo a `handler` (devuelve el estado final). Un fallo del
    handler deja el evento como estaba para un replay posterior."""
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT provider, connection_id, event_id, payload FROM channel_events WHERE kind=? AND state='stored' "
            "ORDER BY received_at LIMIT ?", (kind, limit)).fetchall()]
    done = failed = 0
    for row in rows:
        try:
            state = handler(json.loads(row["payload"]))
        except Exception:  # noqa: BLE001
            failed += 1
            continue
        mark(row["provider"], row["connection_id"], row["event_id"], state or "processed")
        done += 1
    return {"processed": done, "failed": failed, "pending": len(rows) - done}


def defer_echo(connection_id: str, msg: dict) -> bool:
    return record("whatsapp", connection_id, "echo", msg, event_id=msg.get("id") or None,
                  recipient=str(msg.get("to") or ""), state="deferred")


def reconcile_echoes(connection_id: str, recipient: str, own_message_id: str | None) -> list[str]:
    """Resuelve ecos diferidos del destinatario tras completar un envío nuestro."""
    from . import coex, outbound
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT event_id, payload FROM channel_events WHERE provider='whatsapp' AND connection_id=? "
            "AND kind='echo' AND state='deferred' AND recipient=?", (connection_id, recipient)).fetchall()]
    outcomes = []
    for row in rows:
        if own_message_id and row["event_id"] == own_message_id:
            mark("whatsapp", connection_id, row["event_id"], "own_echo")
            outcomes.append("own")
            continue
        if outbound.in_flight(connection_id, recipient):
            continue  # otro envío nuestro sigue en vuelo: se decide cuando termine
        coex.apply_human_echo(connection_id, json.loads(row["payload"]))
        mark("whatsapp", connection_id, row["event_id"], "human_echo")
        outcomes.append("human")
    return outcomes


def sweep_stale_echoes() -> int:
    """Ecos diferidos cuyo envío nunca terminó (caída/reinicio): se tratan como humanos."""
    limit = (datetime.now(timezone.utc) - timedelta(seconds=STALE_SECONDS)).isoformat(timespec="seconds")
    from . import coex
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT connection_id, event_id, payload FROM channel_events WHERE kind='echo' AND state='deferred' "
            "AND received_at < ?", (limit,)).fetchall()]
        # Un envío que quedó 'pending' tras una caída pasa a incierto: nunca se reintenta solo.
        con.execute("UPDATE outbound_messages SET state='uncertain', detail='proceso interrumpido durante el envío', "
                    "updated_at=? WHERE state='pending' AND created_at < ?", (util.now_iso(), limit))
    for row in rows:
        coex.apply_human_echo(row["connection_id"], json.loads(row["payload"]))
        mark("whatsapp", row["connection_id"], row["event_id"], "human_echo")
    return len(rows)
