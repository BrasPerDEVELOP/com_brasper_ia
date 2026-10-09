"""Onboarding determinístico de clientes Brasper.

Recopila identidad de forma progresiva, sincroniza el usuario y muestra cuentas
oficiales. Nunca crea transacciones ni cuentas bancarias del cliente.
"""
from __future__ import annotations

import re
from typing import Any

from core import tenants as T
from . import brasper_api, db, util, idempotency, tool_contracts
from .onboarding_copy import text as copy


_DOC_TYPES = {
    "dni": "dni", "ce": "ce", "carnet extranjeria": "ce",
    "carné extranjería": "ce", "cpf": "cpf", "cnpj": "cnpj",
    "ruc": "ruc", "pasaporte": "passport", "passport": "passport", "passaporte": "passport",
}
_SKIP_EMAIL = {"omitir", "no tengo", "sin correo", "saltar", "ninguno", "no", "pular", "nao", "nao tenho", "sem email"}


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def phone_from_channel(channel: str, user_ref: str) -> tuple[str, str] | None:
    if channel != "whatsapp" or not user_ref.startswith("wa:"):
        return None
    raw = user_ref[3:]
    if not re.fullmatch(r"\+?[0-9]+", raw):
        return None
    raw = raw.lstrip("+")
    if raw.startswith("51") and len(raw) == 11:
        return "+51", raw[2:]
    if raw.startswith("55") and len(raw) in {12, 13}:
        return "+55", raw[2:]
    return None


def _parse_phone(text: str) -> tuple[str, str] | None:
    raw = _digits(text)
    if text.strip().startswith("+"):
        return phone_from_channel("whatsapp", f"wa:{raw}")
    if len(raw) == 9:
        return "+51", raw
    if len(raw) in {10, 11}:
        return "+55", raw
    return None


def _next_prompt(stage: str, language: str = "es") -> str:
    return copy(stage, language)


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
        "is_first_transfer": client.get("is_first_transfer") if isinstance(client.get("is_first_transfer"), bool) else None,
        "identity_source": "channel_phone_match",
        "nombres": client.get("names"),
        "apellidos": client.get("lastnames"),
        "tipo_documento": client.get("document_type"),
        "document_verified": False,
        "document_recorded": bool(client.get("document_recorded") or client.get("document_verified")),
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
    if (not client.get("id") or str(client.get("phone") or "") != detected[1]
            or client.get("code_phone") != detected[0]):
        return {"ok": False, "found": False}
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
        "document_number": "document_recorded", "phone": "telefono",
    }
    merged = {**lead, **updates}
    stage = next((item for item in required if not merged.get(mapping[item])), "sync")
    updates["onboarding_field"] = stage
    return stage, updates


