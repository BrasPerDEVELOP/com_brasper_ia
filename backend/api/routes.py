"""API de la plataforma: chat, webhooks (WhatsApp/Telegram), panel de agencia."""
import asyncio
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from core import db, engine, whatsapp, connectors, wa_templates, auth, telegram, rate_limit, redis_runtime, jobs, debounce, observability, alerts, audio_adapter, util, brasper_api
from core import tenants as T

router = APIRouter()
logger = logging.getLogger(__name__)
_PLAIN_SECRET_KEYS = {"api_key", "token", "bot_token", "secret_token"}





_is_production = util.is_production  # helper único, ver core/util.py


def _plain_secret_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in _PLAIN_SECRET_KEYS and nested:
                paths.append(path)
            paths.extend(_plain_secret_paths(nested, path))
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            paths.extend(_plain_secret_paths(nested, f"{prefix}[{idx}]"))
    return paths


def _reject_plain_secrets(config: dict) -> None:
    if not _is_production():
        return
    paths = _plain_secret_paths(config)
    if paths:
        raise HTTPException(
            status_code=422,
            detail="En produccion no guardes secretos directos; usa *_env. Rutas rechazadas: "
            + ", ".join(paths),
        )


def _write_tenant_or_error(fn, *args):
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Tenant '{e.args[0]}' no existe") from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _enqueue_tenant_changed(tenant_id: str, actor: str | None, action: str) -> None:
    jobs.enqueue("tenant.changed", {"tenant_id": tenant_id, "actor": actor, "action": action})


# ---------- salud ----------
@router.get("/health")
def health():
    db_ok = db.ping()
    redis_ok = redis_runtime.ping() if redis_runtime.configured() else False
    ok = db_ok and (redis_ok or not _is_production())
    if _is_production() and db.backend_name() != "postgres":
        ok = False
    payload = {
        "ok": ok,
        "tenants": 1,
        "db": {"backend": db.backend_name(), "ok": db_ok},
        "redis": {"configured": redis_runtime.configured(), "ok": redis_ok},
        "env": "production" if _is_production() else "development",
    }
    return JSONResponse(payload, status_code=200 if ok else 503)


# ---------- chat (webchat / API por tenant) ----------
class ChatIn(BaseModel):
    message: str
    user_ref: str = "webchat-visitor"
    conversation_id: str | None = None


@router.post("/api/chat")
async def chat(body: ChatIn, request: Request,
               user: dict = Depends(auth.require("chat:test"))):
    rate_limit.check(request, "chat", limit=60)
    tenant = T.get_config()
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="Mensaje vacío")
    try:
        out = await engine.handle_message(body.user_ref, body.message.strip(),
                                          channel="webchat",
                                          conversation_id=body.conversation_id)
        # Lead nuevo: en webchat el banner se antepone al texto de respuesta.
        banner = out.get("banner")
        if banner and banner.get("text"):
            out["response"] = banner["text"] + "\n\n" + (out.get("response") or "")
        return out
    except engine.ConversationBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except engine.llm.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ---------- compat: webchat del IA anterior (ia.finzeler.com/consulta-webchat) ----------
# Reemplaza al bot mono-tenant previo SIN romper el frontend (com_brasper_www).
# Endpoint PUBLICO (sin auth), tenant fijo via WEBCHAT_TENANT (por defecto "brasper").
# Contrato idéntico al viejo: body {message, session_id?} + ?conversation_id
# -> {"response", "conversation_id"}.
class WebChatIn(BaseModel):
    message: str
    session_id: str | None = None


@router.post("/consulta-webchat")
async def consulta_webchat(body: WebChatIn, request: Request,
                           conversation_id: str | None = Query(None)):
    rate_limit.check(request, "chat", limit=60)
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="Mensaje vacío")
    session_id = (conversation_id or body.session_id or "webchat").strip() or "webchat"
    tenant = T.get_config()
    try:
        out = await engine.handle_message(f"webchat:{session_id}", body.message.strip(),
                                          channel="webchat", conversation_id=session_id)
        response = out.get("response") or ""
        banner = out.get("banner")
        if banner and banner.get("text"):
            response = banner["text"] + "\n\n" + response
        return {"response": response, "conversation_id": session_id}
    except engine.ConversationBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except engine.llm.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ---------- webhook WhatsApp (multi-tenant por phone_number_id) ----------
