"""Adapter Telegram Bot API por tenant (multi-tenant). Mismo espíritu que whatsapp.py.

Telegram NO incluye la identidad del bot en el update, así que el tenant se
resuelve por la URL del webhook: /telegram/webhook/{tenant_id}. Para desarrollo
local (sin dominio público) se usa long polling (poll_loop). Ambos convergen en
process_update() -> engine.handle_message().
"""
import asyncio

import httpx

from . import audio_adapter, auth, db, engine, observability
from core import tenants as T

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4096


def _escape_html(text: str) -> str:
    """Telegram parse_mode=HTML solo requiere escapar estos 3 caracteres."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _call(method: str, payload: dict) -> dict:
    tenant = T.get_config()
    token = T.telegram_token(tenant)
    if not token:
        return {"ok": False, "reason": f"Telegram sin bot_token configurado"}
    url = API.format(token=token, method=method)
    async with httpx.AsyncClient(timeout=45) as client:
        for _ in range(2):
            try:
                r = await client.post(url, json=payload)
            except httpx.RequestError as e:
                return {"ok": False, "reason": f"red: {e}"}
            if r.status_code == 429:
                retry = (r.json().get("parameters", {}) or {}).get("retry_after", 1)
                await asyncio.sleep(min(retry, 5))
                continue
            try:
                return r.json()
            except ValueError:
                return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    return {"ok": False, "reason": "rate_limited"}


_EXTERNAL_BTN_HOSTS = ("wa.me", "whatsapp", "instagram", "facebook", "fb.me", "t.me", "messenger")


def build_handoff_markup() -> dict | None:
    """Teclado inline para el handoff. Con takeover el asesor atiende en el MISMO
    chat, así que NO se muestran botones a canales externos (WhatsApp/redes)."""
    tenant = T.get_config()
    btns = (tenant.get("telegram", {}) or {}).get("handoff_buttons") or []
    rows = []
    for b in btns:
        url = b.get("url") or ""
        if url and not any(h in url.lower() for h in _EXTERNAL_BTN_HOSTS):
            rows.append([{"text": b["text"], "url": url}])
    return {"inline_keyboard": rows} if rows else None


async def send_message(chat_id, text: str, reply_markup: dict | None = None) -> dict:
    safe = _escape_html(text or "")
    parts = [safe[i:i + MAX_LEN] for i in range(0, len(safe), MAX_LEN)] or [""]
    result: dict = {"ok": True}
    for idx, part in enumerate(parts):
        payload = {
            "chat_id": chat_id, "text": part, "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup and idx == len(parts) - 1:
            payload["reply_markup"] = reply_markup
        result = await _call("sendMessage", payload)
    return result


async def send_photo(chat_id, photo: str, caption: str = "") -> dict:
    """Envía una imagen por Telegram (sendPhoto). `photo` es una URL http(s) pública."""
    payload: dict = {"chat_id": chat_id, "photo": photo}
    if caption:
        payload["caption"] = _escape_html(caption)[:1024]
        payload["parse_mode"] = "HTML"
    return await _call("sendPhoto", payload)


def sent_media_ref(result: dict) -> dict | None:
    """De la respuesta de sendPhoto/sendDocument extrae {kind, ref(file_id)} del
    archivo enviado, para mostrarlo luego en el panel (burbuja del propio asesor)."""
    res = (result or {}).get("result") or {}
    photos = res.get("photo")
    if isinstance(photos, list) and photos and photos[-1].get("file_id"):
        return {"kind": "image", "ref": photos[-1]["file_id"]}
    doc = res.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        return {"kind": "document", "ref": doc["file_id"]}
    return None


async def send_file_upload(chat_id, filename: str, content: bytes,
                           mime: str = "", caption: str = "") -> dict:
    """Sube un archivo por multipart (sin URL pública). Imágenes -> sendPhoto;
    otros -> sendDocument (conserva el original, p.ej. PDF)."""
    tenant = T.get_config()
    token = T.telegram_token(tenant)
    if not token:
        return {"ok": False, "reason": f"Telegram sin bot_token configurado"}
    is_image = (mime or "").startswith("image/")
    method = "sendPhoto" if is_image else "sendDocument"
    field = "photo" if is_image else "document"
    data: dict = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = _escape_html(caption)[:1024]
        data["parse_mode"] = "HTML"
    files = {field: (filename or "archivo", content, mime or "application/octet-stream")}
    url = API.format(token=token, method=method)
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, data=data, files=files)
        return r.json()
    except httpx.RequestError as e:
        return {"ok": False, "reason": f"red: {e}"}
    except ValueError:
        return {"ok": False, "reason": "respuesta no-JSON de Telegram"}


async def send_typing(chat_id) -> dict:
    return await _call("sendChatAction", {"chat_id": chat_id, "action": "typing"})


def _extract_media(msg: dict) -> dict | None:
    """Detecta adjuntos entrantes (foto/documento/voz/audio/video/sticker)."""
    if msg.get("photo"):
        p = msg["photo"][-1]  # mayor resolución
        return {"kind": "image", "ref": p["file_id"], "mime": "image/jpeg", "name": "foto.jpg"}
    for key, kind in (("document", "document"), ("voice", "voice"), ("audio", "audio"),
                      ("video", "video"), ("sticker", "sticker")):
        obj = msg.get(key)
        if obj and obj.get("file_id"):
            return {"kind": kind, "ref": obj["file_id"],
                    "mime": obj.get("mime_type") or "application/octet-stream",
                    "name": obj.get("file_name") or f"{kind}"}
    return None


def parse_update(body: dict) -> dict | None:
    """Extrae lo mínimo de un Update. Soporta texto y adjuntos (media)."""
    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return None
    chat = msg.get("chat", {})
    if "id" not in chat:
        return None
    base = {"chat_id": chat["id"], "chat_type": chat.get("type", "private"),
            "from": msg.get("from", {})}
    text = msg.get("text")
    if text:
        return {**base, "text": text}
    media = _extract_media(msg)
    if media:
        return {**base, "media": {**media, "provider": "telegram"}, "text": msg.get("caption") or ""}
    return None  # tipos no soportados (ubicación, contacto, etc.)


def _allows_chat(chat_type: str) -> bool:
    """Por defecto el bot SOLO responde en chats privados (1-a-1), no en grupos.
    Un tenant puede habilitar grupos con telegram.allow_groups=true."""
    tenant = T.get_config()
    if chat_type == "private":
        return True
    return bool((tenant.get("telegram", {}) or {}).get("allow_groups"))


async def process_update(body: dict) -> dict:
    """Pipeline compartido por webhook y poller."""
    tenant = T.get_config()
    msg = parse_update(body)
    if not msg:
        return {"handled": False}
    if not _allows_chat(msg["chat_type"]):
        # Ignora grupos/canales en silencio (no responde ni gasta LLM).
        return {"handled": False, "ignored_chat_type": msg["chat_type"]}
    chat_id = msg["chat_id"]
    if msg.get("media"):
        media = msg["media"]
        # Voz/audio: si hay transcripción configurada y el bot no está en pausa,
        # transcribimos y lo tratamos como texto (el bot responde). Si no, handoff.
        if media["kind"] in ("voice", "audio") and audio_adapter.enabled(tenant):
            cid = db.get_or_create_conversation(f"tg:{chat_id}", "telegram")
            if db.conversation_status(cid) != "handoff":
                return await _handle_incoming_audio(chat_id, msg, cid)
        return await _handle_incoming_media(chat_id, msg)
    # Si un asesor atiende (handoff) no mostramos "escribiendo…": el bot está en pausa.
    cid = db.get_or_create_conversation(f"tg:{chat_id}", "telegram")
    if db.conversation_status(cid) != "handoff":
        await send_typing(chat_id)
    try:
        out = await engine.handle_message(f"tg:{chat_id}", msg["text"],
                                          channel="telegram", conversation_id=cid)
    except engine.ConversationBusyError:
        return {"handled": False, "busy": True}
    # Lead nuevo: banner de primer envío antes de la respuesta normal.
    await _send_banner(chat_id, cid, out.get("banner"))
    # Bot pausado (un asesor atiende) o sin texto -> el bot no responde.
    if out.get("paused") or not (out.get("response") or "").strip():
        return {"handled": True, "paused": out.get("paused", False)}
    markup = build_handoff_markup() if out.get("handoff") else None
    await send_message(chat_id, out["response"], reply_markup=markup)
    return {"handled": True, "handoff": out.get("handoff", False), "new_lead": out.get("new_lead", False)}


async def _send_banner(chat_id, cid: str, banner: dict | None) -> None:
    """Envía el banner de primer envío (imagen + texto o solo texto) y lo registra."""
    tenant = T.get_config()
    if not banner:
        return
    image_url = banner.get("image_url")
    text = (banner.get("text") or "").strip()
    if image_url:
        r = await send_photo(chat_id, image_url, text)
        mref = sent_media_ref(r)
        media = {"provider": "telegram", "kind": "image", "ref": mref["ref"],
                 "caption": text} if mref and mref.get("ref") else None
        db.add_message(cid, "assistant", text or "🎁 Banner primer envío", media=media)
    elif text:
        await send_message(chat_id, text)
        db.add_message(cid, "assistant", text)


_MEDIA_LABEL = {"image": "🖼️ Imagen", "document": "📎 Archivo", "voice": "🎤 Nota de voz",
                "audio": "🎵 Audio", "video": "🎬 Video", "sticker": "🌟 Sticker"}


async def _handle_incoming_media(chat_id, msg: dict) -> dict:
    """Guarda un adjunto entrante como mensaje del usuario (visible en el panel) y,
    si el bot no está en pausa, deriva a un asesor (el bot no procesa archivos)."""
    tenant = T.get_config()
    media = msg["media"]
    caption = (msg.get("text") or "").strip()
    cid = db.get_or_create_conversation(f"tg:{chat_id}", "telegram")
    label = _MEDIA_LABEL.get(media["kind"], "📎 Adjunto")
    name = media.get("name") or ""
    text = label + (f": {name}" if name and media["kind"] not in ("image", "sticker") else "")
    if caption:
        text += f" — {caption}"
    db.add_message(cid, "user", text, media={**media, "caption": caption})
    db.merge_lead_data(cid, {"commercial_stage": "proof_received"})
    observability.event("message.media_received", tenant_id=tenant["id"],
                        conversation_id=cid, kind=media["kind"])
    status = db.conversation_status(cid)
    if status != "handoff":
        # Comprobante/adjunto -> lo revisa un humano: pausa el bot y asigna asesor.
        db.set_conversation_status(cid, "handoff")
        auth.derive_to_advisor(cid)
        ack = ("Recibí tu comprobante 📎. Un asesor lo revisará y te contactará "
               "para completar tu envío.")
        db.add_message(cid, "assistant", ack)
        await send_message(chat_id, ack)
        observability.event("conversation.handoff", tenant_id=tenant["id"],
                            conversation_id=cid, reason="media")
    return {"handled": True, "media": media["kind"]}


async def _handle_incoming_audio(chat_id, msg: dict, cid: str) -> dict:
    """Voz/audio entrante: descarga, transcribe y lo procesa como texto para que el
    bot responda. La transcripción se guarda como mensaje del usuario junto al audio
    original (burbuja). Si la transcripción falla -> cae a media/handoff."""
    tenant = T.get_config()
    media = msg["media"]
    content, ctype = await download_file(media["ref"])
    if not content:
        return await _handle_incoming_media(chat_id, msg)
    tr = await audio_adapter.transcribe_bytes(
        tenant, content, media.get("mime") or ctype or "audio/ogg"
    )
    text = (tr.get("text") or "").strip()
    if not tr.get("ok") or not text:
        observability.event("audio.transcription_failed", tenant_id=tenant["id"],
                            conversation_id=cid, error=tr.get("error"))
        return await _handle_incoming_media(chat_id, msg)
    observability.event("audio.transcribed", tenant_id=tenant["id"], conversation_id=cid,
                        provider=tr.get("provider"), chars=len(text))
    await send_typing(chat_id)
    try:
        # Un solo mensaje de usuario: texto = transcripción, media = audio original.
        out = await engine.handle_message(f"tg:{chat_id}", text, channel="telegram",
                                          conversation_id=cid, user_media={**media, "caption": text})
    except engine.ConversationBusyError:
        return {"handled": False, "busy": True}
    if out.get("paused") or not (out.get("response") or "").strip():
        return {"handled": True, "paused": out.get("paused", False), "transcribed": True}
    markup = build_handoff_markup() if out.get("handoff") else None
    await send_message(chat_id, out["response"], reply_markup=markup)
    return {"handled": True, "handoff": out.get("handoff", False), "transcribed": True}


async def download_file(file_id: str) -> tuple[bytes | None, str | None]:
    """Descarga un archivo de Telegram por file_id (getFile + descarga con el token)."""
    tenant = T.get_config()
    token = T.telegram_token(tenant)
    if not token:
        return None, None
    info = await _call("getFile", {"file_id": file_id})
    if not info.get("ok"):
        return None, None
    file_path = (info.get("result") or {}).get("file_path")
    if not file_path:
        return None, None
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(url)
    except httpx.RequestError:
        return None, None
    if r.status_code != 200:
        return None, None
    return r.content, r.headers.get("content-type") or "application/octet-stream"


# ---------- admin / diagnóstico ----------
async def get_me() -> dict:
    return await _call("getMe", {})


async def get_webhook_info() -> dict:
    return await _call("getWebhookInfo", {})


async def set_webhook(base_url: str) -> dict:
    tenant = T.get_config()
    url = base_url.rstrip("/") + "/telegram/webhook"
    payload: dict = {"url": url, "allowed_updates": ["message"], "drop_pending_updates": True}
    secret = T.telegram_secret(tenant)
    if secret:
        payload["secret_token"] = secret
    return {"webhook_url": url, "result": await _call("setWebhook", payload)}


async def delete_webhook() -> dict:
    return await _call("deleteWebhook", {"drop_pending_updates": False})


# ---------- long polling (solo desarrollo local) ----------
async def poll_loop(stop: asyncio.Event | None = None) -> None:
    import traceback
    tenant = T.get_config()
    await delete_webhook()  # polling y webhook son mutuamente excluyentes
    offset = None
    print(f"[telegram] polling activo para '{tenant['id']}'", flush=True)
    while not (stop and stop.is_set()):
        payload: dict = {"timeout": 30, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        data = await _call("getUpdates", payload)
        if not data.get("ok"):
            # No lo escondas: log del motivo (409 webhook activo, red, token, etc.)
            print(f"[telegram] getUpdates fallo: {data.get('description') or data.get('reason') or data}", flush=True)
            await asyncio.sleep(3)
            continue
        updates = data.get("result", [])
        if updates:
            print(f"[telegram] {len(updates)} update(s) recibido(s)", flush=True)
        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat", {})
            print(f"[telegram] update {upd['update_id']}: chat={chat.get('type')} "
                  f"text={(msg.get('text') or '')[:40]!r}", flush=True)
            try:
                res = await process_update(upd)
                print(f"[telegram]  -> {res}", flush=True)
            except Exception as e:  # noqa: BLE001 - dev loop robusto
                print(f"[telegram] ERROR procesando update {upd.get('update_id')}: {e}", flush=True)
                traceback.print_exc()


async def start_pollers() -> list:
    tasks = []
    tenant = T.get_config()
    if T.telegram_token(tenant):
        tasks.append(asyncio.create_task(poll_loop()))
    return tasks
