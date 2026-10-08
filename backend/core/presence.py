"""Presencia de asesores (etapa 4): heartbeat con vencimiento y estado
disponible / ocupado / ausente. La asignación automática solo considera asesores
con presencia vigente cuando la flag `presence_required` está activa.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from . import db
from .util import now_iso

STATUSES = ("available", "busy", "away")


def ttl_seconds() -> int:
    try:
        return max(15, int(os.getenv("PRESENCE_TTL_SECONDS", "90")))
    except ValueError:
        return 90


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS agent_presence ("
            "email TEXT PRIMARY KEY, status TEXT NOT NULL, last_seen TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )


def heartbeat(email: str, status: str = "available") -> dict:
    if status not in STATUSES:
        raise ValueError("status debe ser available | busy | away")
    email = (email or "").strip().lower()
    now = now_iso()
    with db.connect() as con:
        row = con.execute("SELECT email FROM agent_presence WHERE email=?", (email,)).fetchone()
        if row:
            con.execute("UPDATE agent_presence SET status=?, last_seen=?, updated_at=? WHERE email=?",
                        (status, now, now, email))
        else:
            con.execute("INSERT INTO agent_presence (email, status, last_seen, updated_at) VALUES (?,?,?,?)",
                        (email, status, now, now))
    return {"email": email, "status": status, "last_seen": now}


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def snapshot() -> dict[str, dict]:
    """Presencia efectiva por email: el estado expira a `away` si el heartbeat venció."""
    try:
        with db.connect() as con:
            rows = con.execute("SELECT * FROM agent_presence").fetchall()
    except Exception:  # noqa: BLE001 - tabla aún no creada
        return {}
    out: dict[str, dict] = {}
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds())
    for r in rows:
        d = dict(r)
        seen = _parse(d.get("last_seen"))
        fresh = bool(seen and seen >= cutoff)
        out[d["email"]] = {"status": d["status"] if fresh else "away", "last_seen": d.get("last_seen"),
                           "fresh": fresh, "declared": d["status"]}
    return out


def is_available(email: str) -> bool:
    p = snapshot().get((email or "").lower())
    return bool(p and p["status"] == "available")