@router.get("/webhook")
def webhook_verify(mode: str = Query(None, alias="hub.mode"),
                   token: str = Query(None, alias="hub.verify_token"),
                   challenge: str = Query(None, alias="hub.challenge")):
    if mode == "subscribe" and token == whatsapp.verify_token():
        return PlainTextResponse(challenge or "")
    raise HTTPException(status_code=403, detail="Verify token inválido")


async def _handle_whatsapp_audio(tenant: dict, msg: dict, user_ref: str) -> dict:
    """Audio entrante de WhatsApp: se difiere al worker para transcribir. Si no
    hay Redis/worker, se transcribe en línea como fallback para no perder el
    mensaje (más lento, pero el webhook igual responde y no crashea)."""
    base = {"tenant": tenant["id"], "from": msg["from"], "resolved": True, "audio": True}
    payload = {
        "tenant_id": tenant["id"], "channel": "whatsapp",
        "user_ref": user_ref, "to": msg["from"],
        "media_id": msg.get("media_id"), "mime_type": msg.get("mime_type"),
    }
    if jobs.enqueue("whatsapp.audio", payload):
        return {**base, "queued": True}
    try:
        tr = await audio_adapter.transcribe_whatsapp(tenant, msg.get("media_id"))
    except Exception as e:  # noqa: BLE001 - fallback en línea, no debe romper el webhook
        return {**base, "sent": False, "reason": f"audio: {e}"}
    if not tr.get("ok") or not (tr.get("text") or "").strip():
        return {**base, "sent": False, "reason": f"audio no transcrito: {tr.get('error')}"}
    out = await engine.handle_message(user_ref, tr["text"].strip(), channel="whatsapp")
    send = await whatsapp.send_text(msg["from"], out["response"])
    return {**base, "transcribed": True, "sent": send.get("sent", False)}


_WA_MEDIA_LABEL = {"image": "🖼️ Imagen", "document": "📎 Archivo",
                   "video": "🎬 Video", "sticker": "🌟 Sticker"}


async def _handle_whatsapp_media(tenant: dict, msg: dict, user_ref: str) -> dict:
    """Media entrante de WhatsApp: se guarda como mensaje del usuario (visible en el
    panel) y la conversación pasa a manos de un asesor (el bot no procesa archivos)."""
    kind = msg["type"]
    cid = db.get_or_create_conversation(user_ref, "whatsapp")
    name = msg.get("filename") or ""
    caption = (msg.get("caption") or "").strip()
    label = _WA_MEDIA_LABEL.get(kind, "📎 Adjunto")
    text = label + (f": {name}" if name and kind not in ("image", "sticker") else "")
    if caption:
        text += f" — {caption}"
    media = {"provider": "whatsapp", "kind": kind, "ref": msg.get("media_id"),
             "mime": msg.get("mime_type"), "name": name or None, "caption": caption}
    db.add_message(cid, "user", text, media=media)
    db.merge_lead_data(cid, {"commercial_stage": "proof_received"})
    observability.event("message.media_received", tenant_id=tenant["id"], conversation_id=cid, kind=kind)
    sent = False
    if db.conversation_status(cid) != "handoff":
        # Comprobante/adjunto -> lo revisa un humano: pausa el bot y asigna asesor.
        db.set_conversation_status(cid, "handoff")
        auth.derive_to_advisor(cid)
        ack = ("Recibí tu comprobante 📎. Un asesor lo revisará y te contactará "
               "para completar tu envío.")
        db.add_message(cid, "assistant", ack)
        r = await whatsapp.send_text(msg["from"], ack)
        sent = r.get("sent", False)
        observability.event("conversation.handoff", tenant_id=tenant["id"],
                            conversation_id=cid, reason="media")
    return {"tenant": tenant["id"], "from": msg["from"], "resolved": True,
            "media": kind, "sent": sent}


