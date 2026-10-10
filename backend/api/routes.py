"""API de la plataforma: chat, webhooks (WhatsApp/Telegram), panel de agencia."""
import asyncio
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from core import db, engine, whatsapp, connectors, wa_templates, auth, telegram, rate_limit, redis_runtime, jobs, debounce, observability, alerts, audio_adapter, util, brasper_api, llm
from core import audio_flow, features, handoff_summary, idempotency, knowledge, presence, public_docs, tool_contracts
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
        from core import media_library
        await media_library.deliver(out["conversation_id"], "webchat", body.user_ref, out.get("banner"))
        # Lead nuevo: en webchat el banner se antepone al texto de respuesta.
        banner = out.get("banner")
        if banner and banner.get("text") and not banner.get("campaign"):
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
        from core import media_library
        await media_library.deliver(out["conversation_id"], "webchat", session_id, banner)
        if banner and banner.get("text") and not banner.get("campaign"):
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


async def _handle_whatsapp_audio(tenant: dict, msg: dict, user_ref: str, conn: dict | None = None) -> dict:
    """Audio entrante de WhatsApp: se difiere al worker para transcribir. Si no
    hay Redis/worker, se transcribe en línea como fallback para no perder el
    mensaje. En ambos casos se conserva el audio como evidencia (burbuja reproducible
    en el panel), se confirman cifras ambiguas y, si falla la transcripción, pasa a un
    asesor en vez de perderse. Recibir un audio NO deriva por sí mismo."""
    base = {"tenant": tenant["id"], "from": msg["from"], "resolved": True, "audio": True}
    cid = db.get_or_create_conversation(user_ref, "whatsapp", connection_id=(conn or {}).get("id"))
    payload = {
        "tenant_id": tenant["id"], "channel": "whatsapp",
        "user_ref": user_ref, "to": msg["from"],
        "media_id": msg.get("media_id"), "mime_type": msg.get("mime_type"),
        "connection_id": (conn or {}).get("id"),
        "conversation_id": cid,
    }
    if jobs.enqueue("whatsapp.audio", payload):
        return {**base, "queued": True}
    media = {"provider": "whatsapp", "kind": "audio", "ref": msg.get("media_id"), "mime": msg.get("mime_type")}

    async def _send(text: str) -> dict:
        return await whatsapp.send_text(msg["from"], text, connection=conn)

    try:
        tr = await audio_adapter.transcribe_whatsapp(tenant, msg.get("media_id"), connection=conn)
    except Exception as e:  # noqa: BLE001 - fallback en línea, no debe romper el webhook
        tr = {"ok": False, "error": str(e)[:120]}
    if not tr.get("ok") or not (tr.get("text") or "").strip():
        out = await audio_flow.unreadable(channel="whatsapp", user_ref=user_ref, media=media, send=_send,
                                          error=tr.get("error"), conversation_id=cid)
        return {**base, "transcribed": False, "sent": out.get("sent", False), "reason": "audio no transcrito"}
    try:
        out = await audio_flow.process_transcript(channel="whatsapp", user_ref=user_ref, text=tr["text"].strip(),
                                                  media=media, send=_send, conversation_id=cid)
    except engine.ConversationBusyError as e:
        return {**base, "sent": False, "reason": str(e)}
    if out.get("conversation_id") and conn:
        db.set_connection(out["conversation_id"], conn["id"])
    return {**base, "transcribed": True, "sent": out.get("sent", False), "paused": out.get("paused", False),
            "ambiguous": out.get("ambiguous", False)}


_WA_MEDIA_LABEL = {"image": "🖼️ Imagen", "document": "📎 Archivo",
                   "video": "🎬 Video", "sticker": "🌟 Sticker"}


_PROOF_MIMES = ("image/", "application/pdf")
_PROOF_ACK = ("Recibí tu comprobante 📎. Un asesor lo validará en el sistema de Brasper; "
              "el envío se confirma solo cuando el pago quede verificado. Te aviso aquí mismo.")
_UNSUPPORTED_ACK = ("Recibí tu archivo, pero por aquí solo puedo procesar imágenes o PDF de comprobantes. "
                    "Si necesitas ayuda escribe *asesor*.")


