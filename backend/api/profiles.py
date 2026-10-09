"""Authenticated management of assistant style profiles."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import agent_profiles as profiles, auth, db

router = APIRouter(prefix="/api/admin/agent-profiles")


class SaveIn(BaseModel):
    profile: profiles.Profile
    expected_version: int = Field(default=0, ge=0)


class PublishIn(BaseModel):
    version: int = Field(gt=0)


@router.get("")
def index(user: dict = Depends(auth.require("config:read"))):
    return {"profiles": profiles.inventory()}


@router.get("/{profile_id}/history")
def history(profile_id: str, user: dict = Depends(auth.require("config:read"))):
    return {"versions": profiles.history(profile_id)}


@router.put("/{profile_id}")
def save(profile_id: str, body: SaveIn, user: dict = Depends(auth.require("tenants:write"))):
    try:
        result = profiles.save(profile_id, body.profile, body.expected_version, user["email"])
    except profiles.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add_audit_event(user["email"], "agent_profile.draft", f"profile:{profile_id}", {"version": result["version"]})
    return result


@router.post("/{profile_id}/publish")
def publish(profile_id: str, body: PublishIn, user: dict = Depends(auth.require("tenants:write"))):
    try:
        profiles.publish(profile_id, body.version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.add_audit_event(user["email"], "agent_profile.publish", f"profile:{profile_id}", {"version": body.version})
    return {"ok": True}


@router.post("/{profile_id}/disable")
def disable(profile_id: str, user: dict = Depends(auth.require("tenants:write"))):
    try:
        profiles.disable(profile_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.add_audit_event(user["email"], "agent_profile.disable", f"profile:{profile_id}", {})
    return {"ok": True}
