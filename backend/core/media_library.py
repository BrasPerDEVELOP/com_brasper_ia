"""Approved, versioned public marketing images. Receipts never enter this library."""
import base64
import hashlib
import io
import json
import re
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from . import db, idempotency, observability
from .util import now_iso

MAX_BYTES = 5 * 1024 * 1024


class Conflict(ValueError):
    pass


class Asset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    purpose: Literal["promotion", "instructions", "official_accounts"]
    language: Literal["es", "pt"]
    description: str = Field(default="", max_length=1000)


def ensure_schema():
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS media_library (id TEXT PRIMARY KEY, latest_version INTEGER NOT NULL, "
                    "published_version INTEGER, enabled INTEGER NOT NULL DEFAULT 0)")
        con.execute("CREATE TABLE IF NOT EXISTS media_library_versions (asset_id TEXT NOT NULL, version INTEGER NOT NULL, "
                    "payload TEXT NOT NULL, image_base64 TEXT NOT NULL, mime TEXT NOT NULL, sha256 TEXT NOT NULL, "
                    "author TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(asset_id, version))")


def verify_image(content: bytes):
    if not content or len(content) > MAX_BYTES:
        raise ValueError("Usa una imagen PNG o JPEG de hasta 5 MB")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG"} or image.width * image.height > 16_000_000 or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Usa PNG o JPEG estático de hasta 16 megapíxeles")
            mime = "image/png" if image.format == "PNG" else "image/jpeg"
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("La imagen no es válida") from exc
    return mime


def get(asset_id, version, *, include_image=False):
    with db.connect() as con:
        row = con.execute("SELECT * FROM media_library_versions WHERE asset_id=? AND version=?", (asset_id, version)).fetchone()
    if not row:
        raise KeyError("Imagen no encontrada")
    result = dict(row)
    result["asset"] = json.loads(result.pop("payload"))
    if not include_image:
        result.pop("image_base64")
    return result


def inventory():
    with db.connect() as con:
        rows = con.execute("SELECT * FROM media_library ORDER BY id").fetchall()
    return [{**dict(r), "latest": get(r["id"], r["latest_version"]),
             "published": get(r["id"], r["published_version"]) if r["enabled"] and r["published_version"] else None}
            for r in rows]


def history(asset_id):
    with db.connect() as con:
        rows = con.execute("SELECT version FROM media_library_versions WHERE asset_id=? ORDER BY version DESC", (asset_id,)).fetchall()
    return [get(asset_id, row["version"]) for row in rows]


def save(asset_id, asset, image, expected_version, actor):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", asset_id):
        raise ValueError("Identificador no válido")
    mime = verify_image(image)
    version = expected_version + 1
    with db.connect() as con:
        con.execute("INSERT INTO media_library(id,latest_version) VALUES (?,0) ON CONFLICT(id) DO NOTHING", (asset_id,))
        updated = con.execute("UPDATE media_library SET latest_version=? WHERE id=? AND latest_version=?", (version, asset_id, expected_version))
        if updated.rowcount != 1:
            raise Conflict("La imagen cambió; recarga antes de guardar")
        con.execute("INSERT INTO media_library_versions VALUES (?,?,?,?,?,?,?,?)",
                    (asset_id, version, asset.model_dump_json(), base64.b64encode(image).decode(), mime,
                     hashlib.sha256(image).hexdigest(), actor, now_iso()))
    return get(asset_id, version)


def publish(asset_id, version):
    get(asset_id, version)
    with db.connect() as con:
        con.execute("UPDATE media_library SET published_version=?,enabled=1 WHERE id=?", (version, asset_id))


def disable(asset_id):
    with db.connect() as con:
        con.execute("UPDATE media_library SET enabled=0 WHERE id=?", (asset_id,))


def approved(asset_id, language, purpose="promotion"):
    with db.connect() as con:
        row = con.execute("SELECT published_version FROM media_library WHERE id=? AND enabled=1", (asset_id,)).fetchone()
    if not row or row["published_version"] is None:
        return None
    item = get(asset_id, row["published_version"])
    return item if item["asset"]["language"] == language and item["asset"]["purpose"] == purpose else None


def campaign_banner(quote, lead, language):
    rules = quote.get("campaign_rules") or {}
    copy = (rules.get("messages") or {}).get(language)
    if not copy or not quote.get("coupon_id") or not quote.get("campaign_version"):
        return None
    key = idempotency.make_key("campaign_media", lead.get("brasper_user_id"), quote["coupon_id"], quote["campaign_version"], language)
    if idempotency.recall(key) is not None:
        return None
    asset = approved(copy.get("media_id"), language) if copy.get("media_id") else None
    return {"text": copy["text"], "asset_id": asset["asset_id"] if asset else None,
            "asset_version": asset["version"] if asset else None, "delivery_key": key, "campaign": True}


async def deliver(cid, channel, recipient, banner, connection=None):
    """At-most-once image attempt. Conditions are already included in the reply."""
    if not banner or not banner.get("campaign"):
        return
    if "human_revision" in banner:
        from . import engine
        if not engine.delivery_allowed({"conversation_id": cid, "human_revision": banner["human_revision"]}):
            return
    key = banner["delivery_key"]
    try:
        if not idempotency.claim_write(key, "campaign.media"):
            return
    except Exception:
        observability.event("campaign.media_delivery", conversation_id=cid, sent=False, reason="reservation_unavailable")
        return
    result = {"sent": False, "reason": "text_only"}
    try:
        if banner.get("asset_id"):
            item = get(banner["asset_id"], banner["asset_version"], include_image=True)
            current = approved(banner["asset_id"], item["asset"]["language"])
            if current and current["version"] == banner["asset_version"]:
                content = base64.b64decode(item["image_base64"])
                filename = item["sha256"] + (".png" if item["mime"] == "image/png" else ".jpg")
                if channel == "whatsapp":
                    from . import whatsapp
                    from . import engine
                    guard = (lambda: engine.delivery_allowed({"conversation_id": cid, "human_revision": banner["human_revision"]})) if "human_revision" in banner else None
                    result = await whatsapp.send_image_upload(str(recipient), filename, content, item["mime"], "", connection=connection, delivery_guard=guard)
                elif channel == "telegram":
                    from . import telegram
                    response = await telegram.send_file_upload(recipient, filename, content, item["mime"], "")
                    result = {"sent": bool(response.get("ok"))}
                elif channel == "webchat":
                    banner["image_url"] = f"data:{item['mime']};base64,{item['image_base64']}"
                    result = {"sent": True}
                if result.get("sent"):
                    db.add_message(cid, "assistant", "Imagen de promoción", media={"provider": "library", "kind": "image",
                                   "ref": f"{item['asset_id']}:{item['version']}", "caption": banner["text"]})
            else:
                result = {"sent": False, "reason": "approval_changed"}
    except Exception as exc:
        result = {"sent": False, "reason": type(exc).__name__}
    try:
        idempotency.complete_write(key, result)
    except Exception:
        observability.event("campaign.media_delivery", conversation_id=cid, sent=False, reason="result_unpersisted")
    observability.event("campaign.media_delivery", conversation_id=cid, **result)