async def _handle_whatsapp_media(tenant: dict, msg: dict, user_ref: str, conn: dict | None = None) -> dict:
    """Media entrante de WhatsApp: se guarda como mensaje del usuario (evidencia visible
    en el panel). Imagen/PDF se tratan como posible comprobante -> lo valida un asesor
    (el comprobante NUNCA se confunde con un pago confirmado). Video/sticker y otros
    formatos no derivan: se responde con cortesía y se conservan."""
    kind = msg["type"]
    cid = db.get_or_create_conversation(user_ref, "whatsapp", connection_id=(conn or {}).get("id"))
    if conn:
        db.set_connection(cid, conn["id"])
    name = msg.get("filename") or ""
    caption = (msg.get("caption") or "").strip()
    label = _WA_MEDIA_LABEL.get(kind, "📎 Adjunto")
    text = label + (f": {name}" if name and kind not in ("image", "sticker") else "")
    if caption:
        text += f" — {caption}"
    mime = msg.get("mime_type") or ""
    media = {"provider": "whatsapp", "kind": kind, "ref": msg.get("media_id"),
             "mime": mime, "name": name or None, "caption": caption}
    db.add_message(cid, "user", text, media=media)
    guard = {"conversation_id": cid, "human_revision": int((db.get_conversation(cid) or {}).get("human_revision", 0))}
    observability.event("message.media_received", tenant_id=tenant["id"], conversation_id=cid, kind=kind, mime=mime)
    is_proof = kind in ("image", "document") and (not mime or mime.startswith(_PROOF_MIMES))
    sent = False
    pt = db.get_lead_data(cid).get("idioma") == "pt"
    unsupported_ack = ("Recebi seu arquivo, mas por aqui posso processar apenas imagens ou PDF de comprovantes. Se precisar, peça um atendente." if pt else _UNSUPPORTED_ACK)
    proof_ack = ("Recebi seu comprovante 📎. Um atendente vai validá-lo no sistema Brasper; a operação só é confirmada depois da verificação do pagamento." if pt else _PROOF_ACK)
    if not is_proof:
        if db.conversation_status(cid) != "handoff":
            db.add_message(cid, "assistant", unsupported_ack)
            if not engine.delivery_allowed(guard):
                return {"resolved": True, "sent": False, "paused": True}
            r = await whatsapp.send_text(msg["from"], unsupported_ack, connection=conn)
            sent = r.get("sent", False)
        return {"tenant": tenant["id"], "from": msg["from"], "resolved": True,
                "media": kind, "sent": sent, "ignored": True}
    db.merge_lead_data(cid, {"commercial_stage": "proof_received", "proof_validated": False})
    from core import cases
    cases.attach_proof(cid, media)  # evidencia para el asesor; nunca confirma el pago
    if db.conversation_status(cid) != "handoff":
        # Comprobante -> lo valida un humano en el sistema: pausa el bot y asigna asesor.
        db.set_conversation_status(cid, "handoff")
        assigned = auth.derive_to_advisor(cid)
        handoff_summary.build(cid, "media", extra=f"{kind} {name}".strip())
        db.add_message(cid, "assistant", proof_ack)
        if not engine.delivery_allowed(guard):
            return {"resolved": True, "sent": False, "paused": True}
        r = await whatsapp.send_text(msg["from"], proof_ack, connection=conn)
        sent = r.get("sent", False)
        observability.event("conversation.handoff", tenant_id=tenant["id"],
                            conversation_id=cid, reason="media", assigned_to=assigned)
    return {"tenant": tenant["id"], "from": msg["from"], "resolved": True,
            "media": kind, "sent": sent}


