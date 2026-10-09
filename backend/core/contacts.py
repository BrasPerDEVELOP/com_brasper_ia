"""Contacto interno separado de la identidad del proveedor (C5).

Un contacto es la persona; un alias es cómo la ve un proveedor en una conexión
(`whatsapp`/`connection_id`/`5511…` o un BSUID opaco, `telegram`/``/`tg:123`, webchat).
Reglas:
  - El teléfono es opcional y solo se registra cuando el canal lo entrega como
    teléfono (WhatsApp `from` numérico). Nunca se extraen dígitos de un ID opaco.
  - Mismo teléfono verificado por WhatsApp en dos conexiones = mismo contacto.
  - Username, nombre de perfil o datos escritos nunca vinculan.
  - Si un alias ya apunta a otro contacto distinto del que sugiere el teléfono, se
    registra un conflicto y NO se fusiona automáticamente.
"""
from __future__ import annotations

import re
import uuid

from . import db, util

_PHONE = re.compile(r"\+?[0-9]{6,15}")
_BSUID = re.compile(r"[A-Z]{2}\.(?:ENT\.)?[A-Za-z0-9]{1,128}")


def ensure_schema() -> None:
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, display_name TEXT, "
                    "phone_e164 TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        con.execute("CREATE INDEX IF NOT EXISTS contacts_phone ON contacts(phone_e164)")
        con.execute("CREATE TABLE IF NOT EXISTS contact_aliases (provider TEXT NOT NULL, "
                    "connection_id TEXT NOT NULL DEFAULT '', external_id TEXT NOT NULL, kind TEXT NOT NULL, "
                    "contact_id TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "PRIMARY KEY(provider, connection_id, external_id))")
        con.execute("CREATE INDEX IF NOT EXISTS contact_aliases_contact ON contact_aliases(contact_id)")
        con.execute("CREATE TABLE IF NOT EXISTS contact_conflicts (id TEXT PRIMARY KEY, provider TEXT NOT NULL, "
                    "connection_id TEXT NOT NULL, external_id TEXT NOT NULL, existing_contact_id TEXT NOT NULL, "
                    "proposed_contact_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "resolved_at TEXT, resolved_by TEXT)")
    if not db.has_column("conversations", "contact_id"):
        with db.connect() as con:
            con.execute("ALTER TABLE conversations ADD COLUMN contact_id TEXT")
        db.has_column.cache_clear()


def classify(provider: str, external_id: str) -> tuple[str, str | None]:
    """(kind, teléfono E.164 o None). Solo WhatsApp numérico es teléfono."""
    ref = (external_id or "").strip()
    if provider == "whatsapp" and _PHONE.fullmatch(ref):
        return "phone", "+" + ref.lstrip("+")
    if provider == "whatsapp" and _BSUID.fullmatch(ref):
        return "opaque", None
    if provider == "telegram":
        return "chat", None
    return "session", None


def split_user_ref(channel: str, user_ref: str) -> tuple[str, str]:
    """`wa:5511…` -> ("whatsapp", "5511…"); otros canales conservan la referencia completa."""
    if channel == "whatsapp" and user_ref.startswith("wa:"):
        return "whatsapp", user_ref[3:]
    return channel, user_ref


def _alias(con, provider: str, connection_id: str, external_id: str):
    return con.execute("SELECT contact_id FROM contact_aliases WHERE provider=? AND connection_id=? "
                       "AND external_id=?", (provider, connection_id, external_id)).fetchone()


def _conflict(con, provider, connection_id, external_id, existing, proposed, reason) -> None:
    if existing == proposed:
        return
    dup = con.execute("SELECT 1 FROM contact_conflicts WHERE provider=? AND connection_id=? AND external_id=? "
                      "AND existing_contact_id=? AND proposed_contact_id=? AND resolved_at IS NULL",
                      (provider, connection_id, external_id, existing, proposed)).fetchone()
    if not dup:
        con.execute("INSERT INTO contact_conflicts VALUES (?,?,?,?,?,?,?,?,NULL,NULL)",
                    (uuid.uuid4().hex, provider, connection_id, external_id, existing, proposed, reason,
                     util.now_iso()))


