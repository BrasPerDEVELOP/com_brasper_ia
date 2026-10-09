"""Alcance de usuarios del panel, conflictos de contactos y estado de salidas (C5–C7)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import access, auth, contacts, db, outbound

router = APIRouter(prefix="/api")


class ScopeIn(BaseModel):
    channels: list[str] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)


@router.get("/admin/users")
def users(user: dict = Depends(auth.require("users:read"))):
    with db.connect() as con:
        rows = [auth._row_to_user(r) for r in con.execute("SELECT * FROM panel_users ORDER BY id").fetchall()]
    return {"users": [{**auth._public_user(u), "access_scope": access.scope_for(u)} for u in rows]}


@router.put("/admin/users/{email}/scope")
def set_scope(email: str, body: ScopeIn, user: dict = Depends(auth.require("users:write"))):
    try:
        scope = access.set_scope(email, body.model_dump())
    except KeyError as exc:
        raise HTTPException(404, "Usuario no encontrado") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add_audit_event(user.get("email"), "user.scope", f"user:{email.strip().lower()}", scope)
    return {"email": email.strip().lower(), "access_scope": scope}


@router.get("/admin/contact-conflicts")
def contact_conflicts(user: dict = Depends(auth.require("config:read"))):
    return {"conflicts": contacts.conflicts()}


@router.post("/admin/contact-conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, user: dict = Depends(auth.require("config:write"))):
    # Solo marca la revisión: la fusión de contactos no es automática.
    if not contacts.resolve_conflict(conflict_id, user.get("email")):
        raise HTTPException(404, "Conflicto no encontrado o ya revisado")
    db.add_audit_event(user.get("email"), "contact.conflict_reviewed", f"contact_conflict:{conflict_id}", {})
    return {"resolved": True}


@router.get("/conversations/{conversation_id}/deliveries")
def deliveries(conversation_id: str, user: dict = Depends(auth.require("conversations:read"))):
    from api.routes import _assert_conversation_access
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    _assert_conversation_access(user, conv)
    return {"deliveries": outbound.for_conversation(conversation_id)}