async def _handle_whatsapp_echo(tenant: dict, msg: dict, conn: dict | None) -> dict:
    """Coexistencia: un mensaje enviado desde la app WhatsApp Business del celular
    (`smb_message_echoes`) es actividad HUMANA. Se guarda como mensaje del asesor en la
    conversación del destinatario, pausa el bot (takeover) y nunca genera respuesta.
    Solo aplica si la conexión está en modo coex y la flag `coex` está activa."""
    base = {"tenant": tenant["id"], "to": msg.get("to"), "resolved": True, "echo": True}
    if not (features.enabled("coex") and conn and conn.get("mode") == "coex"):
        observability.event("webhook.echo_ignored", reason="coex_disabled", connection=(conn or {}).get("id"))
        return {**base, "ignored": True}
    if not msg.get("to"):
        return {**base, "ignored": True, "reason": "sin destinatario"}
    from core import channel_receipts
    if channel_receipts.is_own(conn["id"], msg.get("id")):
        return {**base, "ignored": True, "reason": "eco de la API"}
    from core import channel_events, coex, outbound
    # Nuestro envío al mismo destinatario sigue en vuelo: el eco puede ser propio y aún no
    # conocemos su id. Se difiere y se resuelve al terminar el envío (nunca por igual texto).
    if outbound.in_flight(conn["id"], str(msg["to"])):
        channel_events.defer_echo(conn["id"], msg)
        return {**base, "deferred": True}
    cid = coex.apply_human_echo(conn["id"], msg)
    return {**base, "conversation_id": cid, "takeover": True}


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
        tenant = T.resolve_by_phone_number_id(msg.get("phone_number_id"))
        if not tenant:
            results.append({"from": msg.get("from"), "resolved": False})
            continue
        conn = T.resolve_whatsapp_connection(msg.get("phone_number_id"), tenant)
        kind = msg.get("type")

        # Eventos que NUNCA disparan respuestas: entregas e historial/sincronización Coex.
        if kind == "status":
            observability.event("whatsapp.status", status=msg.get("status"), message_id=msg.get("id"))
            from core import outbound
            outbound.apply_status((conn or {}).get("id"), msg.get("id"), msg.get("status"))
            results.append({"tenant": tenant["id"], "resolved": True, "status": msg.get("status")})
            continue
        if kind in ("history", "state_sync"):
            observability.event("whatsapp.coex_sync", kind=kind, keys=msg.get("raw_keys"))
            # Se conserva íntegro para replay cuando el contrato Meta esté confirmado; no se procesa.
            from core import channel_events
            stored = channel_events.record("whatsapp", (conn or {}).get("id"), kind, msg.get("raw") or {})
            results.append({"tenant": tenant["id"], "resolved": True, "sync": kind, "ignored": True,
                            "stored": stored})
            continue
        if kind == "echo":
            if features.enabled("webhook_dedup") and idempotency.seen_event("whatsapp", msg.get("id")):
                results.append({"tenant": tenant["id"], "resolved": True, "duplicate": True})
                continue
            results.append(await _handle_whatsapp_echo(tenant, msg, conn))
            continue

        # Deduplicación: Meta reintenta el mismo mensaje si no respondemos a tiempo.
        if features.enabled("webhook_dedup") and idempotency.seen_event("whatsapp", msg.get("id")):
            observability.event("webhook.duplicate", channel="whatsapp", message_id=msg.get("id"))
            results.append({"tenant": tenant["id"], "from": msg.get("from"), "resolved": True, "duplicate": True})
            continue
        if kind == "unsupported":
            results.append({"tenant": tenant["id"], "from": msg.get("from"), "resolved": True,
                            "ignored": True, "kind": msg.get("kind")})
            continue
        if not msg.get("from"):
            results.append({"resolved": True, "ignored": True, "reason": "missing_sender_identity"})
            continue
        user_ref = f"wa:{msg['from']}"
        cid = db.get_or_create_conversation(user_ref, "whatsapp", connection_id=(conn or {}).get("id"))
        contact = msg.get("contact") or {}

        if kind == "audio":
            results.append(await _handle_whatsapp_audio(tenant, msg, user_ref, conn))
            continue
        if kind in ("image", "document", "video", "sticker"):
            results.append(await _handle_whatsapp_media(tenant, msg, user_ref, conn))
            continue

        if debounce.buffer_message(
            tenant["id"], "whatsapp", user_ref, msg["text"],
            {"to": msg["from"], "connection_id": (conn or {}).get("id"), "conversation_id": cid},
        ):
            results.append({"tenant": tenant["id"], "from": msg["from"],
                            "resolved": True, "queued": True})
            continue
        try:
            out = await engine.handle_message(user_ref, msg["text"],
                                              channel="whatsapp", conversation_id=cid)
        except engine.ConversationBusyError as e:
            results.append({"tenant": tenant["id"], "from": msg["from"],
                            "resolved": True, "sent": False, "reason": str(e)})
            continue
        cid = out.get("conversation_id")
        if cid:
            if conn:
                db.set_connection(cid, conn["id"])
            # Identidad del remitente (nombre de perfil, wa_id y campos adicionales de Meta
            # como identificadores con alcance de negocio): se conservan sin asumir su
            # semántica. El teléfono sigue siendo `from` mientras Meta lo exponga.
            ident = {k: v for k, v in (("wa_profile_name", contact.get("profile_name")),
                                       ("wa_id", contact.get("wa_id")),
                                       ("wa_identity", contact.get("identity"))) if v}
            if ident:
                db.merge_lead_data(cid, ident)
            # Alias opaco (BSUID) del mismo evento: se vincula al contacto del teléfono que
            # Meta entrega junto a él; si ya apuntaba a otro contacto queda como conflicto.
            if msg.get("user_id") and msg.get("user_id") != msg.get("from"):
                from core import contacts
                contacts.resolve("whatsapp", (conn or {}).get("id"), str(msg["user_id"]),
                                 phone_hint=msg.get("phone"))
        if not engine.delivery_allowed(out):
            results.append({"resolved": True, "sent": False, "paused": True})
            continue
        # Lead nuevo: banner de primer envío antes de la respuesta.
        banner = out.get("banner")
        if banner and banner.get("campaign"):
            from core import media_library
            await media_library.deliver(cid, "whatsapp", msg["from"], banner, connection=conn)
        elif banner:
            if banner.get("image_url"):
                await whatsapp.send_image(msg["from"], banner["image_url"], banner.get("text") or "", connection=conn)
            elif banner.get("text"):
                await whatsapp.send_text(msg["from"], banner["text"], connection=conn)
            if cid:
                db.add_message(cid, "assistant", banner.get("text") or "🎁 Banner primer envío")
        if not engine.delivery_allowed(out) or not (out.get("response") or "").strip():
            # Un asesor humano atiende esta conversación: el bot no responde.
            results.append({"tenant": tenant["id"], "from": msg["from"],
                            "resolved": True, "sent": False, "paused": True})
            continue
        from core import outbound
        send = await outbound.deliver(out, "whatsapp", msg["from"],
                                      lambda: whatsapp.send_text(msg["from"], out["response"], connection=conn),
                                      connection_id=(conn or {}).get("id"), text=out["response"])
        results.append({"tenant": tenant["id"], "from": msg["from"],
                        "resolved": True, "sent": send.get("sent", False), "flow": out.get("flow")})
    return {"received": len(results), "results": results}


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