@router.post("/webhook")
async def webhook_receive(request: Request):
    rate_limit.check(request, "whatsapp_webhook", limit=240)
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not whatsapp.verify_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Firma de webhook inválida")
    try:
        body = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")

    results = []
    for msg in whatsapp.parse_incoming(body):
        tenant = T.resolve_by_phone_number_id(msg["phone_number_id"])
        if not tenant:
            results.append({"from": msg["from"], "resolved": False})
            continue
        user_ref = f"wa:{msg['from']}"

        if msg.get("type") == "audio":
            results.append(await _handle_whatsapp_audio(tenant, msg, user_ref))
            continue
        if msg.get("type") in ("image", "document", "video", "sticker"):
            results.append(await _handle_whatsapp_media(tenant, msg, user_ref))
            continue

        if debounce.buffer_message(
            tenant["id"], "whatsapp", user_ref, msg["text"], {"to": msg["from"]},
        ):
            results.append({"tenant": tenant["id"], "from": msg["from"],
                            "resolved": True, "queued": True})
            continue
        try:
            out = await engine.handle_message(user_ref, msg["text"],
                                              channel="whatsapp")
        except engine.ConversationBusyError as e:
            results.append({"tenant": tenant["id"], "from": msg["from"],
                            "resolved": True, "sent": False, "reason": str(e)})
            continue
        # Lead nuevo: banner de primer envío antes de la respuesta.
        banner = out.get("banner")
        if banner:
            if banner.get("image_url"):
                await whatsapp.send_image(msg["from"], banner["image_url"], banner.get("text") or "")
            elif banner.get("text"):
                await whatsapp.send_text(msg["from"], banner["text"])
            if out.get("conversation_id"):
                db.add_message(out["conversation_id"], "assistant",
                               banner.get("text") or "🎁 Banner primer envío")
        if out.get("paused") or not (out.get("response") or "").strip():
            # Un asesor humano atiende esta conversación: el bot no responde.
            results.append({"tenant": tenant["id"], "from": msg["from"],
                            "resolved": True, "sent": False, "paused": True})
# ---------- panel de agencia ----------
@router.get("/api/tenants")
def tenants_overview(user: dict = Depends(auth.require("tenants:read"))):
    summary = db.usage_summary()
    u = summary[0] if summary else {}
    out = []
    t = T.get_config()
    if t:
        tid = t.get("id", "brasper")
        cost = round(u.get("cost_usd") or 0, 6)
        fee = t.get("fee_usd", 0)
        out.append({
            "id": tid, "name": t.get("name", "Brasper"), "vertical": t.get("vertical", ""),
            "fee_usd": fee, "cost_usd": cost, "margin_usd": round(fee - cost, 6),
            "llm_model": t.get("llm", {}).get("model"),
            "llm_key_configured": bool(T.llm_api_key(t)),
            "whatsapp_configured": bool(T.whatsapp_token(t) and T.whatsapp_phone_number_id(t)),
            "telegram_configured": bool(T.telegram_token(t)),
            "handoff_number": t.get("handoff", {}).get("number"),
            "calls": u.get("calls", 0),
            "tokens_in": u.get("tokens_in") or 0,
            "tokens_out": u.get("tokens_out") or 0,
        })
    return {"tenants": out}


# ---------- administracion real de tenants ----------
class TenantCreateIn(BaseModel):
    id: str
    config: dict[str, Any]


class TenantPatchIn(BaseModel):
    config: dict[str, Any]


class TenantSecretRefsIn(BaseModel):
    refs: dict[str, str]
    note: str | None = None


@router.get("/api/admin/tenants")
def admin_tenants_list(user: dict = Depends(auth.require("tenants:read"))):
    cfg = T.get_config()
    # The UI expects a list of tenants
    return {
        "source": "config/tenants.json",
        "tenants": [{"id": cfg.get("id", "brasper"), **cfg}],
    }


@router.get("/api/admin/quote-rates")
def admin_tenant_quote_rates(user: dict = Depends(auth.require("tenants:read"))):
    tenant = T.get_config()
    if not brasper_api.enabled(tenant):
        raise HTTPException(status_code=409, detail="La API de cotización no está activa para este cliente")
    rates = brasper_api.live_rates(tenant)
    if not rates:
        raise HTTPException(status_code=503, detail="La API de Brasper no devolvió tasas disponibles")
    allowed = set(tuple(pair) for pair in (tenant.get("quote") or {}).get("pairs", []))
    return {
        "source": "Brasper API",
        "rates": [r for r in rates if (r["origin"], r["destination"]) in allowed],
    }


@router.post("/api/admin/tenants")
def admin_tenants_create(body: TenantCreateIn,
                         user: dict = Depends(auth.require("tenants:write"))):
    _reject_plain_secrets(body.config)
    tenant = _write_tenant_or_error(T.upsert_tenant_config, body.id, body.config)
    db.add_audit_event(
        user.get("email"), "tenant.upsert", f"tenant:{tenant['id']}",
        {"keys": sorted(body.config.keys())},
    )
    _enqueue_tenant_changed(tenant["id"], user.get("email"), "tenant.upsert")
    return {"tenant": tenant}


