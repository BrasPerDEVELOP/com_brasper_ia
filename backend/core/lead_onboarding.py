"""Onboarding determinístico de clientes Brasper.

Recopila identidad, sincroniza el usuario y muestra cuentas oficiales. Nunca crea
transacciones ni cuentas bancarias del cliente.
"""
from __future__ import annotations

import re
from typing import Any

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
        "names": "Para registrarte de forma segura, dime tus nombres.",
        "lastnames": "Gracias. Ahora dime tus apellidos.",
        "document_type": "¿Qué tipo de documento tienes? Puedes responder: DNI, CE, CPF, CNPJ, RUC o pasaporte.",
        "document_number": "Escribe el número de tu documento, por favor.",
        "phone": "Compárteme tu teléfono con código de país, por ejemplo +51 999999999 o +55 11999999999.",
        "email": "Si deseas, escribe tu correo. También puedes responder *omitir*; es opcional.",
    }
    return prompts[stage]


def needs_onboarding(lead: dict, *, new_lead: bool, checkout: bool, text: str) -> bool:
    if lead.get("brasper_user_id"):
        return False
    greeting = util.normalize_text(text).strip("!¡., ") in {
        "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "oi", "ola", "hello", "hi",
    }
    return (new_lead and greeting) or lead.get("commercial_stage") == "collecting_identity" or checkout


def _initial_stage(lead: dict, channel: str, user_ref: str) -> tuple[str, dict]:
    updates: dict[str, Any] = {"commercial_stage": "collecting_identity"}
    detected = phone_from_channel(channel, user_ref)
    if detected and not lead.get("telefono"):
        updates.update({"codigo_telefono": detected[0], "telefono": detected[1]})
    required = ("names", "lastnames", "document_type", "document_number", "phone", "email")
    mapping = {
        "names": "nombres", "lastnames": "apellidos", "document_type": "tipo_documento",
        "document_number": "numero_documento", "phone": "telefono", "email": "correo_procesado",
    }
    merged = {**lead, **updates}
    stage = next((item for item in required if not merged.get(mapping[item])), "sync")
    updates["onboarding_field"] = stage
    return stage, updates


def _consume(stage: str, text: str) -> tuple[dict, str | None]:
    value = text.strip()
    if stage == "names":
        if len(value) < 2 or any(ch.isdigit() for ch in value):
            return {}, "Escribe tus nombres usando letras, por favor."
        return {"nombres": value[:100]}, None
    if stage == "lastnames":
        if len(value) < 2 or any(ch.isdigit() for ch in value):
            return {}, "Escribe tus apellidos usando letras, por favor."
        return {"apellidos": value[:100]}, None
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
        return {"numero_documento": number}, None
    if stage == "phone":
        parsed = _parse_phone(value)
        if not parsed:
            return {}, "No reconocí el teléfono. Incluye el código de país, por ejemplo +51 o +55."
        return {"codigo_telefono": parsed[0], "telefono": parsed[1]}, None
    if stage == "email":
        if value.lower() in _SKIP_EMAIL:
            return {"correo": None, "correo_procesado": True}, None
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            return {}, "El correo no parece válido. Corrígelo o responde *omitir*."
        return {"correo": value.lower()[:255], "correo_procesado": True}, None
    return {}, None


def process(tenant: dict, cid: str, text: str, channel: str, user_ref: str,
            *, new_lead: bool) -> dict:
    lead = db.get_lead_data(tenant["id"], cid)
    stage = lead.get("onboarding_field")
    if not stage:
        stage, updates = _initial_stage(lead, channel, user_ref)
        lead = db.merge_lead_data(tenant["id"], cid, updates)
        return {"response": _next_prompt(stage), "handoff": False, "usage": None}

    updates, error = _consume(stage, text)
    if error:
        return {"response": error, "handoff": False, "usage": None}
    if updates:
        lead = db.merge_lead_data(tenant["id"], cid, updates)

    next_stage, stage_updates = _initial_stage(lead, channel, user_ref)
    lead = db.merge_lead_data(tenant["id"], cid, stage_updates)
    if next_stage != "sync":
        return {"response": _next_prompt(next_stage), "handoff": False, "usage": None}

    result = brasper_api.upsert_client(tenant, lead)
    if not result.get("ok"):
        db.merge_lead_data(tenant["id"], cid, {"commercial_stage": "sync_error"})
        return {
            "response": "Guardé tus datos, pero no pude sincronizarlos con Brasper ahora. Un asesor lo revisará aquí mismo.",
            "handoff": True, "usage": None,
        }
    data = result["data"]
    db.merge_lead_data(tenant["id"], cid, {
        "brasper_user_id": str(data["id"]),
        "brasper_user_created": bool(data.get("created")),
        "commercial_stage": "client_synced",
        "onboarding_field": "complete",
        "client_synced_at": util.now_iso(),
    })
    action = "registrado" if data.get("created") else "encontrado y actualizado"
    return {
        "response": f"Listo, tu perfil fue {action} en Brasper ✅. Ya puedes solicitar tu cotización.",
        "handoff": False, "usage": None,
    }


def deposit_accounts_reply(tenant: dict, lead: dict) -> tuple[str, list[dict]]:
    route = str(lead.get("ruta") or "")
    currency = route.split("->", 1)[0].upper() if "->" in route else ""
    if not currency:
        return "Primero necesito una cotización para saber en qué moneda realizarás el depósito.", []
    result = brasper_api.deposit_accounts(tenant, currency)
    accounts = result.get("data") if result.get("ok") else []
    if not accounts:
        return "No pude consultar las cuentas oficiales de Brasper. Un asesor te ayudará aquí mismo.", []
    lines = [f"Estas son las cuentas oficiales de Brasper para depositar en {currency}:"]
    for item in accounts:
        detail = item.get("account") or (f"PIX: {item.get('pix')}" if item.get("pix") else "")
        lines.append(f"• {item.get('bank')} — {item.get('company')} — {detail}")
    lines.append("Cuando realices el depósito, envía el comprobante por este chat. Un agente comercial verificará el pago y registrará la operación.")
    return "\n".join(lines), accounts