@router.delete("/api/admin/brasper/clients/{user_id}")
def admin_brasper_client_delete(
    user_id: str,
    expected_name: str = Query(..., min_length=2),
    user: dict = Depends(auth.require("tenants:write")),
):
    """Elimina un perfil Brasper concreto; nombre requerido como guard humano."""
    tenant = T.get_config()
    result = brasper_api.delete_client(tenant, user_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo eliminar el perfil Brasper de {expected_name}: {result.get('error')}",
        )
    db.add_audit_event(
        user.get("email"),
        "brasper.client.delete",
        f"brasper-user:{user_id}",
        {"expected_name": expected_name, "status": result.get("status")},
    )
    return {
        "deleted": True,
        "user_id": user_id,
        "expected_name": expected_name,
        "upstream_status": result.get("status"),
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
    """Alcance por canal/número/sector para todos los roles; además un asesor solo opera
    conversaciones asignadas a él o libres (que reclama)."""
    from core import access
    access.assert_conversation(user, conv)
    if _is_agent(user):
        owner = conv.get("assigned_to")
        if owner and owner != user.get("email"):
            raise HTTPException(status_code=403, detail="Conversación asignada a otro asesor")


@router.get("/api/conversations")
def conversations(status: str | None = None, channel: str | None = None,
                  assigned: str | None = None, q: str | None = None,
                  since: str | None = None, before: str | None = None, tag: str | None = None,
                  limit: int = Query(100, ge=1, le=500),
                  user: dict = Depends(auth.require("conversations:read"))):
    """Bandeja del panel con filtros opcionales.

    - `status`: active | handoff | closed · `channel`: whatsapp | telegram | webchat
    - `assigned`: `me` (las mías), `none` (libres, cola) o un email
    - `q`: texto libre (número, nombre del lead, último mensaje)
    - `since`: solo conversaciones con `updated_at` posterior (polling incremental)
    - `before`: cursor de paginación (`updated_at` anterior) · `limit`: tamaño de página
    """
    tenant = T.get_config()
    tenant_id = tenant["id"]
    if status and status not in {"active", "handoff", "closed"}:
        raise HTTPException(status_code=422, detail="status debe ser active | handoff | closed")
    kw: dict = {"status": status, "channel": channel, "q": q, "since": since, "before": before,
                "limit": limit, "tag": tag}
    if assigned == "me":
        kw["assigned_to"] = user.get("email")
    elif assigned == "none":
        kw["only_unassigned"] = True
    elif assigned:
        kw["assigned_to"] = assigned.strip().lower()
    if _is_agent(user):
        # El asesor ve sus conversaciones + las libres (cola por reclamar), no las de otros.
        if kw.get("assigned_to") and kw["assigned_to"] != user.get("email"):
            raise HTTPException(status_code=403, detail="Solo puedes filtrar por tus conversaciones")
        if not kw.get("assigned_to") and not kw.get("only_unassigned"):
            kw["assigned_to"] = user.get("email")
            kw["include_unassigned"] = True
    from core import access
    kw["scope_where"], kw["scope_args"] = access.sql_filter(user)
    convs = db.list_conversations(**kw)
    return {"conversations": convs, "count": len(convs),
            "next_before": convs[-1]["updated_at"] if len(convs) >= limit else None}


@router.get("/api/conversations/{conversation_id}")
def conversation_messages(conversation_id: str, after: str | None = None,
                          user: dict = Depends(auth.require("conversations:read"))):
    """Hilo completo o, con `after=<created_at>`, solo los mensajes nuevos (append)."""
    tenant = T.get_config()
    tenant_id = tenant["id"]
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada para este tenant")
    _assert_conversation_access(user, conv)
    msgs = db.get_messages(conversation_id, after=after)
    # Fase 3: datos estructurados del lead (idioma, ruta, monto, KYC…) para el panel.
    return {"conversation_id": conversation_id, "messages": msgs, "partial": bool(after),
            "lead": conv.get("lead_data", {}),
            "status": conv.get("status"), "assigned_to": conv.get("assigned_to"),
            "updated_at": conv.get("updated_at"), "connection_id": conv.get("connection_id"),
            "tags": db.tags_for(conversation_id) if not after else None,
            "notes": db.list_notes(conversation_id) if not after else None}


@router.delete("/api/conversations/{conversation_id}")
def conversation_delete(
    conversation_id: str,
    expected_user_ref: str = Query(..., min_length=1),
    user: dict = Depends(auth.require("tenants:write")),
):
    """Eliminación administrativa permanente con guard de identidad."""
    try:
        result = db.delete_conversation(conversation_id, expected_user_ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversación no encontrada") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add_audit_event(
        user.get("email"),
        "conversation.delete",
        f"conversation:{conversation_id}",
        {
            "user_ref": expected_user_ref,
            "channel": result.get("channel"),
            "deleted": result.get("deleted"),
        },
    )
    return result


@router.get("/api/media")
async def media_proxy(provider: str, ref: str, conversation_id: str | None = None,
                      user: dict = Depends(auth.require("conversations:read"))):
    """Proxy de descarga de un adjunto entrante (imagen/archivo) para verlo en el
    panel, sin exponer los tokens del canal al navegador."""
    tenant = T.get_config()
    if provider not in {"telegram", "whatsapp", "library"}:
        raise HTTPException(422, "provider inválido")
    if not conversation_id:
        raise HTTPException(422, "conversation_id es obligatorio")
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "Adjunto no encontrado")
    _assert_conversation_access(user, conv)
    matches = [m for m in db.get_messages(conversation_id)
               if (m.get("media") or {}).get("provider") == provider and (m.get("media") or {}).get("ref") == ref]
    if not matches:
        raise HTTPException(404, "Adjunto no encontrado")
    from core import access
    if any(access.is_private_media(m) for m in matches):
        access.assert_private_media(user)
    if provider == "telegram":
        content, mime = await telegram.download_file(ref)
    elif provider == "whatsapp":
        content, mime = await whatsapp.download_media(ref, connection=T.whatsapp_connection_by_id(conv.get("connection_id"), tenant))
    elif provider == "library":
        import base64
        from core import media_library
        try:
            asset_id, version = ref.rsplit(":", 1)
            item = media_library.get(asset_id, int(version), include_image=True)
            content, mime = base64.b64decode(item["image_base64"]), item["mime"]
        except (KeyError, ValueError) as exc:
            raise HTTPException(404, "Imagen no encontrada") from exc
    else:
        raise HTTPException(status_code=422, detail="provider inválido")
    if content is None:
        raise HTTPException(status_code=404, detail="No se pudo obtener el archivo del canal")
    return Response(content=content, media_type=mime or "application/octet-stream",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "sandbox", "Content-Disposition": "inline"})