@router.patch("/api/admin/tenants")
def admin_tenants_patch(body: TenantPatchIn,
                        user: dict = Depends(auth.require("tenants:write"))):
    _reject_plain_secrets(body.config)
    
    # Save the config locally to tenants.json
    import json
    cfg_path = T.CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if "tenants" not in data:
        data["tenants"] = {}
    if "brasper" not in data["tenants"]:
        data["tenants"]["brasper"] = {}
        
    def deep_merge(target, source):
        for k, v in source.items():
            if isinstance(v, dict) and isinstance(target.get(k), dict):
                deep_merge(target[k], v)
            else:
                target[k] = v
                
    deep_merge(data["tenants"]["brasper"], body.config)
    
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    T.reload_config()
    tenant = T.get_config()

    db.add_audit_event(
        user.get("email"), "tenant.patch", "tenant:brasper",
        {"keys": sorted(body.config.keys())},
    )
    _enqueue_tenant_changed(tenant.get("id", "brasper"), user.get("email"), "tenant.patch")
    return {"tenant": tenant}


@router.post("/api/admin/tenants/pause")
def admin_tenants_pause(user: dict = Depends(auth.require("tenants:write"))):
    tenant = _write_tenant_or_error(T.set_tenant_active, T.get_config()["id"], False)
    db.add_audit_event(user.get("email"), "tenant.pause", f"tenant:{tenant['id']}")
    _enqueue_tenant_changed(tenant["id"], user.get("email"), "tenant.pause")
    return {"tenant": tenant}


@router.post("/api/admin/tenants/resume")
def admin_tenants_resume(user: dict = Depends(auth.require("tenants:write"))):
    tenant = _write_tenant_or_error(T.set_tenant_active, T.get_config()["id"], True)
    db.add_audit_event(user.get("email"), "tenant.resume", f"tenant:{tenant['id']}")
    _enqueue_tenant_changed(tenant["id"], user.get("email"), "tenant.resume")
    return {"tenant": tenant}


@router.post("/api/admin/tenants/secrets")
def admin_tenants_secret_refs(body: TenantSecretRefsIn,
                              user: dict = Depends(auth.require("tenants:write"))):
    tenant = _write_tenant_or_error(T.set_secret_refs, T.get_config()["id"], body.refs)
    for path, env_name in body.refs.items():
        db.add_secret_rotation(user.get("email"), path, env_name, body.note)
    db.add_audit_event(
        user.get("email"), "tenant.secret_refs", f"tenant:{tenant['id']}",
        {"refs": sorted(body.refs.keys())},
    )
    _enqueue_tenant_changed(tenant["id"], user.get("email"), "tenant.secret_refs")
    return {"tenant": tenant}


@router.get("/api/admin/tenants/secrets/rotations")
def admin_tenants_secret_rotations(limit: int = 100,
                                   user: dict = Depends(auth.require("config:read"))):
    tenant = T.get_config()
    return {"rotations": db.list_secret_rotations(limit)}


@router.get("/api/admin/tenants/usage")
def admin_tenants_usage(limit: int = 100,
                        user: dict = Depends(auth.require("usage:read"))):
    tenant = T.get_config()
    return {"summary": db.usage_summary(),
            "events": db.usage_events(limit)}


def _is_agent(user: dict) -> bool:
    """Rol 'agent' = asesor: ve/opera solo lo suyo. Owner/admin/analyst ven todo."""
    return user.get("role") == "agent"


def _assert_conversation_access(user: dict, conv: dict) -> None:
    """Un asesor solo opera conversaciones asignadas a él o libres (que reclama)."""
    if _is_agent(user):
        owner = conv.get("assigned_to")
        if owner and owner != user.get("email"):
            raise HTTPException(status_code=403, detail="Conversación asignada a otro asesor")


@router.get("/api/conversations")
def conversations(user: dict = Depends(auth.require("conversations:read"))):
    tenant = T.get_config()
    tenant_id = tenant["id"]
    if _is_agent(user):
        # El asesor ve sus conversaciones + las libres (cola por reclamar), no las de otros.
        convs = db.list_conversations(assigned_to=user.get("email"), include_unassigned=True)
    else:
        convs = db.list_conversations()
    return {"conversations": convs}


