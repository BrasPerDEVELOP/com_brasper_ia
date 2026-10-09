"""Adapter WhatsApp Cloud API por tenant (mismo patrón que app/, token por tenant)."""
import hashlib
import hmac
import os
import re
from urllib.parse import urlparse

import httpx

from core import tenants as T
from .util import env_bool

GRAPH = "https://graph.facebook.com/" + os.getenv("WHATSAPP_GRAPH_VERSION", "v21.0")


def recipient_fields(value: str) -> dict:
    """Meta BSUID contract reviewed 2026-10-08; never strip an opaque ID."""
    if re.fullmatch(r"[A-Z]{2}\.(?:ENT\.)?[A-Za-z0-9]{1,128}", value):
        return {"recipient": value}
    if re.fullmatch(r"\+?[0-9]{6,15}", value):
        return {"to": value}
    raise ValueError("Identificador WhatsApp no válido")


def _sent_result(response, connection):
    ok = response.status_code == 200
    message_id = None
    if ok:
        messages = response.json().get("messages") or []
        message_id = messages[0].get("id") if messages else None
        conn = connection if connection is not None else T.whatsapp_connection_by_id(None)
        from . import channel_receipts
        channel_receipts.remember((conn or {}).get("id"), message_id)
    return {"sent": ok, "status": response.status_code, "message_id": message_id,
            "detail": None if ok else response.text[:200]}


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


def _creds(connection: dict | None) -> tuple[str | None, str | None, dict]:
    """(token, phone_number_id, tenant) de la conexión indicada o de la principal."""
    tenant = T.get_config()
    conn = connection if connection is not None else T.whatsapp_connection_by_id(None, tenant)
    if conn:
        return conn.get("token"), conn.get("phone_number_id"), tenant
    return None, None, tenant


async def send_text(to: str, text: str, connection: dict | None = None) -> dict:
    token, pnid, tenant = _creds(connection)
    if not token or not pnid:
        return {"sent": False, "reason": f"Tenant {tenant['id']}: WhatsApp sin token/phone_number_id"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        **recipient_fields(to),
        "type": "text",
        "text": {"body": text[:4096]},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GRAPH}/{pnid}/messages", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
    return _sent_result(r, connection)


async def upload_media(filename: str, content: bytes, mime: str, connection: dict | None = None) -> dict:
    """Sube un archivo a WhatsApp (POST /{pnid}/media) y devuelve su media_id."""
    token, pnid, tenant = _creds(connection)
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


async def send_image_upload(to: str, filename: str, content: bytes,
                            mime: str, caption: str = "", connection: dict | None = None, delivery_guard=None) -> dict:
    """Sube la imagen y la envía por WhatsApp usando su media_id (sin URL pública)."""
    up = await upload_media(filename, content, mime, connection=connection)
    if not up.get("ok"):
        return {"sent": False, "reason": up.get("detail") or up.get("reason")}
    if delivery_guard is not None and not delivery_guard():
        return {"sent": False, "reason": "conversation_changed"}
    token, pnid, _tenant = _creds(connection)
    image: dict = {"id": up["id"]}
    if caption:
        image["caption"] = caption[:1024]
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual",
               **recipient_fields(to), "type": "image", "image": image}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GRAPH}/{pnid}/messages", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
    return {**_sent_result(r, connection), "media_id": up.get("id")}


async def send_image(to: str, link: str, caption: str = "", connection: dict | None = None) -> dict:
    """Envía una imagen por WhatsApp Cloud API (type=image). `link` es una URL pública."""
    token, pnid, tenant = _creds(connection)
    if not token or not pnid:
        return {"sent": False, "reason": f"Tenant {tenant['id']}: WhatsApp sin token/phone_number_id"}
    image: dict = {"link": link}
    if caption:
        image["caption"] = caption[:1024]
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual",
               **recipient_fields(to), "type": "image", "image": image}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GRAPH}/{pnid}/messages", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
    return _sent_result(r, connection)


_CONTACT_STD_KEYS = {"profile", "wa_id"}