# ---------- derivación a asesores ----------
class AssignIn(BaseModel):
    email: str | None = None   # None = desasignar


@router.get("/api/advisors")
def advisors_list(user: dict = Depends(auth.require("conversations:read"))):
    tenant = T.get_config()
    tenant_id = tenant["id"]
    snap = presence.snapshot()
    advisors = []
    for u in auth.list_advisors():
        pub = auth._public_user(u)
        pub["presence"] = snap.get(u["email"], {"status": "away", "last_seen": None, "fresh": False})
        advisors.append(pub)
    return {"advisors": advisors, "load": db.handoff_load_by_agent(),
            "presence_required": features.enabled("presence_required"), "presence_ttl_s": presence.ttl_seconds()}


@router.post("/api/conversations/{conversation_id}/assign")
def conversation_assign(conversation_id: str, body: AssignIn,
                        user: dict = Depends(auth.require("conversations:write"))):
    tenant = T.get_config()
    tenant_id = tenant["id"]
    email = (body.email or "").strip().lower() or None
    target = auth.user_from_email(email) if email else None
    if email and not target:
        raise HTTPException(status_code=422, detail=f"Usuario '{email}' no existe en el panel")
    if target and not target.get("active", True):
        raise HTTPException(status_code=422, detail=f"Usuario '{email}' está desactivado")
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    if _is_agent(user) and email != user.get("email") and conv.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Un asesor solo puede tomar o soltar sus conversaciones")
    from core import access
    if target and not access.conversation_allowed(target, conv):
        raise HTTPException(status_code=422, detail="El destinatario no tiene alcance sobre esta conversación")
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
        # Siempre por el número (conexión) que recibió la conversación; nunca se cambia implícitamente.
        conn = T.whatsapp_connection_by_id(conv.get("connection_id"), tenant)
        r = await whatsapp.send_text(ref[3:], text, connection=conn)
        return {"sent": bool(r.get("sent")), "channel": "whatsapp", "connection_id": (conn or {}).get("id")}
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
    db.invalidate_ai(conversation_id)
    db.add_message(conversation_id, "assistant", text, sender="agent", agent_email=user.get("email"))
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
    db.invalidate_ai(conversation_id)
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
        r = await whatsapp.send_image(ref[3:], url, caption,
                                      connection=T.whatsapp_connection_by_id(conv.get("connection_id"), tenant))
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
    db.add_message(conversation_id, "assistant", text, media=media, sender="agent",
                   agent_email=user.get("email"))
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
    db.invalidate_ai(conversation_id)
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
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
        r = await whatsapp.send_image_upload(ref[3:], fname, content, mime, cap,
                                             connection=T.whatsapp_connection_by_id(conv.get("connection_id"), tenant))
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
    db.add_message(conversation_id, "assistant", f"{label} {cap or fname}", media=media,
                   sender="agent", agent_email=user.get("email"))
    if conv.get("status") != "handoff":
        db.set_conversation_status(conversation_id, "handoff")
    if not conv.get("assigned_to"):
        db.assign_conversation(conversation_id, user.get("email"))
    db.add_audit_event(user.get("email"), "conversation.upload",
                       f"conversation:{conversation_id}",
                       {"channel": channel, "filename": fname, "mime": mime, "sent": delivery.get("sent")})
    return {"conversation_id": conversation_id, "filename": fname, "delivery": delivery}