@router.get("/api/conversations/{conversation_id}")
def conversation_messages(conversation_id: str,
                          user: dict = Depends(auth.require("conversations:read"))):
    tenant = T.get_config()
    tenant_id = tenant["id"]
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada para este tenant")
    _assert_conversation_access(user, conv)
    msgs = db.get_messages(conversation_id)
    # Fase 3: datos estructurados del lead (idioma, ruta, monto, KYC…) para el panel.
    return {"conversation_id": conversation_id, "messages": msgs,
            "lead": conv.get("lead_data", {}),
            "status": conv.get("status"), "assigned_to": conv.get("assigned_to")}


@router.get("/api/media")
async def media_proxy(provider: str, ref: str,
                      user: dict = Depends(auth.require("conversations:read"))):
    """Proxy de descarga de un adjunto entrante (imagen/archivo) para verlo en el
    panel, sin exponer los tokens del canal al navegador."""
    tenant = T.get_config()
    if provider == "telegram":
        content, mime = await telegram.download_file(ref)
    elif provider == "whatsapp":
        content, mime = await whatsapp.download_media(ref)
    else:
        raise HTTPException(status_code=422, detail="provider inválido")
    if content is None:
        raise HTTPException(status_code=404, detail="No se pudo obtener el archivo del canal")
    return Response(content=content, media_type=mime or "application/octet-stream")


# ---------- derivación a asesores ----------
class AssignIn(BaseModel):
    email: str | None = None   # None = desasignar


@router.get("/api/advisors")
def advisors_list(user: dict = Depends(auth.require("conversations:read"))):
    tenant = T.get_config()
    tenant_id = tenant["id"]
    return {"advisors": [auth._public_user(u) for u in auth.list_advisors()],
            "load": db.handoff_load_by_agent()}


@router.post("/api/conversations/{conversation_id}/assign")
def conversation_assign(conversation_id: str, body: AssignIn,
                        user: dict = Depends(auth.require("conversations:write"))):
    tenant = T.get_config()
    tenant_id = tenant["id"]
    email = (body.email or "").strip().lower() or None
    if email and not auth.user_from_email(email):
        raise HTTPException(status_code=422, detail=f"Usuario '{email}' no existe en el panel")
    db.assign_conversation(conversation_id, email)
    db.add_audit_event(user.get("email"), "conversation.assign",
                       f"conversation:{conversation_id}", {"assigned_to": email})
    return {"conversation_id": conversation_id, "assigned_to": email}


# ---------- takeover humano: el asesor responde por el canal ----------
class ReplyIn(BaseModel):
    text: str


class StatusIn(BaseModel):
    status: str  # 'handoff' (tomar, pausa el bot) | 'active' (devolver al bot) | 'closed'


async def _deliver_to_user(tenant: dict, conv: dict, text: str) -> dict:
    """Entrega el mensaje del asesor al usuario por su canal (Telegram/WhatsApp)."""
    ref = conv.get("user_ref") or ""
    channel = conv.get("channel")
    if channel == "telegram" and ref.startswith("tg:"):
        try:
            chat_id = int(ref[3:])
        except ValueError:
            return {"sent": False, "reason": "chat_id inválido"}
        r = await telegram.send_message(chat_id, text)
        return {"sent": bool(r.get("ok")), "channel": "telegram"}
    if channel == "whatsapp" and ref.startswith("wa:"):
        r = await whatsapp.send_text(ref[3:], text)
        return {"sent": bool(r.get("sent")), "channel": "whatsapp"}
    # webchat u otro: se guarda; el cliente lo verá al refrescar (no hay push).
    return {"sent": False, "channel": channel or "webchat", "reason": "canal sin envío push"}


@router.post("/api/conversations/{conversation_id}/reply")
async def conversation_reply(conversation_id: str, body: ReplyIn,
                             user: dict = Depends(auth.require("conversations:write"))):
    """El asesor escribe al usuario A TRAVÉS del bot (mismo chat). Pausa implícita:
    guarda el mensaje y lo entrega por el canal; el bot no interfiere en handoff."""
    tenant = T.get_config()
    tenant_id = tenant["id"]
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Mensaje vacío")
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    db.add_message(conversation_id, "assistant", text)
    # Al responder un asesor, la conversación queda en handoff (bot en pausa).
    if conv.get("status") != "handoff":
        db.set_conversation_status(conversation_id, "handoff")
    if not conv.get("assigned_to"):
        db.assign_conversation(conversation_id, user.get("email"))
    delivery = await _deliver_to_user(tenant, conv, text)
    db.add_audit_event(user.get("email"), "conversation.reply",
                       f"conversation:{conversation_id}", {"channel": conv.get("channel"),
                                                           "sent": delivery.get("sent")})
    return {"conversation_id": conversation_id, "delivery": delivery}


