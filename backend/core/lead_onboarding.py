"""Onboarding determinístico de clientes Brasper.

Recopila identidad de forma progresiva, sincroniza el usuario y muestra cuentas
oficiales. Nunca crea transacciones ni cuentas bancarias del cliente.
"""
from __future__ import annotations

import re
from typing import Any

from core import tenants as T
from . import brasper_api, db, util


_DOC_TYPES = {
    "dni": "dni", "ce": "ce", "carnet extranjeria": "ce",
    "carné extranjería": "ce", "cpf": "cpf", "cnpj": "cnpj",
    "ruc": "ruc", "pasaporte": "passport", "passport": "passport",
}
_SKIP_EMAIL = {"omitir", "no tengo", "sin correo", "saltar", "ninguno", "no"}


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def phone_from_channel(channel: str, user_ref: str) -> tuple[str, str] | None:
    if channel != "whatsapp" or not user_ref.startswith("wa:"):
        return None
    raw = _digits(user_ref[3:])
    if raw.startswith("51") and len(raw) > 9:
        return "+51", raw[2:]
    if raw.startswith("55") and len(raw) > 10:
        return "+55", raw[2:]
    return ("+51", raw) if raw else None


def _parse_phone(text: str) -> tuple[str, str] | None:
    raw = _digits(text)
    if text.strip().startswith("+") and raw.startswith("55"):
        return "+55", raw[2:]
    if text.strip().startswith("+") and raw.startswith("51"):
        return "+51", raw[2:]
    if len(raw) == 9:
        return "+51", raw
    if len(raw) in {10, 11}:
        return "+55", raw
    return None


def _next_prompt(stage: str) -> str:
    prompts = {
        "full_name": ("¡Buen día! Bienvenido a Brasper Transferencias 🇵🇪🇧🇷✨\n"
                      "Puedes indicarme tu nombre completo o decirme directamente "
                      "cuánto deseas enviar."),
        "document_type": "¿Qué tipo de documento tienes? Puedes responder: DNI, CE, CPF, CNPJ, RUC o pasaporte.",
        "document_number": "Escribe el número de tu documento, por favor.",
        "phone": "Compárteme tu teléfono con código de país, por ejemplo +51 999999999 o +55 11999999999.",
        "email": "Si deseas, escribe tu correo. También puedes responder *omitir*; es opcional.",
    }
    return prompts[stage]


def needs_onboarding(lead: dict, *, new_lead: bool, checkout: bool, text: str) -> bool:
    greeting = util.normalize_text(text).strip("!¡., ") in {
        "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "oi", "ola", "hello", "hi",
    }
    if new_lead and greeting:
        return True
    if checkout:
        return not bool(lead.get("brasper_user_id"))
    return lead.get("commercial_stage") in {"awaiting_name", "collecting_identity"}


def _client_updates(client: dict) -> dict[str, Any]:
    return {
        "brasper_user_id": str(client.get("id")),
        "brasper_user_created": False,
        "nombres": client.get("names"),
        "apellidos": client.get("lastnames"),
        "tipo_documento": client.get("document_type"),
        "document_verified": bool(client.get("document_verified")),
        "codigo_telefono": client.get("code_phone"),
        "telefono": str(client.get("phone") or ""),
        "commercial_stage": "client_synced",
        "onboarding_field": "complete",
        "client_synced_at": util.now_iso(),
    }


def recognize_by_phone(channel: str, user_ref: str) -> dict:
    tenant = T.get_config()
    tenant_id = tenant["id"]
    detected = phone_from_channel(channel, user_ref)
    if not detected:
        return {"ok": True, "found": False}
    result = brasper_api.find_client(tenant, phone=detected[1], code_phone=detected[0])
    if not result.get("ok"):
        return {"ok": False, "found": False}
    client = result.get("data")
    if not client:
        return {"ok": True, "found": False, "phone": detected}
    return {"ok": True, "found": True, "updates": _client_updates(client)}


def _initial_stage(lead: dict, channel: str, user_ref: str, *, checkout: bool) -> tuple[str, dict]:
    updates: dict[str, Any] = {}
    detected = phone_from_channel(channel, user_ref)
    if detected and not lead.get("telefono"):
        updates.update({"codigo_telefono": detected[0], "telefono": detected[1]})
    if not checkout:
        updates["commercial_stage"] = "awaiting_name"
        stage = "full_name" if not lead.get("nombres") else "identified"
        updates["onboarding_field"] = stage
        return stage, updates

    updates["commercial_stage"] = "collecting_identity"
    required = ("full_name", "document_type", "document_number", "phone")
    mapping = {
        "full_name": "nombres", "document_type": "tipo_documento",
        "document_number": "document_verified", "phone": "telefono",
    }
    merged = {**lead, **updates}
    stage = next((item for item in required if not merged.get(mapping[item])), "sync")
    updates["onboarding_field"] = stage
    return stage, updates