class NoteIn(BaseModel):
    text: str


@router.get("/api/conversations/{conversation_id}/notes")
def conversation_notes(conversation_id: str,
                       user: dict = Depends(auth.require("conversations:read"))):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    return {"conversation_id": conversation_id, "notes": db.list_notes(conversation_id)}


@router.post("/api/conversations/{conversation_id}/notes")
def conversation_add_note(conversation_id: str, body: NoteIn,
                          user: dict = Depends(auth.require("conversations:write"))):
    """Nota interna del asesor: se guarda en el panel, NUNCA se envía al cliente."""
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Nota vacía")
    if len(text) > 2000:
        raise HTTPException(status_code=422, detail="Nota demasiado larga (máx. 2000)")
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    note = db.add_note(conversation_id, user.get("email"), text)
    db.add_audit_event(user.get("email"), "conversation.note",
                       f"conversation:{conversation_id}", {"len": len(text)})
    return {"conversation_id": conversation_id, "note": note}


_DEFAULT_QUICK_REPLIES = [
    {"key": "saludo", "title": "Saludo", "lang": "es",
     "text": "¡Hola {nombre}! Soy del equipo Brasper y te acompaño con tu envío. ¿En qué te ayudo?"},
    {"key": "saudacao", "title": "Saudação", "lang": "pt",
     "text": "Olá {nombre}! Sou da equipe Brasper e vou te acompanhar no seu envio. Como posso ajudar?"},
    {"key": "comprobante", "title": "Pedir comprobante", "lang": "es",
     "text": "Perfecto. Cuando realices el depósito de {monto}, envíame aquí el comprobante y lo validamos al instante."},
    {"key": "comprovante", "title": "Pedir comprovante", "lang": "pt",
     "text": "Perfeito. Quando fizer o depósito de {monto}, me envie aqui o comprovante e validamos na hora."},
    {"key": "tiempo", "title": "Tiempo de llegada", "lang": "es",
     "text": "Tu envío llega en minutos una vez confirmado el depósito; te aviso aquí mismo cuando esté acreditado."},
    {"key": "cierre", "title": "Cierre", "lang": "es",
     "text": "¡Listo {nombre}! Tu envío fue realizado con éxito. Gracias por confiar en Brasper 💙"},
]


@router.get("/api/quick-replies")
def quick_replies(user: dict = Depends(auth.require("conversations:read"))):
    """Respuestas rápidas del asesor. Se configuran en tenants.json (`quick_replies`,
    lista de {key,title,lang,text}); si no hay, se usan las predeterminadas.
    Variables disponibles: {nombre}, {monto}, {monto_recibir}, {ruta}."""
    cfg = T.get_config()
    items = cfg.get("quick_replies") or _DEFAULT_QUICK_REPLIES
    out = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not (it.get("text") or "").strip():
            continue
        out.append({"key": it.get("key") or f"qr{i}", "title": it.get("title") or f"Respuesta {i + 1}",
                    "lang": it.get("lang") or "es", "text": it["text"]})
    return {"quick_replies": out, "variables": ["nombre", "monto", "monto_recibir", "ruta"]}


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
    if status == "handoff":
        # Claim atómico: dos asesores tomando a la vez no provocan conflicto; el segundo recibe 409.
        if not db.claim_conversation(conversation_id, user.get("email")):
            owner = (db.get_conversation(conversation_id) or {}).get("assigned_to")
            raise HTTPException(status_code=409, detail=f"Conversación tomada por {owner}")
        if conv.get("status") != "handoff":
            handoff_summary.build(conversation_id, "manual")
    db.invalidate_ai(conversation_id, pause=False)
    db.set_conversation_status(conversation_id, status)
    from core import engagement
    engagement.cancel(conversation_id)
    if status == "closed":
        engagement.schedule(conversation_id, "survey")
    if status == "active":
        db.assign_conversation(conversation_id, None)  # devuelto al bot
        db.merge_lead_data(conversation_id, {"repeat_count": 0})
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


