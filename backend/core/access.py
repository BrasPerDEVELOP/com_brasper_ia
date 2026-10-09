"""Alcance de cada usuario del panel por canal, conexión (número) y sector (C6/C7).

`panel_users.access_scope` (JSON) = {"channels": [...], "connections": [...], "sectors": [...]}.
Lista vacía o ausente = sin restricción en esa dimensión (compatibilidad con usuarios
existentes). Un sector es la etiqueta `sector:<nombre>` de la conversación. Owner ignora
el alcance. El frontend oculto nunca es autorización: todo se valida aquí.

Medios privados del cliente (comprobantes, documentos, audios enviados por el canal) además
exigen el permiso `media:private`.
"""
from __future__ import annotations

import json

from fastapi import HTTPException

from . import auth, db

DIMENSIONS = ("channels", "connections", "sectors")
_CHANNELS = {"whatsapp", "telegram", "webchat"}


def ensure_schema() -> None:
    auth.ensure_schema()
    db.has_column.cache_clear()
    if not db.has_column("panel_users", "access_scope"):
        with db.connect() as con:
            con.execute("ALTER TABLE panel_users ADD COLUMN access_scope TEXT")
        db.has_column.cache_clear()


def normalize(scope: dict | None) -> dict:
    scope = scope or {}
    out = {}
    for dim in DIMENSIONS:
        values = scope.get(dim) or []
        if not isinstance(values, list) or not all(isinstance(v, str) and 0 < len(v) <= 80 for v in values):
            raise ValueError(f"{dim} debe ser una lista de textos")
        if dim == "channels" and set(values) - _CHANNELS:
            raise ValueError("Canal no válido")
        out[dim] = sorted({v.strip().lower() if dim != "connections" else v.strip() for v in values})
    return out


def scope_for(user: dict | None) -> dict:
    if not user or user.get("role") == "owner":
        return normalize(None)
    raw = user.get("access_scope")
    if raw is None and user.get("email"):
        found = auth.user_from_email(user["email"]) or {}
        raw = found.get("access_scope")
    try:
        return normalize(json.loads(raw) if isinstance(raw, str) and raw else raw)
    except (ValueError, TypeError):
        # Alcance corrupto: se cierra (sin acceso) en vez de abrir todo.
        return {"channels": ["__none__"], "connections": [], "sectors": []}


def set_scope(email: str, scope: dict) -> dict:
    clean = normalize(scope)
    with db.connect() as con:
        if not con.execute("UPDATE panel_users SET access_scope=? WHERE email=?",
                           (json.dumps(clean), email.strip().lower())).rowcount:
            raise KeyError(email)
    return clean


def conversation_allowed(user: dict, conv: dict) -> bool:
    scope = scope_for(user)
    if scope["channels"] and conv.get("channel") not in scope["channels"]:
        return False
    if scope["connections"] and conv.get("channel") == "whatsapp" and conv.get("connection_id") not in scope["connections"]:
        return False
    if scope["sectors"]:
        tags = set(db.tags_for(conv["id"]))
        if not tags & {f"sector:{s}" for s in scope["sectors"]}:
            return False
    return True


def assert_conversation(user: dict, conv: dict) -> None:
    if not conversation_allowed(user, conv):
        raise HTTPException(status_code=403, detail="Conversación fuera de tu alcance (canal, número o sector)")


def sql_filter(user: dict) -> tuple[str, list]:
    """Condición SQL equivalente para listar conversaciones (alias `c`)."""
    scope = scope_for(user)
    where, args = "", []
    if scope["channels"]:
        where += f" AND c.channel IN ({','.join('?' * len(scope['channels']))})"
        args += scope["channels"]
    if scope["connections"]:
        where += (f" AND (c.channel<>'whatsapp' OR c.connection_id IN "
                  f"({','.join('?' * len(scope['connections']))}))")
        args += scope["connections"]
    if scope["sectors"]:
        where += (" AND EXISTS (SELECT 1 FROM conversation_tags st WHERE st.conversation_id=c.id AND st.tag IN "
                  f"({','.join('?' * len(scope['sectors']))}))")
        args += [f"sector:{s}" for s in scope["sectors"]]
    return where, args


def is_private_media(message: dict) -> bool:
    """Lo que envió el cliente por el canal (comprobante, documento, audio) es privado; las
    imágenes aprobadas de la biblioteca comercial no."""
    media = message.get("media") or {}
    return message.get("role") == "user" and media.get("provider") in {"telegram", "whatsapp"}


def assert_private_media(user: dict) -> None:
    if not auth.has_perm(user, "media:private"):
        raise HTTPException(status_code=403, detail="Sin permiso para ver adjuntos privados del cliente")