class ImageIn(BaseModel):
    image_url: str
    caption: str | None = None


@router.post("/api/conversations/{conversation_id}/send-image")
async def conversation_send_image(conversation_id: str, body: ImageIn,
                                  user: dict = Depends(auth.require("conversations:write"))):
    """El asesor envía una IMAGEN al usuario por su canal (Telegram sendPhoto /
    WhatsApp image). `image_url` debe ser una URL pública http(s)."""
    tenant = T.get_config()
    tenant_id = tenant["id"]
    url = (body.image_url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="image_url debe ser una URL http(s) pública")
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    caption = (body.caption or "").strip()
    ref = conv.get("user_ref") or ""
    channel = conv.get("channel")
    if channel == "telegram" and ref.startswith("tg:"):
        try:
            chat_id = int(ref[3:])
        except ValueError:
            raise HTTPException(status_code=422, detail="chat_id inválido")
        r = await telegram.send_photo(chat_id, url, caption)
        delivery = {"sent": bool(r.get("ok")), "channel": "telegram"}
    elif channel == "whatsapp" and ref.startswith("wa:"):
        r = await whatsapp.send_image(ref[3:], url, caption)
        delivery = {"sent": bool(r.get("sent")), "channel": "whatsapp"}
    else:
        delivery = {"sent": False, "channel": channel or "webchat", "reason": "canal sin envío push"}
    # Telegram devuelve file_id -> lo guardamos como media (burbuja del asesor).
    media = None
    if delivery.get("sent") and channel == "telegram":
        mref = telegram.sent_media_ref(r)
        if mref and mref.get("ref"):
            media = {"provider": "telegram", "kind": mref["kind"], "ref": mref["ref"],
                     "mime": "image/jpeg", "name": None, "caption": caption}
    text = (f"🖼️ {caption}" if caption else "🖼️ Imagen") if media else f"🖼️ {caption or 'Imagen'} — {url}"
    db.add_message(conversation_id, "assistant", text, media=media)
    if conv.get("status") != "handoff":
        db.set_conversation_status(conversation_id, "handoff")
    if not conv.get("assigned_to"):
        db.assign_conversation(conversation_id, user.get("email"))
    db.add_audit_event(user.get("email"), "conversation.send_image",
                       f"conversation:{conversation_id}", {"channel": channel, "sent": delivery.get("sent")})
    return {"conversation_id": conversation_id, "delivery": delivery}


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB (foto Telegram; WhatsApp imagen exige <=5 MB)


@router.post("/api/conversations/{conversation_id}/upload")
async def conversation_upload(conversation_id: str,
                              file: UploadFile = File(...), caption: str = Form(""),
                              user: dict = Depends(auth.require("conversations:write"))):
    """El asesor SUBE un archivo (imagen/PDF) y se envía al usuario por su canal:
    Telegram por multipart (sendPhoto/sendDocument), WhatsApp subiendo a /media."""
    tenant = T.get_config()
    tenant_id = tenant["id"]
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Archivo vacío")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Archivo supera 10 MB")
    mime = file.content_type or "application/octet-stream"
    fname = file.filename or "archivo"
    cap = (caption or "").strip()
    ref = conv.get("user_ref") or ""
    channel = conv.get("channel")
    if channel == "telegram" and ref.startswith("tg:"):
        try:
            chat_id = int(ref[3:])
        except ValueError:
            raise HTTPException(status_code=422, detail="chat_id inválido")
        r = await telegram.send_file_upload(chat_id, fname, content, mime, cap)
        delivery = {"sent": bool(r.get("ok")), "channel": "telegram", "detail": r.get("reason") or r.get("description")}
    elif channel == "whatsapp" and ref.startswith("wa:"):
        if not mime.startswith("image/"):
            raise HTTPException(status_code=422, detail="WhatsApp aquí solo acepta imagen (jpeg/png)")
        r = await whatsapp.send_image_upload(ref[3:], fname, content, mime, cap)
        delivery = {"sent": bool(r.get("sent")), "channel": "whatsapp", "detail": r.get("reason") or r.get("detail")}
    else:
        delivery = {"sent": False, "channel": channel or "webchat", "reason": "canal sin envío push"}
    label = "🖼️" if mime.startswith("image/") else "📎"
    # Guarda el adjunto SALIENTE como media para que el asesor vea su propia burbuja.
    media = None
    if delivery.get("sent") and channel == "telegram":
        mref = telegram.sent_media_ref(r)
        if mref and mref.get("ref"):
            media = {"provider": "telegram", "kind": mref["kind"], "ref": mref["ref"],
                     "mime": mime, "name": fname, "caption": cap}
    elif delivery.get("sent") and channel == "whatsapp" and r.get("media_id"):
        media = {"provider": "whatsapp", "kind": "image", "ref": r["media_id"],
                 "mime": mime, "name": fname, "caption": cap}
    db.add_message(conversation_id, "assistant", f"{label} {cap or fname}", media=media)
    if conv.get("status") != "handoff":
        db.set_conversation_status(conversation_id, "handoff")
    if not conv.get("assigned_to"):
        db.assign_conversation(conversation_id, user.get("email"))
    db.add_audit_event(user.get("email"), "conversation.upload",
                       f"conversation:{conversation_id}",
                       {"channel": channel, "filename": fname, "mime": mime, "sent": delivery.get("sent")})
    return {"conversation_id": conversation_id, "filename": fname, "delivery": delivery}