class VitalIn(BaseModel):
    name: str
    value: float
    path: str | None = None
    rating: str | None = None


@router.post("/api/ops/web-vitals")
def ops_web_vitals(body: VitalIn, user: dict = Depends(auth.current_user)):
    """El panel reporta Core Web Vitals (LCP, INP, CLS…) para seguir la velocidad real."""
    if body.name.upper() not in {"LCP", "INP", "CLS", "FCP", "TTFB", "FID"}:
        raise HTTPException(status_code=422, detail="métrica desconocida")
    observability.record_web_vital(body.name.upper(), float(body.value), body.path or "", body.rating or "")
    return {"ok": True}


@router.get("/api/ops/usage-daily")
def ops_usage_daily(user: dict = Depends(auth.require("usage:read"))):
    """Agregación de consumo/costo por día y tenant."""
    tenant_id = T.get_config()["id"]
    return {"daily": db.usage_daily()}


# ---------- presencia de asesores ----------
class PresenceIn(BaseModel):
    status: str = "available"  # available | busy | away


@router.post("/api/presence")
def presence_heartbeat(body: PresenceIn, user: dict = Depends(auth.current_user)):
    """Heartbeat del panel (cada ~30 s). Sin heartbeat vigente el asesor cuenta como ausente."""
    try:
        return presence.heartbeat(user.get("email"), body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/presence")
def presence_list(user: dict = Depends(auth.require("conversations:read"))):
    return {"presence": presence.snapshot(), "ttl_s": presence.ttl_seconds()}


# ---------- etiquetas ----------
class TagIn(BaseModel):
    tag: str


@router.get("/api/tags")
def tags_all(user: dict = Depends(auth.require("conversations:read"))):
    return {"tags": db.all_tags()}


@router.get("/api/conversations/{conversation_id}/tags")
def conversation_tags(conversation_id: str, user: dict = Depends(auth.require("conversations:read"))):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    return {"conversation_id": conversation_id, "tags": db.tags_for(conversation_id)}


@router.post("/api/conversations/{conversation_id}/tags")
def conversation_add_tag(conversation_id: str, body: TagIn,
                         user: dict = Depends(auth.require("conversations:write"))):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    try:
        tags = db.add_tag(conversation_id, body.tag, user.get("email"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add_audit_event(user.get("email"), "conversation.tag", f"conversation:{conversation_id}", {"tag": body.tag})
    return {"conversation_id": conversation_id, "tags": tags}


@router.delete("/api/conversations/{conversation_id}/tags/{tag}")
def conversation_remove_tag(conversation_id: str, tag: str,
                            user: dict = Depends(auth.require("conversations:write"))):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    _assert_conversation_access(user, conv)
    return {"conversation_id": conversation_id, "tags": db.remove_tag(conversation_id, tag)}


# ---------- conocimiento, herramientas y conexiones (inventario operativo) ----------
@router.get("/api/knowledge")
def knowledge_summary(user: dict = Depends(auth.require("conversations:read"))):
    """Estado del corpus FAQ (aprobadas vs. borradores). Edición vía repo/PR."""
    return knowledge.summary()


@router.get("/api/tools")
def tools_inventory(user: dict = Depends(auth.require("usage:read"))):
    """Contratos de herramientas: entradas, permisos, timeout y disponibilidad real."""
    return {"tools": tool_contracts.describe(), "features": features.all_flags()}


@router.get("/api/whatsapp/connections")
def whatsapp_connections(user: dict = Depends(auth.require("config:read"))):
    """Conexiones WhatsApp (varios números) sin secretos: id, modalidad y si están configuradas."""
    out = []
    for c in T.whatsapp_connections():
        out.append({"id": c["id"], "label": c["label"], "mode": c["mode"],
                    "phone_number_id": c.get("phone_number_id"), "display_phone": c.get("display_phone"),
                    "configured": bool(c.get("token") and c.get("phone_number_id"))})
    return {"connections": out, "coex_enabled": features.enabled("coex")}


# ---------- documentos públicos (privacidad / términos / eliminación de datos) ----------
class DocIn(BaseModel):
    expected_version: int = 0
    lang: str = "es"
    title: str
    body_md: str


class PublishIn(BaseModel):
    lang: str = "es"
    version: int


@router.get("/api/public/documents/{slug}")
def public_document(slug: str, lang: str = "es"):
    """Público, sin login: SOLO la versión publicada. Si no hay, 404 con estado."""
    try:
        doc = public_docs.get_published(slug, lang)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not doc:
        raise HTTPException(status_code=404, detail="Documento en preparación: aún no publicado")
    return {k: doc.get(k) for k in ("slug", "lang", "version", "title", "body_md", "published_at")}


class DeletionIn(BaseModel):
    contact: str
    channel: str | None = None
    detail: str | None = None


@router.post("/api/public/data-deletion-request")
def public_deletion_request(body: DeletionIn, request: Request):
    """Solicitud pública de eliminación de datos. No ejecuta borrados: queda registrada
    para verificación de identidad por el equipo (ver panel › Documentos públicos)."""
    rate_limit.check(request, "deletion_request", limit=5)
    try:
        req = public_docs.create_deletion_request(body.contact, body.channel, body.detail)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    observability.event("privacy.deletion_requested", request_id=req.get("id"), channel=body.channel)
    return {"id": req["id"], "status": req["status"], "received_at": req["created_at"]}


@router.get("/api/admin/documents")
def admin_documents(user: dict = Depends(auth.require("config:read"))):
    return {"documents": public_docs.overview(), "slugs": list(public_docs.SLUGS), "langs": list(public_docs.LANGS)}


@router.get("/api/admin/documents/{slug}")
def admin_document(slug: str, lang: str = "es", user: dict = Depends(auth.require("config:read"))):
    try:
        latest = public_docs.get_latest(slug, lang)
        return {"latest": latest, "published": public_docs.get_published(slug, lang),
                "history": public_docs.history(slug, lang)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/admin/documents/{slug}")
def admin_document_save(slug: str, body: DocIn, user: dict = Depends(auth.require("tenants:write"))):
    """Guarda un borrador (nueva versión). Los borradores NO son públicos."""
    try:
        doc = public_docs.save_draft(slug, body.lang, body.title, body.body_md, user.get("email"), body.expected_version)
    except public_docs.Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add_audit_event(user.get("email"), "document.draft", f"document:{slug}:{body.lang}", {"version": doc.get("version")})
    return {"document": doc}


@router.post("/api/admin/documents/{slug}/publish")
def admin_document_publish(slug: str, body: PublishIn, user: dict = Depends(auth.require("tenants:write"))):
    try:
        doc = public_docs.publish(slug, body.lang, body.version, user.get("email"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add_audit_event(user.get("email"), "document.publish", f"document:{slug}:{body.lang}", {"version": body.version})
    return {"document": doc}


class DeletionStatusIn(BaseModel):
    status: str
    note: str | None = None


@router.get("/api/admin/deletion-requests")
def admin_deletion_requests(user: dict = Depends(auth.require("tenants:write"))):
    return {"requests": public_docs.list_deletion_requests()}


@router.post("/api/admin/deletion-requests/{req_id}/status")
def admin_deletion_status(req_id: int, body: DeletionStatusIn, user: dict = Depends(auth.require("tenants:write"))):
    try:
        req = public_docs.set_deletion_status(req_id, body.status, user.get("email"), body.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add_audit_event(user.get("email"), "privacy.deletion_status", f"deletion_request:{req_id}",
                       {"status": body.status})
    return {"request": req}


# ---------- auth / panel interno ----------
class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str | None = Field(default=None, max_length=256)
    code: str | None = Field(default=None, max_length=256)   # PANEL_LOGIN_CODE (transición)


@router.post("/api/login")
def login(body: LoginIn, request: Request):
    rate_limit.check(request, "login", limit=10)
    host = request.client.host if request.client else ""
    local_request = host in {"127.0.0.1", "::1", "localhost", "testclient"}
    res = auth.login(body.email, code=body.code, password=body.password,
                     local_request=local_request, ip=host)
    if not res:
        raise HTTPException(status_code=401, detail="Correo, contraseña o código incorrectos, o cuenta desactivada")
    return res


@router.get("/api/me")
def me(user: dict = Depends(auth.current_user_pending_ok)):
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
    # Solo se agrupan ráfagas de TEXTO en chats privados. Un adjunto agrupado
    # perdería el archivo (el buffer solo guarda texto) y un chat de grupo se
    # saltaría el filtro de allows_chat: ambos van por process_update.
    if (parsed and not parsed.get("media") and (parsed.get("text") or "").strip()
            and telegram.allows_chat(parsed["chat_type"])
            and debounce.buffer_message(
                tenant["id"],
                "telegram",
                f"tg:{parsed['chat_id']}",
                parsed["text"],
                {"chat_id": parsed["chat_id"]},
            )):
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


# ---------- diagnóstico del LLM ----------
@router.get("/api/diagnostics/llm")
async def diagnostics_llm(user: dict = Depends(auth.require("config:read"))):
    """¿El modelo configurado sigue existiendo en el proveedor? Si no, el bot
    responde 400 en cada turno y deriva todo a un asesor. Sin gasto de tokens."""
    return await llm.probe(T.get_config())