def _contact_for(value: dict, wa_from: str | None, user_id: str | None = None) -> dict:
    """Identidad del remitente según `contacts[]`: nombre de perfil, wa_id y cualquier
    campo adicional que Meta añada (p. ej. identificadores con alcance de negocio o
    username). Los campos extra se conservan tal cual en `identity` para no asumir
    nombres de campo no confirmados (ver plan: BSUID/usernames)."""
    for c in value.get("contacts", []) or []:
        if not isinstance(c, dict):
            continue
        if not ((wa_from and str(c.get("wa_id")) == str(wa_from)) or
                (user_id and str(c.get("user_id")) == str(user_id))):
            continue
        profile = c.get("profile") or {}
        extra = {k: v for k, v in c.items() if k not in _CONTACT_STD_KEYS}
        return {"wa_id": c.get("wa_id"), "profile_name": profile.get("name"),
                "username": profile.get("username"), "identity": extra or None}
    return {"wa_id": wa_from, "profile_name": None, "identity": None}


def parse_incoming(body: dict) -> list[dict]:
    """Extrae eventos del payload del webhook de Meta.

    Tipos devueltos: 'text', 'audio', 'image'|'document'|'video'|'sticker' (mensajes
    del cliente, con `id`, `timestamp` y `contact`), 'status' (entregas), 'echo'
    (mensaje enviado desde la app WhatsApp Business en modo coexistencia:
    `smb_message_echoes`), 'history' y 'state_sync' (sincronización Coex; solo se
    registran, nunca disparan respuestas). Puede venir más de uno.
    """
    out = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            field = change.get("field") or "messages"
            pnid = (value.get("metadata", {}) or {}).get("phone_number_id")
            if field == "smb_message_echoes":
                for m in value.get("message_echoes", []) or []:
                    out.append({"type": "echo", "phone_number_id": pnid, "id": m.get("id"),
                                "to": m.get("to"), "timestamp": m.get("timestamp"),
                                "text": ((m.get("text") or {}).get("body") if m.get("type") == "text" else None),
                                "kind": m.get("type")})
                continue
            if field in ("history", "smb_app_state_sync"):
                out.append({"type": "history" if field == "history" else "state_sync",
                            "phone_number_id": pnid, "raw_keys": sorted(value.keys()), "raw": value})
                continue
            for st in value.get("statuses", []) or []:
                out.append({"type": "status", "phone_number_id": pnid, "id": st.get("id"),
                            "status": st.get("status"), "recipient": st.get("recipient_id") or st.get("recipient_user_id"),
                            "timestamp": st.get("timestamp")})
            for msg in value.get("messages", []) or []:
                base = {"phone_number_id": pnid, "from": msg.get("from") or msg.get("from_user_id"), "id": msg.get("id"),
                        "user_id": msg.get("from_user_id"), "phone": msg.get("from"),
                        "timestamp": msg.get("timestamp"), "contact": _contact_for(value, msg.get("from"), msg.get("from_user_id"))}
                if msg.get("type") == "text":
                    out.append({**base, "type": "text", "text": msg.get("text", {}).get("body", "")})
                elif msg.get("type") == "audio":
                    audio = msg.get("audio", {}) or {}
                    out.append({**base, "type": "audio", "media_id": audio.get("id"),
                                "mime_type": audio.get("mime_type")})
                elif msg.get("type") in ("image", "document", "video", "sticker"):
                    obj = msg.get(msg["type"], {}) or {}
                    out.append({**base, "type": msg["type"], "media_id": obj.get("id"),
                                "mime_type": obj.get("mime_type"), "filename": obj.get("filename"),
                                "caption": obj.get("caption")})
                else:
                    out.append({**base, "type": "unsupported", "kind": msg.get("type")})
    return out


async def download_media(media_id: str, connection: dict | None = None) -> tuple[bytes | None, str | None]:
    """Descarga un archivo entrante de WhatsApp por media_id (GET media -> url -> bytes)."""
    token, _pnid, _tenant = _creds(connection)
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
            parsed = urlparse(url or "")
            host = (parsed.hostname or "").lower()
            if (parsed.scheme != "https" or parsed.username or parsed.password or
                    not any(host == domain or host.endswith("." + domain)
                            for domain in ("facebook.com", "fbsbx.com", "fbcdn.net"))):
                return None, None
            from . import media_limits
            content, _ = await media_limits.download(client, url, headers=headers)
        return content, mime
    except (httpx.RequestError, ValueError):
        return None, None
