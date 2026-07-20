"""Adapter WhatsApp Cloud API por tenant (mismo patrón que app/, token por tenant)."""
import hashlib
import hmac
import os

import httpx

from . import tenants as T
from .util import env_bool

GRAPH = "https://graph.facebook.com/v21.0"


def verify_token() -> str:
    return (os.getenv("WHATSAPP_VERIFY_TOKEN") or os.getenv("WEBHOOK_VERIFY_TOKEN")
            or os.getenv("VERIFY_TOKEN") or "cauce-verify")


def app_secret() -> str | None:
    return os.getenv("WHATSAPP_APP_SECRET") or os.getenv("META_APP_SECRET")


def signature_required() -> bool:
    return env_bool("WHATSAPP_REQUIRE_SIGNATURE")


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Valida X-Hub-Signature-256 de Meta si hay secreto o se exige por env.

    En desarrollo se permite no configurar `WHATSAPP_APP_SECRET`; en producción
    debe activarse `WHATSAPP_REQUIRE_SIGNATURE=true` y definir el secreto.
    """
    secret = app_secret()
    if not secret:
        return not signature_required()
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header or "", expected)


async def send_text(tenant: dict, to: str, text: str) -> dict:
    token = T.whatsapp_token(tenant)
    pnid = T.whatsapp_phone_number_id(tenant)
    if not token or not pnid:
        return {"sent": False, "reason": f"Tenant {tenant['id']}: WhatsApp sin token/phone_number_id"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GRAPH}/{pnid}/messages", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
    ok = r.status_code == 200
    return {"sent": ok, "status": r.status_code, "detail": None if ok else r.text[:200]}


async def upload_media(tenant: dict, filename: str, content: bytes, mime: str) -> dict:
    """Sube un archivo a WhatsApp (POST /{pnid}/media) y devuelve su media_id."""
    token = T.whatsapp_token(tenant)
    pnid = T.whatsapp_phone_number_id(tenant)
    if not token or not pnid:
        return {"ok": False, "reason": f"Tenant {tenant['id']}: WhatsApp sin token/phone_number_id"}
    files = {"file": (filename or "archivo", content, mime or "application/octet-stream")}
    data = {"messaging_product": "whatsapp", "type": mime or "application/octet-stream"}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{GRAPH}/{pnid}/media", data=data, files=files,
                              headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    return {"ok": True, "id": r.json().get("id")}


async def send_image_upload(tenant: dict, to: str, filename: str, content: bytes,
                            mime: str, caption: str = "") -> dict:
    """Sube la imagen y la envía por WhatsApp usando su media_id (sin URL pública)."""
    up = await upload_media(tenant, filename, content, mime)
    if not up.get("ok"):
        return {"sent": False, "reason": up.get("detail") or up.get("reason")}
    token = T.whatsapp_token(tenant)
    pnid = T.whatsapp_phone_number_id(tenant)
    image: dict = {"id": up["id"]}
    if caption:
        image["caption"] = caption[:1024]
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual",
               "to": to, "type": "image", "image": image}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GRAPH}/{pnid}/messages", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
    ok = r.status_code == 200
    return {"sent": ok, "status": r.status_code, "detail": None if ok else r.text[:200],
            "media_id": up.get("id")}


async def send_image(tenant: dict, to: str, link: str, caption: str = "") -> dict:
    """Envía una imagen por WhatsApp Cloud API (type=image). `link` es una URL pública."""
    token = T.whatsapp_token(tenant)
    pnid = T.whatsapp_phone_number_id(tenant)
    if not token or not pnid:
        return {"sent": False, "reason": f"Tenant {tenant['id']}: WhatsApp sin token/phone_number_id"}
    image: dict = {"link": link}
    if caption:
        image["caption"] = caption[:1024]
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual",
               "to": to, "type": "image", "image": image}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GRAPH}/{pnid}/messages", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
    ok = r.status_code == 200
    return {"sent": ok, "status": r.status_code, "detail": None if ok else r.text[:200]}


def parse_incoming(body: dict) -> list[dict]:
    """Extrae mensajes de texto/audio del payload del webhook de Meta.

    Devuelve items con type='text' o type='audio' — puede venir más de uno.
    """
    out = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            pnid = value.get("metadata", {}).get("phone_number_id")
            for msg in value.get("messages", []):
                if msg.get("type") == "text":
                    out.append({
                        "type": "text",
                        "phone_number_id": pnid,
                        "from": msg.get("from"),
                        "text": msg.get("text", {}).get("body", ""),
                    })
                elif msg.get("type") == "audio":
                    audio = msg.get("audio", {}) or {}
                    out.append({
                        "type": "audio",
                        "phone_number_id": pnid,
                        "from": msg.get("from"),
                        "media_id": audio.get("id"),
                        "mime_type": audio.get("mime_type"),
                    })
                elif msg.get("type") in ("image", "document", "video", "sticker"):
                    obj = msg.get(msg["type"], {}) or {}
                    out.append({
                        "type": msg["type"],
                        "phone_number_id": pnid,
                        "from": msg.get("from"),
                        "media_id": obj.get("id"),
                        "mime_type": obj.get("mime_type"),
                        "filename": obj.get("filename"),
                        "caption": obj.get("caption"),
                    })
    return out


async def download_media(tenant: dict, media_id: str) -> tuple[bytes | None, str | None]:
    """Descarga un archivo entrante de WhatsApp por media_id (GET media -> url -> bytes)."""
    token = T.whatsapp_token(tenant)
    if not token:
        return None, None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            meta = await client.get(f"{GRAPH}/{media_id}", headers=headers)
            if meta.status_code != 200:
                return None, None
            data = meta.json()
            url = data.get("url")
            mime = data.get("mime_type") or "application/octet-stream"
            if not url:
                return None, None
            media = await client.get(url, headers=headers)
        if media.status_code != 200:
            return None, None
        return media.content, mime
    except httpx.RequestError:
        return None, None
