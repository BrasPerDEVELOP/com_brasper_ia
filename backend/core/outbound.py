"""Registro de salidas automáticas: pendiente -> enviado | cancelado | incierto | fallido (C5).

- `cancelled`: la autorización cambió (humano intervino, conversación cerrada) justo antes
  de llamar al proveedor; no salió nada.
- `uncertain`: excepción, timeout o 5xx: el proveedor pudo haberlo aceptado. Nunca se
  reintenta automáticamente (riesgo de duplicado); queda visible para el asesor.
- `failed`: el proveedor lo rechazó explícitamente (4xx).
- Los estados de entrega del proveedor (delivered/read) solo avanzan: un evento atrasado
  no retrocede el estado.

Límite inevitable: un envío ya aceptado por el proveedor no se puede retirar si el humano
interviene después de la llamada; queda registrado como `sent`.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Awaitable, Callable

from . import db, observability, util

_RANK = {"pending": 0, "sent": 1, "delivered": 2, "read": 3}
_FINAL_FAILURES = {"failed", "cancelled", "uncertain"}


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS outbound_messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
                    "channel TEXT NOT NULL, connection_id TEXT NOT NULL DEFAULT '', recipient TEXT NOT NULL, "
                    "kind TEXT NOT NULL, human_revision INTEGER, text_sha256 TEXT, state TEXT NOT NULL, "
                    "provider_message_id TEXT, detail TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        con.execute("CREATE INDEX IF NOT EXISTS outbound_provider ON outbound_messages(connection_id, provider_message_id)")
        con.execute("CREATE INDEX IF NOT EXISTS outbound_inflight ON outbound_messages(connection_id, recipient, state)")


def _set(oid: str, state: str, detail: str | None = None, message_id: str | None = None) -> None:
    with db.connect() as con:
        con.execute("UPDATE outbound_messages SET state=?, detail=?, provider_message_id=COALESCE(?, provider_message_id), "
                    "updated_at=? WHERE id=?", (state, detail, message_id, util.now_iso(), oid))


def _outcome(channel: str, result) -> tuple[str, str | None, str | None]:
    if not isinstance(result, dict):
        return "uncertain", "respuesta no verificable", None
    if channel == "telegram":
        if result.get("ok"):
            mid = (result.get("result") or {}).get("message_id")
            return "sent", None, str(mid) if mid is not None else None
        code = result.get("error_code")
        return ("failed" if isinstance(code, int) and 400 <= code < 500 else "uncertain"), str(result.get("description") or "")[:160], None
    if result.get("sent"):
        return "sent", None, result.get("message_id")
    status = result.get("status")
    if isinstance(status, int) and 400 <= status < 500:
        return "failed", str(result.get("detail") or "")[:160], None
    return "uncertain", str(result.get("detail") or result.get("reason") or "")[:160], None


async def deliver(out: dict, channel: str, recipient: str, send: Callable[[], Awaitable[dict]], *,
                  connection_id: str | None = None, kind: str = "text", text: str = "") -> dict:
    """Envía si sigue autorizado JUSTO antes de llamar al proveedor y registra el resultado."""
    from . import engine
    from .lease import guard
    guard()  # sin exclusión vigente no se inicia un envío automático
    oid = uuid.uuid4().hex
    now = util.now_iso()
    with db.connect() as con:
        con.execute("INSERT INTO outbound_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (oid, out.get("conversation_id") or "", channel, connection_id or "", str(recipient), kind,
                     out.get("human_revision"), hashlib.sha256(text.encode()).hexdigest() if text else None,
                     "pending", None, None, now, now))
    if not engine.delivery_allowed(out):
        _set(oid, "cancelled", "intervención humana o conversación cerrada antes del envío")
        _after(connection_id, recipient, None)
        return {"sent": False, "state": "cancelled", "outbound_id": oid}
    try:
        result = await send()
    except Exception as exc:  # noqa: BLE001
        _set(oid, "uncertain", type(exc).__name__)
        observability.event("outbound.uncertain", conversation_id=out.get("conversation_id"), channel=channel)
        _after(connection_id, recipient, None)
        return {"sent": False, "state": "uncertain", "outbound_id": oid}
    state, detail, mid = _outcome(channel, result)
    _set(oid, state, detail, mid)
    if state != "sent":
        observability.event(f"outbound.{state}", conversation_id=out.get("conversation_id"), channel=channel)
    _after(connection_id, recipient, mid if state == "sent" else None)
    return {**(result if isinstance(result, dict) else {}), "sent": state == "sent", "state": state, "outbound_id": oid}


def _after(connection_id, recipient, message_id) -> None:
    if connection_id:
        from . import channel_events
        channel_events.reconcile_echoes(connection_id, str(recipient), message_id)


def in_flight(connection_id: str, recipient: str) -> bool:
    with db.connect() as con:
        return bool(con.execute("SELECT 1 FROM outbound_messages WHERE connection_id=? AND recipient=? AND state='pending'",
                                (connection_id, recipient)).fetchone())


def apply_status(connection_id: str | None, message_id: str | None, status: str | None) -> bool:
    """Estado de entrega del proveedor; solo avanza (fuera de orden no retrocede)."""
    if not message_id or not status:
        return False
    with db.connect() as con:
        row = con.execute("SELECT id, state FROM outbound_messages WHERE connection_id=? AND provider_message_id=?",
                          (connection_id or "", message_id)).fetchone()
        if not row:
            return False
        current = row["state"]
        if status == "failed":
            if current in {"sent", "pending"}:
                con.execute("UPDATE outbound_messages SET state='failed', detail='proveedor informó fallo', updated_at=? "
                            "WHERE id=?", (util.now_iso(), row["id"]))
                return True
            return False
        if current in _FINAL_FAILURES or _RANK.get(status, -1) <= _RANK.get(current, -1):
            return False
        con.execute("UPDATE outbound_messages SET state=?, updated_at=? WHERE id=?", (status, util.now_iso(), row["id"]))
        return True


def for_conversation(conversation_id: str, limit: int = 50) -> list[dict]:
    with db.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, channel, kind, state, detail, provider_message_id, created_at, updated_at "
            "FROM outbound_messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit)).fetchall()]