def _consume(stage: str, text: str, language: str = "es", document_type: str = "") -> tuple[dict, str | None]:
    value = text.strip()
    if stage == "full_name":
        parts = value.split()
        if len(parts) < 2 or any(ch.isdigit() for ch in value):
            return {}, copy("invalid_name", language)
        split_at = max(1, len(parts) // 2)
        return {"nombres": " ".join(parts[:split_at])[:100],
                "apellidos": " ".join(parts[split_at:])[:100]}, None
    if stage == "document_type":
        normalized = util.normalize_text(value)
        doc_type = _DOC_TYPES.get(normalized)
        if not doc_type:
            return {}, copy("invalid_type", language)
        return {"tipo_documento": doc_type}, None
    if stage == "document_number":
        number = re.sub(r"[\s.-]", "", value).upper()
        pattern = r"[A-Z0-9]{3,20}" if document_type in {"passport", "ce"} else r"[0-9]{3,20}"
        if not re.fullmatch(pattern, number):
            return {}, copy("invalid_document", language)
        return {"numero_documento": number, "document_recorded": True,
                "document_verified": False}, None
    if stage == "phone":
        parsed = _parse_phone(value)
        if not parsed:
            return {}, copy("invalid_phone", language)
        
        return {"codigo_telefono": parsed[0], "telefono": parsed[1],
                "identity_source": "self_reported"}, None
    if stage == "email":
        if util.normalize_text(value) in _SKIP_EMAIL:
            return {"correo": None, "correo_procesado": True}, None
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            return {}, copy("invalid_email", language)
        return {"correo": value.lower()[:255], "correo_procesado": True}, None
    return {}, None


def process(cid: str, text: str, channel: str, user_ref: str,
            *, new_lead: bool, checkout: bool = False) -> dict:
    tenant = T.get_config()
    tenant_id = tenant["id"]
    lead = db.get_lead_data(cid)
    language = lead.get("idioma", "es")
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
                    "response": copy("found", language),
                    "handoff": False, "usage": None, "ready_for_deposit": True,
                }
            name = (str(lead.get("nombres") or "").split() or [""])[0]
            return {
                "response": copy("returning", language, name=name),
                "handoff": False, "usage": None,
            }

    stage = lead.get("onboarding_field")
    if not stage or stage in {"complete", "identified"}:
        stage, updates = _initial_stage(lead, channel, user_ref, checkout=checkout)
        lead = db.merge_lead_data(cid, updates)
        if stage == "identified":
            return {"response": copy("amount", language), "handoff": False, "usage": None}
        if stage != "sync":
            return {"response": _next_prompt(stage, language), "handoff": False, "usage": None}

    updates, error = _consume(stage, text, language, lead.get("tipo_documento", ""))
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
                merged = {**lead, **updates}
                c_updates["name"] = f"{merged.get('nombres') or ''} {merged.get('apellidos') or ''}".strip()
            if c_updates:
                db.update_customer(conv["customer_id"], c_updates)
                
        lead = db.merge_lead_data(cid, updates)

    if stage == "full_name":
        # A name is conversational context, never proof of identity or first transfer.
        db.merge_lead_data(cid, {
            "client_status": "unverified",
            "commercial_stage": "identified", "onboarding_field": "identified",
        })
        if not checkout:
            return {
                "response": copy("named", language, name=lead.get("nombres") or ""),
                "handoff": False, "usage": None,
                "banner": None,
            }

    next_stage, stage_updates = _initial_stage(lead, channel, user_ref, checkout=checkout)
    lead = db.merge_lead_data(cid, stage_updates)
    if next_stage != "sync":
        return {"response": _next_prompt(next_stage, language), "handoff": False, "usage": None}

    # Alta/actualización vía contrato tipado con clave de idempotencia (misma persona =
    # mismo resultado) y verificación tras timeout (consultar antes de repetir la escritura).
    idem = idempotency.make_key("client.upsert", lead.get("codigo_telefono"), lead.get("telefono"),
                                lead.get("tipo_documento"), lead.get("numero_documento"))
    run = tool_contracts.run("client.upsert", {"lead": lead},
                             lambda lead: brasper_api.upsert_client(tenant, lead), idempotency_key=idem)
    if run.get("ok"):
        result = run["data"]
    else:
        # A lookup by phone cannot establish that a timed-out write actually succeeded.
        # The tool contract keeps the reservation and stores any late result for replay.
        result = {"ok": False, "error": run.get("detail")}
    if not result.get("ok"):
        db.merge_lead_data(cid, {"commercial_stage": "sync_error"})
        return {
            "response": copy("sync_error", language),
            "handoff": True, "usage": None,
        }
    data = result["data"]
    db.merge_lead_data(cid, {
        "brasper_user_id": str(data["id"]),
        "brasper_user_created": bool(data.get("created")),
        "is_first_transfer": data.get("is_first_transfer") if isinstance(data.get("is_first_transfer"), bool) else None,
        "identity_source": "channel_phone_match" if phone_from_channel(channel, user_ref) ==
                           (lead.get("codigo_telefono"), lead.get("telefono")) else "self_reported",
        "commercial_stage": "client_synced",
        "onboarding_field": "complete",
        "client_synced_at": util.now_iso(),
    })
    return {
        "response": copy("created" if data.get("created") else "identified", language) + copy("continue" if checkout else "quote", language),
        "handoff": False, "usage": None,
        "ready_for_deposit": checkout,
    }


def refresh_history(cid: str, channel: str, user_ref: str) -> dict | None:
    """Refresh eligibility only for a provider-phone link, never a name/typed phone."""
    lead = db.get_lead_data(cid)
    detected = phone_from_channel(channel, user_ref)
    valid_link = (detected is not None and lead.get("identity_source") == "channel_phone_match"
                  and detected == (lead.get("codigo_telefono"), str(lead.get("telefono") or ""))
                  and bool(lead.get("brasper_user_id")))
    invalid = {"history_status": "identity_unverified", "first_transfer_eligible": None,
               "completed_transfers": None, "pending_transfers": None, "history_checked_at": None}
    if not valid_link:
        db.merge_lead_data(cid, invalid, allow_null=True)
        return None
    run = tool_contracts.run("client.history", {
        "user_id": lead["brasper_user_id"], "code_phone": detected[0], "phone": detected[1],
    }, lambda **kwargs: brasper_api.client_history(T.get_config(), **kwargs))
    result = run.get("data") if run.get("ok") else None
    data = result.get("data") if isinstance(result, dict) and result.get("ok") else None
    if isinstance(data, dict):
        completed, pending = data.get("completed_transfers"), data.get("pending_transfers")
        eligible = data.get("first_transfer_eligible")
        if (type(completed) is int and completed >= 0 and type(pending) is int and pending >= 0
                and type(eligible) is bool and eligible == (completed == 0 and pending == 0)):
            updates = {"history_status": "verified", "completed_transfers": completed,
                       "pending_transfers": pending, "first_transfer_eligible": eligible,
                       "history_checked_at": util.now_iso()}
            db.merge_lead_data(cid, updates)
            return updates
    db.merge_lead_data(cid, {**invalid, "history_status": "unavailable"}, allow_null=True)
    return None


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
    language = lead.get("idioma", "es")
    tenant = T.get_config()
    tenant_id = tenant["id"]
    route = str(lead.get("ruta") or "")
    currency = route.split("->", 1)[0].upper() if "->" in route else ""
    if not currency:
        return copy("need_quote", language), []
    result = brasper_api.deposit_accounts(tenant, currency)
    accounts = result.get("data") if result.get("ok") else []
    if not accounts:
        return copy("accounts_unavailable", language), []
    lines = [copy("accounts", language, currency=currency)]
    for item in accounts:
        detail = item.get("account") or (f"PIX: {item.get('pix')}" if item.get("pix") else "")
        lines.append(f"• {item.get('bank')} — {item.get('company')} — {detail}")
    lines.append(copy("proof", language))
    return "\n".join(lines), accounts