def _consume(stage: str, text: str) -> tuple[dict, str | None]:
    value = text.strip()
    if stage == "full_name":
        parts = value.split()
        if len(parts) < 2 or any(ch.isdigit() for ch in value):
            return {}, ("Puedes indicarme tu nombre completo o, si prefieres cotizar primero, "
                        "dime cuánto deseas enviar y en qué moneda.")
        split_at = max(1, len(parts) // 2)
        return {"nombres": " ".join(parts[:split_at])[:100],
                "apellidos": " ".join(parts[split_at:])[:100]}, None
    if stage == "document_type":
        normalized = util.normalize_text(value)
        doc_type = _DOC_TYPES.get(normalized)
        if not doc_type:
            return {}, "No reconocí el tipo. Responde DNI, CE, CPF, CNPJ, RUC o pasaporte."
        return {"tipo_documento": doc_type}, None
    if stage == "document_number":
        number = _digits(value)
        if len(number) < 3 or len(number) > 20:
            return {}, "El número de documento no parece válido. Revísalo y envíalo nuevamente."
        return {"numero_documento": number, "document_verified": True}, None
    if stage == "phone":
        parsed = _parse_phone(value)
        if not parsed:
            return {}, "No reconocí el teléfono. Incluye el código de país, por ejemplo +51 o +55."
        
        # Guardar en customers
        phone_str = f"{parsed[0]}{parsed[1]}"
        cust = db.get_or_create_customer(phone_str)
        
        return {"codigo_telefono": parsed[0], "telefono": parsed[1], "customer_id_internal": cust["id"]}, None
    if stage == "email":
        if value.lower() in _SKIP_EMAIL:
            return {"correo": None, "correo_procesado": True}, None
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            return {}, "El correo no parece válido. Corrígelo o responde *omitir*."
        return {"correo": value.lower()[:255], "correo_procesado": True}, None
    return {}, None


def process(cid: str, text: str, channel: str, user_ref: str,
            *, new_lead: bool, checkout: bool = False) -> dict:
    tenant = T.get_config()
    tenant_id = tenant["id"]
    lead = db.get_lead_data(cid)
    # Una vez iniciada la identificación para pagar, las respuestas siguientes
    # ("DNI", número, teléfono) ya no contienen la palabra "continuar".
    checkout = checkout or lead.get("commercial_stage") == "collecting_identity"
    if (new_lead or checkout) and not lead.get("client_lookup_done"):
        recognition = recognize_by_phone(channel, user_ref)
        lookup_updates: dict[str, Any] = {"client_lookup_done": True}
        detected = phone_from_channel(channel, user_ref)
        if detected:
            lookup_updates.update({"codigo_telefono": detected[0], "telefono": detected[1]})
            phone_str = f"{detected[0]}{detected[1]}"
            cust = db.get_or_create_customer(phone_str)
            with db.connect() as con:
                con.execute("UPDATE conversations SET customer_id=? WHERE id=?", (cust["id"], cid))
        if recognition.get("found"):
            lookup_updates.update(recognition["updates"])
        lead = db.merge_lead_data(cid, lookup_updates)
        if recognition.get("found"):
            if checkout:
                return {
                    "response": "Encontré tu perfil de Brasper ✅. Continuamos con tu envío.",
                    "handoff": False, "usage": None, "ready_for_deposit": True,
                }
            name = str(lead.get("nombres") or "").split()[0]
            return {
                "response": (f"¡Hola, {name}! Qué gusto atenderte nuevamente en Brasper 😊\n"
                             "¿Cuánto deseas enviar hoy?"),
                "handoff": False, "usage": None,
            }

    stage = lead.get("onboarding_field")
    if not stage or stage in {"complete", "identified"}:
        stage, updates = _initial_stage(lead, channel, user_ref, checkout=checkout)
        lead = db.merge_lead_data(cid, updates)
        if stage == "identified":
            return {"response": "¿Cuánto deseas enviar y en qué moneda?", "handoff": False, "usage": None}
        return {"response": _next_prompt(stage), "handoff": False, "usage": None}

    updates, error = _consume(stage, text)
    if error:
        return {"response": error, "handoff": False, "usage": None}
    if updates:
        # Check if we got a customer_id_internal
        cust_id = updates.pop("customer_id_internal", None)
        if cust_id:
            with db.connect() as con:
                con.execute("UPDATE conversations SET customer_id=? WHERE id=?", (cust_id, cid))
        
        # Also, if we have identity info, update the customer record if customer_id exists
        conv = db.get_conversation(cid)
        if conv and conv.get("customer_id"):
            c_updates = {}
            if "tipo_documento" in updates:
                c_updates["document_type"] = updates["tipo_documento"]
            if "numero_documento" in updates:
                c_updates["document_number"] = updates["numero_documento"]
            if "nombres" in updates or "apellidos" in updates:
                c_updates["name"] = f"{lead.get('nombres') or ''} {lead.get('apellidos') or ''}".strip()
            if c_updates:
                db.update_customer(conv["customer_id"], c_updates)
                
        lead = db.merge_lead_data(cid, updates)

    if stage == "full_name":
        full_name = f"{lead.get('nombres') or ''} {lead.get('apellidos') or ''}".strip()
        found = brasper_api.find_client(tenant, full_name=full_name)
        if found.get("ok") and found.get("data"):
            lead = db.merge_lead_data(cid, _client_updates(found["data"]))
            name = str(lead.get("nombres") or "").split()[0]
            return {"response": f"¡Mucho gusto, {name}! 🙌 ¿Cuánto deseas enviar?",
                    "handoff": False, "usage": None}
        db.merge_lead_data(cid, {
            "client_status": "new" if found.get("ok") else "unverified",
            "commercial_stage": "identified", "onboarding_field": "identified",
        })
        if not checkout:
            return {
                "response": (f"¡Mucho gusto, {lead.get('nombres')}! 🙌 "
                             "Ahora dime cuánto deseas enviar y en qué moneda."),
                "handoff": False, "usage": None,
                "banner": first_send_banner() if found.get("ok") else None,
            }

    next_stage, stage_updates = _initial_stage(lead, channel, user_ref, checkout=checkout)
    lead = db.merge_lead_data(cid, stage_updates)
    if next_stage != "sync":
        return {"response": _next_prompt(next_stage), "handoff": False, "usage": None}

    result = brasper_api.upsert_client(tenant, lead)
    if not result.get("ok"):
        db.merge_lead_data(cid, {"commercial_stage": "sync_error"})
        return {
            "response": "Guardé tus datos, pero no pude sincronizarlos con Brasper ahora. Un asesor lo revisará aquí mismo.",
            "handoff": True, "usage": None,
        }
    data = result["data"]
    db.merge_lead_data(cid, {
        "brasper_user_id": str(data["id"]),
        "brasper_user_created": bool(data.get("created")),
        "commercial_stage": "client_synced",
        "onboarding_field": "complete",
        "client_synced_at": util.now_iso(),
    })
    action = "registrado" if data.get("created") else "encontrado y actualizado"
    return {
        "response": (f"Listo, tu perfil fue {action} en Brasper ✅. "
                     + ("Continuamos con tu envío." if checkout else "Ya puedes solicitar tu cotización.")),
        "handoff": False, "usage": None,
        "ready_for_deposit": checkout,
    }


def first_send_banner() -> dict | None:
    tenant = T.get_config()
    tenant_id = tenant["id"]
    cfg = (tenant.get("onboarding") or {}).get("first_send_banner") or {}
    if cfg.get("enabled") is False:
        return None
    text, image_url = cfg.get("text"), cfg.get("image_url")
    if not text and not image_url:
        return None
    return {"text": text or "", "image_url": image_url or None}


def deposit_accounts_reply(lead: dict) -> tuple[str, list[dict]]:
    tenant = T.get_config()
    tenant_id = tenant["id"]
    route = str(lead.get("ruta") or "")
    currency = route.split("->", 1)[0].upper() if "->" in route else ""
    if not currency:
        return "Primero necesito una cotización para saber en qué moneda realizarás el depósito.", []
    result = brasper_api.deposit_accounts(tenant, currency)
    accounts = result.get("data") if result.get("ok") else []
    if not accounts:
        return ("¡Perfecto! 😊 Un asesor se comunicará contigo en unos instantes "
                "para ayudarte a continuar."), []
    lines = [f"Estas son las cuentas oficiales de Brasper para depositar en {currency}:"]
    for item in accounts:
        detail = item.get("account") or (f"PIX: {item.get('pix')}" if item.get("pix") else "")
        lines.append(f"• {item.get('bank')} — {item.get('company')} — {detail}")
    lines.append("Cuando realices el depósito, envía el comprobante por este chat. Un agente comercial verificará el pago y registrará la operación.")
    return "\n".join(lines), accounts
