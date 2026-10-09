import base64
import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from core import auth, db, media_library as library

router = APIRouter(prefix="/api/admin/media-library")


class VersionIn(BaseModel):
    version: int = Field(ge=1)


@router.get("")
def index(user=Depends(auth.require("config:read"))):
    return {"assets": library.inventory()}


@router.get("/{asset_id}/{version}/preview")
def preview(asset_id: str, version: int, user=Depends(auth.require("config:read"))):
    try:
        item = library.get(asset_id, version, include_image=True)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(base64.b64decode(item["image_base64"]), media_type=item["mime"],
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{asset_id}/history")
def history(asset_id: str, user=Depends(auth.require("config:read"))):
    return {"versions": library.history(asset_id)}


@router.put("/{asset_id}")
async def save(asset_id: str, metadata: str = Form(...), expected_version: int = Form(0, ge=0),
               file: UploadFile = File(...), user=Depends(auth.require("tenants:write"))):
    content = await file.read(library.MAX_BYTES + 1)
    try:
        asset = library.Asset.model_validate(json.loads(metadata))
        result = library.save(asset_id, asset, content, expected_version, user["email"])
    except library.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add_audit_event(user["email"], "media_library.draft", f"media:{asset_id}", {"version": result["version"]})
    return result


@router.post("/{asset_id}/publish")
def publish(asset_id: str, body: VersionIn, user=Depends(auth.require("tenants:write"))):
    try:
        library.publish(asset_id, body.version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.add_audit_event(user["email"], "media_library.publish", f"media:{asset_id}", body.model_dump())
    return {"ok": True}


@router.post("/{asset_id}/disable")
def disable(asset_id: str, user=Depends(auth.require("tenants:write"))):
    library.disable(asset_id)
    db.add_audit_event(user["email"], "media_library.disable", f"media:{asset_id}", {})
    return {"ok": True}
