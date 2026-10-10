"""Usuarios del panel: sesión propia (logout, cambio de contraseña) y gestión por el owner."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from core import auth, rate_limit, users

router = APIRouter(prefix="/api")


class ScopeIn(BaseModel):
    channels: list[str] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)


class UserCreateIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(max_length=80)
    role: str = Field(max_length=32)
    access_scope: ScopeIn | None = None
    password: str | None = Field(default=None, max_length=auth.MAX_PASSWORD_LENGTH)


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    role: str | None = Field(default=None, max_length=32)
    access_scope: ScopeIn | None = None


class PasswordResetIn(BaseModel):
    password: str | None = Field(default=None, max_length=auth.MAX_PASSWORD_LENGTH)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(default="", max_length=auth.MAX_PASSWORD_LENGTH)
    new_password: str = Field(max_length=auth.MAX_PASSWORD_LENGTH)


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, "Usuario no encontrado") from exc
    except users.LastOwnerError as exc:
        raise HTTPException(409, "Debe quedar al menos un owner activo: crea o activa otro owner antes") from exc
    except users.ConflictError as exc:
        raise HTTPException(409, "Ya existe un usuario con ese correo") from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ---------- sesión propia ----------
@router.get("/login/options")
def login_options():
    return auth.login_options()


@router.post("/logout")
def logout(user: dict = Depends(auth.current_user_pending_ok),
           x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")):
    return {"revoked": auth.revoke_session(x_auth_token)}


@router.post("/me/password")
def change_password(body: PasswordChangeIn, request: Request, user: dict = Depends(auth.current_user_pending_ok)):
    rate_limit.check(request, "password_change", limit=10)
    _call(auth.change_own_password, user, body.current_password, body.new_password)
    return {"changed": True, "user": auth._public_user(auth.user_from_email(user["email"]))}


# ---------- gestión (solo owner) ----------
@router.post("/admin/users")
def create_user(body: UserCreateIn, owner: dict = Depends(auth.require_owner)):
    scope = body.access_scope.model_dump() if body.access_scope else None
    user, temporary = _call(users.create, owner, body.email, body.name, body.role, scope, body.password)
    return {"user": user, "temporary_password": temporary}


@router.patch("/admin/users/{email}")
def update_user(email: str, body: UserUpdateIn, owner: dict = Depends(auth.require_owner)):
    scope = body.access_scope.model_dump() if body.access_scope else None
    return {"user": _call(users.update, owner, email, body.name, body.role, scope)}


@router.post("/admin/users/{email}/deactivate")
def deactivate_user(email: str, owner: dict = Depends(auth.require_owner)):
    return {"user": _call(users.set_active, owner, email, False)}


@router.post("/admin/users/{email}/reactivate")
def reactivate_user(email: str, owner: dict = Depends(auth.require_owner)):
    return {"user": _call(users.set_active, owner, email, True)}


@router.post("/admin/users/{email}/password-reset")
def reset_password(email: str, body: PasswordResetIn, owner: dict = Depends(auth.require_owner)):
    user, temporary = _call(users.reset_password, owner, email, body.password)
    return {"user": user, "temporary_password": temporary}


@router.post("/admin/users/{email}/revoke-sessions")
def revoke_sessions(email: str, owner: dict = Depends(auth.require_owner)):
    return {"revoked": _call(users.revoke_sessions, owner, email)}