@router.post("/api/conversations/{conversation_id}/status")
def conversation_status(conversation_id: str, body: StatusIn,
                        user: dict = Depends(auth.require("conversations:write"))):
    """Tomar (handoff = pausa el bot), devolver al bot (active) o cerrar (closed)."""
    tenant = T.get_config()
    tenant_id = tenant["id"]
    status = (body.status or "").strip().lower()
    if status not in {"handoff", "active", "closed"}:
        raise HTTPException(status_code=422, detail="status debe ser handoff | active | closed")
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    db.set_conversation_status(conversation_id, status)
    if status == "handoff" and not (db.get_conversation(conversation_id) or {}).get("assigned_to"):
        db.assign_conversation(conversation_id, user.get("email"))
    if status == "active":
        db.assign_conversation(conversation_id, None)  # devuelto al bot
    db.add_audit_event(user.get("email"), "conversation.status",
                       f"conversation:{conversation_id}", {"status": status})
    return {"conversation_id": conversation_id, "status": status}


@router.get("/api/export")
def export_tenant(limit: int = 500,
                  user: dict = Depends(auth.require("conversations:read"))):
    """Exporta conversaciones + mensajes del tenant (portabilidad / offboarding)."""
    tenant = T.get_config()
    tenant_id = tenant["id"]
    return {"tenant_id": tenant_id, "conversations": db.export_conversations(limit)}


@router.get("/api/appointments")
def appointments(limit: int = 100,
                 user: dict = Depends(auth.require("conversations:read"))):
    tenant = T.get_config()
    tenant_id = tenant["id"]
    return {"appointments": db.list_appointments(limit)}


@router.get("/api/usage")
def usage(limit: int = 100,
          user: dict = Depends(auth.require("usage:read"))):
    tenant_id = T.get_config()["id"]
    return {"summary": db.usage_summary(),
            "events": db.usage_events(limit)}


@router.get("/api/ops/metrics")
def ops_metrics(user: dict = Depends(auth.require("usage:read"))):
    return observability.metrics_snapshot()


@router.get("/api/ops/alerts")
def ops_alerts(user: dict = Depends(auth.require("usage:read"))):
    return {"alerts": alerts.current_alerts()}


@router.get("/api/ops/dead-letter")
def ops_dead_letter(limit: int = 100, user: dict = Depends(auth.require("usage:read"))):
    """Jobs que agotaron reintentos (para diagnóstico operativo, no solo el conteo)."""
    return {"count": jobs.dead_letter_count(), "jobs": jobs.list_dead_letter(limit)}


@router.get("/api/ops/usage-daily")
def ops_usage_daily(user: dict = Depends(auth.require("usage:read"))):
    """Agregación de consumo/costo por día y tenant."""
    tenant_id = T.get_config()["id"]
    return {"daily": db.usage_daily()}


# ---------- auth / panel interno ----------
class LoginIn(BaseModel):
    email: str
    code: str | None = None


@router.post("/api/login")
def login(body: LoginIn, request: Request):
    rate_limit.check(request, "login", limit=10)
    host = request.client.host if request.client else ""
    local_request = host in {"127.0.0.1", "::1", "localhost", "testclient"}
    res = auth.login(body.email, code=body.code, local_request=local_request)
    if not res:
        raise HTTPException(status_code=401, detail="Credenciales inválidas o PANEL_LOGIN_CODE no configurado")
    return res


@router.get("/api/me")
def me(user: dict = Depends(auth.current_user)):
    return auth._public_user(user)


