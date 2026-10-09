"""Panel administration proxy; financial rules remain in the official API."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from core import auth, brasper_api, db, tenants, media_library

router = APIRouter(prefix="/api/admin/campaigns")


def upstream(method, suffix="", body=None):
    kwargs = {"json": body} if body is not None else {}
    result = brasper_api._integration_request(tenants.get_config(), method,
                "/brasper/ai/admin/campaigns" + suffix, admin=True, **kwargs)
    if not result.get("ok"):
        raise HTTPException(result.get("status", 503), result.get("error", "API de campañas no disponible"))
    return result["data"]


class SaveIn(BaseModel):
    draft: dict
    expected_version: int = Field(default=0, ge=0)


class PublishIn(BaseModel):
    version: int = Field(ge=1)


@router.get("")
def index(user=Depends(auth.require("config:read"))):
    return upstream("GET")


@router.get("/{campaign_id}/history")
def history(campaign_id: UUID, user=Depends(auth.require("config:read"))):
    return upstream("GET", f"/{campaign_id}/history")


@router.post("")
def create(body: SaveIn, user=Depends(auth.require("tenants:write"))):
    result = upstream("POST", body={**body.model_dump(), "actor": user["email"]})
    db.add_audit_event(user["email"], "campaign.draft", f"campaign:{result['id']}", {"version": result["version"]})
    return result


@router.put("/{campaign_id}")
def save(campaign_id: UUID, body: SaveIn, user=Depends(auth.require("tenants:write"))):
    result = upstream("PUT", f"/{campaign_id}", {**body.model_dump(), "actor": user["email"]})
    db.add_audit_event(user["email"], "campaign.draft", f"campaign:{campaign_id}", {"version": result["version"]})
    return result


@router.post("/{campaign_id}/publish")
def publish(campaign_id: UUID, body: PublishIn, user=Depends(auth.require("tenants:write"))):
    history = upstream("GET", f"/{campaign_id}/history")
    saved = next((v for v in history["versions"] if v["version"] == body.version), None)
    if not saved:
        raise HTTPException(404, "Versión no encontrada")
    for language, copy in saved["draft"]["campaign_rules"]["messages"].items():
        if copy.get("media_id") and not media_library.approved(copy["media_id"], language):
            raise HTTPException(422, f"La imagen de {language} debe estar aprobada para promociones en ese idioma")
    result = upstream("POST", f"/{campaign_id}/publish", {**body.model_dump(), "actor": user["email"]})
    db.add_audit_event(user["email"], "campaign.publish", f"campaign:{campaign_id}", body.model_dump())
    return result


@router.post("/{campaign_id}/disable")
def disable(campaign_id: UUID, user=Depends(auth.require("tenants:write"))):
    result = upstream("POST", f"/{campaign_id}/disable")
    db.add_audit_event(user["email"], "campaign.disable", f"campaign:{campaign_id}", {})
    return result
