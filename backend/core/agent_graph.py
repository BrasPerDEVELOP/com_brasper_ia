"""Orquestador LangGraph para conversaciones multi-tenant."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from . import auth, calendar_adapter, connectors, db, lead_onboarding, llm, observability, policies, quotes, tool_router, util


# Canales externos a los que el bot NUNCA debe derivar: con takeover el asesor
# atiende en el MISMO chat. Se filtran tanto del historial que entra al LLM como
# de su salida, para que ni siquiera un historial viejo contaminado lo induzca.
_EXTERNAL_CHANNELS_RE = re.compile(
    r"\b(whats?app|wa\.me|api\.whatsapp|instagram|facebook|messenger|fb\.me|t\.me)\b",
    re.IGNORECASE)
_DANGLING_CONNECTOR_RE = re.compile(r"[\s,;:]*\b([oOyY]|o si prefieres|si prefieres)\b[\s,;:]*$",
                                    re.IGNORECASE)


def sanitize_no_external_channels(text: str) -> str:
    """Elimina cualquier oferta de derivar a un canal externo (WhatsApp, redes),
    conservando el resto del mensaje. Si el mensaje quedaba solo en eso, devuelve
    una invitación a seguir en el mismo chat."""
    if not text or not _EXTERNAL_CHANNELS_RE.search(text):
        return text
    # Trocea en oraciones/líneas y descarta las que citen un canal externo.
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text)
    kept = [p for p in pieces if p.strip() and not _EXTERNAL_CHANNELS_RE.search(p)]
    out = _DANGLING_CONNECTOR_RE.sub("", " ".join(kept)).strip()
    if not out:
        out = ("Seguimos por aquí mismo 🙂 Cuando quieras avanzar con tu envío escribe "
               "*continuar* y un asesor te atenderá aquí.")
    return out


class AgentState(TypedDict, total=False):
    tenant: dict
    tenant_id: str
    user_ref: str
    text: str
    channel: str
    conversation_id: str | None
    user_media: dict | None
    cid: str
    conv_status: str | None
    paused: bool
    analysis: dict
    system_prompt: str
    messages: list[dict]
    llm_result: dict
    tool_request: dict | None
    tool_result: dict | None
    quote_pending: bool
    appointment_request: dict | None
    appointment: dict | None
    response: str
    handoff: bool
    usage: dict | None
    new_lead: bool


# Intención de PROCEDER con el envío tras una cotización (checkout). Deben ser
# frases inequívocas: no "enviar"/"transferir" sueltas (esas son pedir cotización).
_DEFAULT_CHECKOUT_KEYWORDS = (
    # Formas escuetas que el propio CTA de la cotización invita a escribir.
    "continuar", "proceder", "confirmar",
    "quiero proceder", "deseo continuar", "quiero continuar", "continuar con el envio",
    "continuar con el envío", "confirmar el envio", "confirmar el envío", "confirmar operacion",
    "confirmar la operacion", "como pago", "cómo pago", "donde pago", "dónde pago",
    "quiero pagar", "voy a pagar", "realizar el pago", "hacer el pago", "como deposito",
    "cómo deposito", "quiero depositar", "como hago el envio", "cómo hago el envío",
    "acepto la cotizacion", "acepto la cotización", "quiero hacer el envio", "quiero hacer el envío",
    "quero pagar", "como faço o pagamento", "i want to proceed", "how do i pay",
)


def _handoff_hit(tenant: dict, text: str) -> bool:
    kws = tenant.get("handoff", {}).get("keywords", [])
    low = text.lower()
    return any(k in low for k in kws)


def _checkout_hit(tenant: dict, text: str) -> bool:
    kws = tenant.get("handoff", {}).get("checkout_keywords") or _DEFAULT_CHECKOUT_KEYWORDS
    low = text.lower()
    return any(k in low for k in kws)


def _handoff_reply(tenant: dict, checkout: bool = False) -> str:
    h = tenant.get("handoff", {})
    if checkout:
        default = ("¡Perfecto! Un asesor te contactará aquí mismo para completar tu envío 🙌 "
                   "En breve te escribe.")
        msg = h.get("checkout_message", default)
    else:
        msg = h.get("message", "Te conecto con un asesor: https://wa.me/{number}")
    return msg.replace("{number}", h.get("number", ""))


def _language_line(language: str) -> str:
    names = {"es": "espanol", "pt": "portugues", "en": "ingles"}
    return f"Responde SIEMPRE en el idioma del usuario ({names.get(language, language)})."


def start_conversation(state: AgentState) -> dict[str, Any]:
    tenant = state["tenant"]
    tid = tenant["id"]
    cid = db.get_or_create_conversation(
        tid,
        state["user_ref"],
        state.get("channel", "webchat"),
        state.get("conversation_id"),
    )
    # Estado ANTES de este mensaje: si ya está en 'handoff', un humano la atiende
    # y el bot no debe responder (se registra el mensaje para que el asesor lo vea).
    prev_status = db.conversation_status(tid, cid)
    # Lead nuevo: primer mensaje de este usuario (antes de guardarlo).
    new_lead = db.is_first_contact(tid, state["user_ref"])
    db.add_message(tid, cid, "user", state["text"], media=state.get("user_media"))
    # Fase 3: guarda datos base del lead (canal). Idioma/ruta/monto se completan luego.
    db.merge_lead_data(tid, cid, {"canal": state.get("channel", "webchat")})
    observability.event("message.received", tenant_id=tid, channel=state.get("channel", "webchat"), conversation_id=cid)
    if new_lead:
        observability.event("lead.new", tenant_id=tid, conversation_id=cid, channel=state.get("channel", "webchat"))
    return {"tenant_id": tid, "cid": cid, "conv_status": prev_status, "new_lead": new_lead}


def pre_process(state: AgentState) -> dict[str, Any]:
    analysis = policies.pre_process(state["text"])
    tenant = state["tenant"]
    is_calendar = calendar_adapter.enabled(tenant) and calendar_adapter.has_intent(state["text"])
    is_quote = quotes.has_intent(tenant, state["text"])
    tool_request = None if is_quote else tool_router.select_tool(tenant, state["text"])
    checkout = (not is_quote) and _checkout_hit(tenant, state["text"])
    lead = db.get_lead_data(tenant["id"], state["cid"])
    onboarding = lead_onboarding.needs_onboarding(
        lead, new_lead=bool(state.get("new_lead")), checkout=checkout, text=state["text"]
    )
    return {
        "analysis": {
            **analysis,
            "handoff": _handoff_hit(tenant, state["text"]),
            "checkout": checkout,
            "onboarding": onboarding,
            "calendar": is_calendar,
            "quote": is_quote,
            "tool": bool(tool_request),
        },
        "tool_request": tool_request,
    }


def route_after_preprocess(state: AgentState) -> str:
    # Conversación ya en manos de un asesor humano -> el bot no responde.
    if state.get("conv_status") == "handoff":
        return "paused"
    analysis = state.get("analysis", {})
    if analysis.get("onboarding"):
        return "onboarding"
    if analysis.get("handoff"):
        return "handoff"
    if analysis.get("calendar"):
        return "calendar"
    if analysis.get("quote"):
        return "quote"
    # Cliente quiere proceder con el envío/pago -> lo toma un asesor humano.
    if analysis.get("checkout"):
        return "deposit"
    if analysis.get("tool"):
        return "tool"
    return "llm"


def handle_onboarding(state: AgentState) -> dict[str, Any]:
    result = lead_onboarding.process(
        state["tenant"], state["cid"], state["text"], state.get("channel", "webchat"),
        state["user_ref"], new_lead=bool(state.get("new_lead")),
    )
    db.add_message(state["tenant"]["id"], state["cid"], "assistant", result["response"])
    if result.get("handoff"):
        db.set_conversation_status(state["tenant"]["id"], state["cid"], "handoff")
        auth.derive_to_advisor(state["tenant"]["id"], state["cid"])
    return result


def handle_deposit_accounts(state: AgentState) -> dict[str, Any]:
    tenant, cid = state["tenant"], state["cid"]
    lead = db.get_lead_data(tenant["id"], cid)
    reply, accounts = lead_onboarding.deposit_accounts_reply(tenant, lead)
    db.add_message(tenant["id"], cid, "assistant", reply)
    if accounts:
        db.merge_lead_data(tenant["id"], cid, {
            "commercial_stage": "awaiting_deposit",
            "deposit_accounts_shown": [str(item.get("id")) for item in accounts],
            "deposit_accounts_shown_at": util.now_iso(),
        })
    return {"response": reply, "handoff": False, "usage": None}


def route_after_tool(state: AgentState) -> str:
    # Si la herramienta pidio datos faltantes ya hay respuesta -> terminar.
    # Si se ejecuto, pasar al LLM para redactar el resultado.
    return "end" if state.get("response") else "llm"


def route_after_quote(state: AgentState) -> str:
    # Cotización clara -> ya hay respuesta (END). Incompleta/ambigua -> LLM.
    return "end" if state.get("response") else "llm"


def handoff(state: AgentState) -> dict[str, Any]:
    tenant = state["tenant"]
    checkout = bool(state.get("analysis", {}).get("checkout"))
    reply = _handoff_reply(tenant, checkout=checkout)
    db.add_message(tenant["id"], state["cid"], "assistant", reply)
    db.set_conversation_status(tenant["id"], state["cid"], "handoff")
    # Derivación: asigna la conversación al asesor con menos carga (si hay).
    assigned = auth.derive_to_advisor(tenant["id"], state["cid"])
    observability.event("conversation.handoff", tenant_id=tenant["id"], conversation_id=state["cid"],
                        reason="checkout" if checkout else "keyword", assigned_to=assigned)
    return {"response": reply, "handoff": True, "usage": None}


def paused(state: AgentState) -> dict[str, Any]:
    """Conversación atendida por un asesor humano: el bot queda en silencio.
    El mensaje del usuario ya se guardó (start_conversation) para que el asesor lo vea."""
    observability.event("conversation.bot_paused", tenant_id=state["tenant"]["id"],
                        conversation_id=state["cid"])
    return {"response": "", "handoff": True, "usage": None, "paused": True}


def handle_quote(state: AgentState) -> dict[str, Any]:
    """Cotizador determinista por tenant (sin LLM): matemática del bot Brasper real.

    Solo resuelve aquí (rápido y gratis) cuando el mensaje trae monto + ambas
    monedas claras. Si viene incompleto o ambiguo (p.ej. typos como 'olesñ'),
    delega al LLM para que lo interprete y guíe con naturalidad.
    """
    tenant = state["tenant"]
    # Contexto de la última cotización (para "continuar la misma línea" cuando el
    # siguiente mensaje solo cambia el monto, p.ej. "¿y para 2000 soles?").
    _lead = db.get_lead_data(tenant["id"], state["cid"])
    _prev = None
    _ruta = str(_lead.get("ruta") or "")
    if "->" in _ruta:
        _o, _d = _ruta.split("->", 1)
        _prev = {"origin": _o.strip(), "destination": _d.strip(), "mode": _lead.get("modo")}
    request = quotes.extract_request(tenant, state["text"], prev=_prev)
    if request["missing"]:
        # Pedido de cotización incompleto: en vez de delegar al LLM (que podía
        # decir "no tengo el tipo de cambio"), respondemos una aclaración concreta
        # y determinista, pidiendo SOLO el dato faltante con opciones del corredor.
        language = state.get("analysis", {}).get("language", "es")
        reply = quotes.clarify_reply(tenant, request, language)
        db.add_message(tenant["id"], state["cid"], "assistant", reply)
        observability.event("quote.clarify", tenant_id=tenant["id"],
                            conversation_id=state["cid"], missing=request["missing"])
        return {"response": reply, "handoff": False, "usage": None}
    quote = quotes.compute(tenant, request["origin"], request["destination"],
                           request["amount"], request["mode"])
    language = state.get("analysis", {}).get("language", "es")
    reply = quotes.reply(tenant, quote, language)
    tid, cid = tenant["id"], state["cid"]
    # Fase 3: guarda en el lead los datos que produjo la cotización (visibles en el panel).
    if not quote.get("error"):
        db.merge_lead_data(tid, cid, {
            "idioma": language,
            "ruta": f"{request['origin']}->{request['destination']}",
            "modo": request["mode"],
            "monto_enviar": quote.get("amount_send"),
            "monto_recibir": quote.get("amount_receive"),
            "tasa": quote.get("rate"),
            "estado_tc": "activo",
            "aplica_promo": bool(quote.get("coupon_code")),
            "cotizado_en": util.now_iso(),
        })
    # Regla del proceso: monto alto -> lo confirma un asesor (el bot no cierra solo).
    threshold = _high_amount_threshold(tenant)
    high = (not quote.get("error")) and bool(threshold) and float(request["amount"] or 0) >= threshold
    final = reply + ("\n\n" + _high_amount_note(language) if high else "")
    db.add_message(tid, cid, "assistant", final)
    observability.event("quote.completed", tenant_id=tid, conversation_id=cid,
                        ok=not quote.get("error"), origin=request["origin"],
                        destination=request["destination"], mode=request["mode"], high_amount=high)
    if high:
        db.set_conversation_status(tid, cid, "handoff")
        assigned = auth.derive_to_advisor(tid, cid)
        observability.event("conversation.handoff", tenant_id=tid, conversation_id=cid,
                            reason="high_amount", assigned_to=assigned)
        return {"response": final, "handoff": True, "usage": None}
    return {"response": final, "handoff": False, "usage": None}


def _high_amount_threshold(tenant: dict) -> float | None:
    raw = (tenant.get("quote") or {}).get("high_amount_threshold")
    try:
        return float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


_HIGH_AMOUNT_NOTE = {
    "es": ("Por el monto de tu operación, un asesor la confirma contigo y te acompaña "
           "para completarla de forma segura. En breve te escribe 🙌"),
    "pt": ("Pelo valor da sua operação, um assessor confirma com você e te acompanha "
           "para concluí-la com segurança. Em breve te escreve 🙌"),
    "en": ("Given the amount of your operation, an advisor will confirm it with you and "
           "assist you to complete it securely. They'll write shortly 🙌"),
}


def _high_amount_note(language: str) -> str:
    return _HIGH_AMOUNT_NOTE.get(language, _HIGH_AMOUNT_NOTE["es"])


def handle_calendar(state: AgentState) -> dict[str, Any]:
    tenant = state["tenant"]
    history = db.get_history(tenant["id"], state["cid"], limit=12)
    request = calendar_adapter.extract_request(tenant, state["text"], history)
    if request["missing"]:
        reply = calendar_adapter.missing_reply(request["missing"])
        db.add_message(tenant["id"], state["cid"], "assistant", reply)
        observability.event("calendar.missing_fields", tenant_id=tenant["id"], conversation_id=state["cid"], missing=request["missing"])
        return {"appointment_request": request, "response": reply, "handoff": False, "usage": None}
    appointment = calendar_adapter.schedule(tenant, state["cid"], state["user_ref"], request["fields"])
    reply = calendar_adapter.confirmation(appointment)
    db.add_message(tenant["id"], state["cid"], "assistant", reply)
    observability.event("calendar.scheduled", tenant_id=tenant["id"], conversation_id=state["cid"], appointment_id=appointment.get("id"))
    return {
        "appointment_request": request,
        "appointment": appointment,
        "response": reply,
        "handoff": False,
        "usage": None,
    }


async def handle_tool(state: AgentState) -> dict[str, Any]:
    tenant = state["tenant"]
    request = state.get("tool_request") or {}
    if request.get("missing"):
        reply = tool_router.missing_reply(request)
        db.add_message(tenant["id"], state["cid"], "assistant", reply)
        observability.event("tool.missing_fields", tenant_id=tenant["id"], conversation_id=state["cid"], tool=request.get("tool"), missing=request.get("missing"))
        return {"response": reply, "handoff": False, "usage": None}
    result = await connectors.call_endpoint(
        tenant,
        request["connector_key"],
        request["tool"],
        request.get("variables", {}),
    )
    tool_router.persist_tool_result(tenant["id"], state["cid"], request, result)
    observability.event("tool.executed", tenant_id=tenant["id"], conversation_id=state["cid"], tool=request.get("tool"), ok=result.get("ok"), status=result.get("status"))
    # No redactamos aqui: el resultado se pasa al LLM (build_messages -> call_llm)
    # para una respuesta en lenguaje natural en vez de JSON crudo.
    return {"tool_result": result}


def build_messages(state: AgentState) -> dict[str, Any]:
    tenant = state["tenant"]
    analysis = state.get("analysis", {})
    base_prompt = tenant.get("system_prompt", "")
    lang_line = _language_line(analysis.get("language", "es"))
    system_prompt = f"{lang_line}\n{base_prompt}" if base_prompt else lang_line
    history = db.get_history(tenant["id"], state["cid"], limit=12)
    # Limpia el historial: turnos viejos del asistente pudieron ofrecer WhatsApp
    # (CTA antiguo del cotizador). Si el LLM los ve, los imita aunque el prompt lo
    # prohíba. Los saneamos ANTES de mandarlos al modelo.
    history = [
        {**m, "content": sanitize_no_external_channels(m.get("content", ""))}
        if m.get("role") == "assistant" else m
        for m in history
    ]
    messages = [{"role": "system", "content": system_prompt}] + history
    tool_result = state.get("tool_result")
    if tool_result is not None:
        req = state.get("tool_request") or {}
        data = tool_result.get("data") if isinstance(tool_result, dict) else tool_result
        payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        if len(payload) > 1500:
            payload = payload[:1500] + "..."
        if tool_result.get("ok"):
            note = (f"Consultaste la herramienta '{req.get('tool')}' de "
                    f"{req.get('connector_name')}. Datos obtenidos: {payload}. "
                    "Responde al usuario en lenguaje natural con estos datos; "
                    "no muestres JSON ni detalles tecnicos, se breve y claro.")
        else:
            note = (f"La herramienta '{req.get('tool')}' fallo "
                    f"(estado {tool_result.get('status')}). Discúlpate brevemente "
                    "y ofrece reintentar o derivar a un asesor.")
        messages.append({"role": "system", "content": note})
    if state.get("quote_pending"):
        messages.append({"role": "system", "content": (
            "El usuario quiere una cotización pero el mensaje es incompleto o ambiguo. "
            "Interpreta monedas aunque tengan errores de tipeo: 'soles'/'sol'/'olesñ'->PEN, "
            "'reales'/'real'->BRL, 'dolares'/'usd'->USD. Corredores válidos: PEN, BRL, USD "
            "entre sí. Si puedes deducir monto y ambas monedas, confírmalo y pídele que "
            "escriba exactamente 'Cotizar <monto> <ORIGEN> a <DESTINO>' (ej: Cotizar 500 BRL a PEN) "
            "para darle el número exacto. NO inventes tasas ni montos. Sé breve y cordial.")})
    return {"system_prompt": system_prompt, "messages": messages}


async def call_llm(state: AgentState) -> dict[str, Any]:
    result = await llm.chat(state["tenant"], state["messages"])
    return {"llm_result": result}


def persist_llm(state: AgentState) -> dict[str, Any]:
    tenant = state["tenant"]
    result = state["llm_result"]
    # Guard final: el LLM nunca deriva a un canal externo, pase lo que pase.
    content = sanitize_no_external_channels(result["content"])
    db.add_message(tenant["id"], state["cid"], "assistant", content)
    db.add_usage(
        tenant["id"],
        state["cid"],
        result["provider"],
        result["model"],
        result["tokens_in"],
        result["tokens_out"],
        result["cost_usd"],
    )
    observability.event("llm.completed", tenant_id=tenant["id"], conversation_id=state["cid"],
                        model=result["model"], tokens_in=result["tokens_in"],
                        tokens_out=result["tokens_out"], cost_usd=result["cost_usd"])
    return {
        "response": content,
        "handoff": False,
        "usage": {
            "tokens_in": result["tokens_in"],
            "tokens_out": result["tokens_out"],
            "cost_usd": result["cost_usd"],
            "model": result["model"],
        },
    }


@lru_cache(maxsize=1)
def graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("start_conversation", start_conversation)
    workflow.add_node("pre_process", pre_process)
    workflow.add_node("handle_onboarding", handle_onboarding)
    workflow.add_node("handle_deposit_accounts", handle_deposit_accounts)
    workflow.add_node("do_handoff", handoff)
    workflow.add_node("bot_paused", paused)
    workflow.add_node("handle_calendar", handle_calendar)
    workflow.add_node("handle_quote", handle_quote)
    workflow.add_node("handle_tool", handle_tool)
    workflow.add_node("build_messages", build_messages)
    workflow.add_node("call_llm", call_llm)
    workflow.add_node("persist_llm", persist_llm)

    workflow.set_entry_point("start_conversation")
    workflow.add_edge("start_conversation", "pre_process")
    workflow.add_conditional_edges(
        "pre_process",
        route_after_preprocess,
        {"paused": "bot_paused", "onboarding": "handle_onboarding", "deposit": "handle_deposit_accounts",
         "handoff": "do_handoff", "calendar": "handle_calendar",
         "quote": "handle_quote", "tool": "handle_tool", "llm": "build_messages"},
    )
    workflow.add_edge("handle_onboarding", END)
    workflow.add_edge("handle_deposit_accounts", END)
    workflow.add_edge("bot_paused", END)
    workflow.add_edge("do_handoff", END)
    workflow.add_edge("handle_calendar", END)
    workflow.add_conditional_edges(
        "handle_quote", route_after_quote, {"end": END, "llm": "build_messages"},
    )
    workflow.add_conditional_edges(
        "handle_tool", route_after_tool, {"end": END, "llm": "build_messages"},
    )
    workflow.add_edge("build_messages", "call_llm")
    workflow.add_edge("call_llm", "persist_llm")
    workflow.add_edge("persist_llm", END)
    return workflow.compile()


async def handle_message(tenant: dict, user_ref: str, text: str,
                         channel: str = "webchat",
                         conversation_id: str | None = None,
                         user_media: dict | None = None) -> dict:
    state = await graph().ainvoke({
        "tenant": tenant,
        "user_ref": user_ref,
        "text": text,
        "channel": channel,
        "conversation_id": conversation_id,
        "user_media": user_media,
    })
    return {
        "response": state["response"],
        "conversation_id": state["cid"],
        "handoff": state["handoff"],
        "usage": state["usage"],
        "paused": state.get("paused", False),
        "new_lead": state.get("new_lead", False),
        "banner": first_send_banner(tenant) if state.get("new_lead") else None,
    }


def first_send_banner(tenant: dict) -> dict | None:
    """Banner de 'primer envío' para leads nuevos: {text, image_url?}. Configurable
    en config.onboarding.first_send_banner; si está deshabilitado, None."""
    cfg = (tenant.get("onboarding") or {}).get("first_send_banner") or {}
    if cfg.get("enabled") is False:
        return None
    text = cfg.get("text")
    image_url = cfg.get("image_url")
    if not text and not image_url:
        return None
    return {"text": text or "", "image_url": image_url or None}