# ---------- conectores de APIs externas por tenant ----------
class ConnectorTestIn(BaseModel):
    variables: dict = {}


@router.get("/api/connectors")
def connectors_list(user: dict = Depends(auth.require("config:read"))):
    tenant = T.get_config()
    return {"connectors": connectors.list_connectors(tenant)}


@router.post("/api/connectors/{connector_key}/{tool}/test")
async def connectors_test(connector_key: str, tool: str,
                          body: ConnectorTestIn,
                          user: dict = Depends(auth.require("config:write"))):
    tenant = T.get_config()
    return await connectors.call_endpoint(tenant, connector_key, tool, body.variables)


# ---------- plantillas WhatsApp / HSM ----------
class TemplateSendIn(BaseModel):
    to: str
    template_name: str
    params: list[str] = []
    language: str | None = None


@router.get("/api/templates")
def templates_list(user: dict = Depends(auth.require("config:read"))):
    tenant = T.get_config()
    return {"templates": wa_templates.list_templates(tenant)}


@router.post("/api/templates/send")
async def templates_send(body: TemplateSendIn,
                         user: dict = Depends(auth.require("config:write"))):
    tenant = T.get_config()
    if not body.to.strip() or not body.template_name.strip():
        raise HTTPException(status_code=422, detail="Faltan 'to' o 'template_name'")
    return await wa_templates.send_template(
        tenant, body.to.strip(), body.template_name.strip(),
        params=body.params, language=body.language,
    )


# ---------- webhook Telegram ----------
# Conservamos la URL histórica con tenant porque los webhooks ya registrados en
# Telegram apuntan allí. La ruta sin tenant es la forma canónica single-tenant.
@router.post("/telegram/webhook")
@router.post("/telegram/webhook/{tenant_id}")
async def telegram_webhook(request: Request, tenant_id: str | None = None):
    rate_limit.check(request, "telegram_webhook", limit=240)
    tenant = T.get_config()
    if tenant_id is not None and tenant_id != tenant["id"]:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    secret = T.telegram_secret(tenant)
    if _is_production() and not secret:
        raise HTTPException(status_code=503, detail="Telegram secret token no configurado")
    if secret and not hmac.compare_digest(
            request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), secret):
        raise HTTPException(status_code=403, detail="Secret token de Telegram inválido")
    try:
        body = json.loads(await request.body() or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")
    parsed = telegram.parse_update(body)
    if parsed and debounce.buffer_message(
        tenant["id"],
        "telegram",
        f"tg:{parsed['chat_id']}",
        parsed["text"],
        {"chat_id": parsed["chat_id"]},
    ):
        return {"ok": True, "queued": True}
    # Telegram reintenta si tardamos: respondemos 200 rápido y procesamos aparte.
    # La tarea captura y registra excepciones; un create_task desnudo ocultaba los
    # fallos que dejaron mensajes recibidos sin respuesta.
    asyncio.create_task(_process_telegram_update_safely(body))
    return {"ok": True}


async def _process_telegram_update_safely(body: dict) -> None:
    try:
        await telegram.process_update(body)
    except Exception as exc:  # noqa: BLE001 - frontera de tarea en background
        parsed = telegram.parse_update(body) or {}
        logger.exception(
            "telegram.process_update failed chat_id=%s update_id=%s",
            parsed.get("chat_id"),
            body.get("update_id"),
        )
        observability.event(
            "telegram.update_failed",
            chat_id=parsed.get("chat_id"),
            update_id=body.get("update_id"),
            error=type(exc).__name__,
        )


# ---------- admin de Telegram por tenant ----------
class TgWebhookIn(BaseModel):
    base_url: str


@router.post("/api/telegram/set-webhook")
async def telegram_set_webhook(body: TgWebhookIn,
                               user: dict = Depends(auth.require("config:write"))):
    tenant = T.get_config()
    if not body.base_url.strip():
        raise HTTPException(status_code=422, detail="Falta 'base_url' (URL pública HTTPS)")
    return await telegram.set_webhook(body.base_url.strip())


@router.post("/api/telegram/delete-webhook")
async def telegram_delete_webhook(user: dict = Depends(auth.require("config:write"))):
    return await telegram.delete_webhook()


@router.get("/api/telegram/info")
async def telegram_info(user: dict = Depends(auth.require("config:read"))):
    tenant = T.get_config()
    return {"getMe": await telegram.get_me(),
            "webhook": await telegram.get_webhook_info()}
