"""Gestión de usuarios del panel (solo owner): alta, edición, desactivación, contraseñas y sesiones.

Reglas que se validan aquí (el frontend nunca autoriza):
  - El último owner ACTIVO no se puede desactivar ni degradar de rol. La comprobación y el
    cambio van en un único UPDATE condicional dentro de una transacción que bloquea a los
    owners activos (`FOR UPDATE` en Postgres, `BEGIN IMMEDIATE` en SQLite): dos peticiones
    concurrentes no pueden dejar el panel sin owner.
  - No hay borrado físico de cuentas: se desactivan (la auditoría y las asignaciones
    históricas siguen apuntando a un usuario existente).
  - Desactivar, resetear la contraseña o "cerrar sesiones" revoca todas las sesiones e
    invalida el token estático al instante.
  - Cada cambio queda en `audit_events` sin contraseñas, hashes ni tokens.
"""
from __future__ import annotations

import re

from . import access, auth, db
from .util import normalize_email, now_iso

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}$")


class LastOwnerError(Exception):
    """La operación dejaría el panel sin owner activo."""


class ConflictError(Exception):
    """El usuario ya existe."""


def _email(email: str | None) -> str:
    value = normalize_email(email)
    if not _EMAIL_RE.match(value):
        raise ValueError("Correo no válido")
    return value


def _role(role: str | None) -> str:
    if role not in auth.ROLE_PERMS:
        raise ValueError(f"Rol no válido. Opciones: {', '.join(auth.ROLE_PERMS)}")
    return role


def _name(name: str | None) -> str:
    clean = "".join(ch for ch in (name or "") if ch.isprintable()).strip()[:80]
    if not clean:
        raise ValueError("El nombre es obligatorio")
    return clean


def _target(email: str) -> dict:
    user = auth.user_from_email(email)
    if not user:
        raise KeyError(email)
    return user


def _audit(actor: dict, action: str, email: str, metadata: dict) -> None:
    db.add_audit_event(actor.get("email"), action, f"user:{email}", metadata)


def public(user: dict, sessions: dict[int, int] | None = None) -> dict:
    counts = sessions if sessions is not None else auth.active_session_counts()
    return {**auth._public_user(user), "access_scope": access.scope_for(user),
            "active_sessions": counts.get(int(user["id"]), 0)}


def list_users() -> list[dict]:
    with db.connect() as con:
        rows = [auth._row_to_user(r) for r in con.execute("SELECT * FROM panel_users ORDER BY id").fetchall()]
    counts = auth.active_session_counts()
    return [public(u, counts) for u in rows]


def _guarded_update(user_id: int, set_sql: str, args: tuple, after=None) -> bool:
    """UPDATE que nunca deja el panel sin owner activo (atómico y serializado).

    Devuelve False si el usuario es el último owner activo y el cambio lo quitaría."""
    with db.connect() as con:
        if db.is_postgres():
            con.execute("SELECT id FROM panel_users WHERE role='owner' AND active=1 FOR UPDATE").fetchall()
        else:
            con.execute("BEGIN IMMEDIATE")
        cur = con.execute(
            f"UPDATE panel_users SET {set_sql} WHERE id=? AND (role<>'owner' OR active=0 OR EXISTS "
            "(SELECT 1 FROM panel_users o WHERE o.role='owner' AND o.active=1 AND o.id<>?))",
            (*args, user_id, user_id))
        if cur.rowcount != 1:
            return False
        if after:
            after(con)
    return True


def create(actor: dict, email: str, name: str, role: str, scope: dict | None = None,
           password: str | None = None) -> tuple[dict, str | None]:
    """Alta. Sin `password` genera una temporal (se devuelve UNA vez). En ambos casos el
    usuario debe cambiarla al entrar, porque el owner la conoce."""
    email, name, role = _email(email), _name(name), _role(role)
    clean_scope = access.normalize(scope)
    temporary = None
    if password:
        auth.validate_new_password(password, email)
    else:
        temporary = password = auth.generate_temporary_password()
    if auth.user_from_email(email):
        raise ConflictError(email)
    try:
        auth.create_user(email, name, role, password=password, must_change_password=True)
    except Exception as exc:  # noqa: BLE001 - alta concurrente del mismo correo
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ConflictError(email) from exc
        raise
    access.set_scope(email, clean_scope)
    _audit(actor, "user.create", email, {"role": role, "name": name, "access_scope": clean_scope,
                                         "password": "generated" if temporary else "set_by_owner"})
    return public(_target(email)), temporary


def update(actor: dict, email: str, name: str | None = None, role: str | None = None,
           scope: dict | None = None) -> dict:
    target = _target(normalize_email(email))
    email = target["email"]
    changes: dict = {}
    clean_scope = access.normalize(scope) if scope is not None else None
    if name is not None and _name(name) != target["name"]:
        changes["name"] = {"from": target["name"], "to": _name(name)}
    if role is not None and _role(role) != target["role"]:
        changes["role"] = {"from": target["role"], "to": role}
    if "role" in changes:
        if not _guarded_update(target["id"], "role=?", (role,)):
            raise LastOwnerError(email)
    if "name" in changes:
        with db.connect() as con:
            con.execute("UPDATE panel_users SET name=? WHERE id=?", (changes["name"]["to"], target["id"]))
    if clean_scope is not None and clean_scope != access.scope_for({**target, "role": "agent"}):
        access.set_scope(email, clean_scope)
        changes["access_scope"] = clean_scope
    if changes:
        _audit(actor, "user.update", email, {"changes": changes})
    return public(_target(email))


def set_active(actor: dict, email: str, active: bool) -> dict:
    target = _target(normalize_email(email))
    email = target["email"]
    if not active:
        if email == normalize_email(actor.get("email")):
            raise ValueError("No puedes desactivar tu propia cuenta")
        revoked = {"n": 0}

        def _revoke(con):
            revoked["n"] = auth.revoke_user_sessions(con, target["id"])

        if not _guarded_update(target["id"], "active=0, deactivated_at=?, token=?",
                               (now_iso(), auth._disabled_token()), after=_revoke):
            raise LastOwnerError(email)
        _audit(actor, "user.deactivate", email, {"sessions_revoked": revoked["n"]})
    else:
        with db.connect() as con:
            con.execute("UPDATE panel_users SET active=1, deactivated_at=NULL WHERE id=?", (target["id"],))
        _audit(actor, "user.reactivate", email, {})
    return public(_target(email))


def reset_password(actor: dict, email: str, password: str | None = None) -> tuple[dict, str | None]:
    """Contraseña temporal fijada por el owner: obliga a cambiarla y cierra todas las sesiones."""
    target = _target(normalize_email(email))
    email = target["email"]
    if email == normalize_email(actor.get("email")):
        raise ValueError("Para tu propia cuenta usa «Cambiar mi contraseña»")
    temporary = None
    if password:
        auth.validate_new_password(password, email)
    else:
        temporary = password = auth.generate_temporary_password()
    auth.set_password(target["id"], password, must_change=True)
    _audit(actor, "user.password_reset", email, {"password": "generated" if temporary else "set_by_owner",
                                                 "sessions_revoked": True})
    return public(_target(email)), temporary


def revoke_sessions(actor: dict, email: str) -> int:
    """"Cerrar sesiones": revoca todas las sesiones e invalida el token estático."""
    target = _target(normalize_email(email))
    with db.connect() as con:
        count = auth.revoke_user_sessions(con, target["id"])
        con.execute("UPDATE panel_users SET token=? WHERE id=?", (auth._disabled_token(), target["id"]))
    _audit(actor, "user.sessions_revoked", target["email"], {"sessions": count})
    return count
