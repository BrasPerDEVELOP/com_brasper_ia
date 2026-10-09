from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import auth, db, engagement

router = APIRouter(prefix="/api/admin/engagement")


class SaveIn(BaseModel):
    settings: engagement.Settings
    expected_version: int = Field(ge=0)


@router.get("")
def read(user=Depends(auth.require("config:read"))):
    return {**engagement.configuration(), "metrics": engagement.metrics()}


@router.put("")
def save(body: SaveIn, user=Depends(auth.require("tenants:write"))):
    try:
        engagement.save(body.settings, body.expected_version)
    except engagement.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    db.add_audit_event(user["email"], "engagement.configure", "engagement", {"version": body.expected_version + 1})
    return engagement.configuration()