def resolve(provider: str, connection_id: str | None, external_id: str, *,
            phone_hint: str | None = None, display_name: str | None = None) -> str:
    """Contacto del alias; lo crea si no existe. Concurrente: el alias es la clave única,
    así que dos webhooks simultáneos terminan en el mismo contacto.

    `phone_hint`: teléfono que el MISMO evento del proveedor entrega junto a un ID opaco
    (p. ej. WhatsApp con BSUID y `from`). Nunca un dato escrito por el cliente."""
    conn = connection_id or ""
    kind, phone = classify(provider, external_id)
    if phone is None and phone_hint and provider == "whatsapp" and _PHONE.fullmatch(phone_hint):
        phone = "+" + phone_hint.lstrip("+")
    now = util.now_iso()
    with db.connect() as con:
        row = _alias(con, provider, conn, external_id)
        by_phone = (con.execute("SELECT id FROM contacts WHERE phone_e164=? ORDER BY created_at LIMIT 1",
                                (phone,)).fetchone() if phone else None)
        if row:
            contact_id = row["contact_id"]
            if by_phone and by_phone["id"] != contact_id:
                _conflict(con, provider, conn, external_id, contact_id, by_phone["id"], "phone_matches_other_contact")
            elif phone and not by_phone:
                con.execute("UPDATE contacts SET phone_e164=?, updated_at=? WHERE id=? AND phone_e164 IS NULL",
                            (phone, now, contact_id))
            return contact_id
        contact_id = by_phone["id"] if by_phone else uuid.uuid4().hex
        inserted = con.execute("INSERT INTO contact_aliases VALUES (?,?,?,?,?,?) "
                               "ON CONFLICT(provider, connection_id, external_id) DO NOTHING",
                               (provider, conn, external_id, kind, contact_id, now)).rowcount
        if not inserted:  # otro proceso creó el alias entre la lectura y la escritura
            return _alias(con, provider, conn, external_id)["contact_id"]
        if not by_phone:
            con.execute("INSERT INTO contacts VALUES (?,?,?,?,?)",
                        (contact_id, (display_name or "")[:120] or None, phone, now, now))
        return contact_id


def attach(conversation_id: str, contact_id: str) -> None:
    with db.connect() as con:
        con.execute("UPDATE conversations SET contact_id=? WHERE id=? AND contact_id IS NULL",
                    (contact_id, conversation_id))


def backfill(limit: int = 5000) -> int:
    """Asigna contacto a conversaciones históricas sin contacto. Idempotente; agrupa solo por
    alias exacto (y teléfono WhatsApp verificado), nunca por nombre ni datos de lead."""
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, channel, user_ref, connection_id FROM conversations WHERE contact_id IS NULL "
            "ORDER BY started_at LIMIT ?", (limit,)).fetchall()]
    for row in rows:
        provider, external = split_user_ref(row["channel"], row["user_ref"] or "")
        if not external:
            continue
        attach(row["id"], resolve(provider, row.get("connection_id"), external))
    return len(rows)


def conflicts(open_only: bool = True) -> list[dict]:
    with db.connect() as con:
        sql = "SELECT * FROM contact_conflicts" + (" WHERE resolved_at IS NULL" if open_only else "")
        return [dict(r) for r in con.execute(sql + " ORDER BY created_at DESC LIMIT 200").fetchall()]


def resolve_conflict(conflict_id: str, actor: str) -> bool:
    """Marca un conflicto como revisado. La fusión de contactos es una acción humana aparte."""
    with db.connect() as con:
        return bool(con.execute("UPDATE contact_conflicts SET resolved_at=?, resolved_by=? "
                                "WHERE id=? AND resolved_at IS NULL", (util.now_iso(), actor, conflict_id)).rowcount)
