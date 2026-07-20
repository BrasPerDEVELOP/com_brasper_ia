"""Calendario deterministico para tenants con citas."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import dateparser

from . import db
from .util import normalize_text

_INTENT_WORDS = (
    "cita", "agendar", "reservar", "reserva", "turno",
    "appointment", "book", "schedule", "consulta",
)
_DEFAULT_SPECIALTIES = ("medicina general", "pediatria", "ginecologia", "odontologia")


def _norm(value: str) -> str:
    return normalize_text(value)


def enabled(tenant: dict) -> bool:
    cfg = tenant.get("calendar") or {}
    return isinstance(cfg, dict) and bool(cfg.get("enabled"))


def has_intent(text: str) -> bool:
    normalized = _norm(text)
    return any(word in normalized for word in _INTENT_WORDS)


def _history_text(history: list[dict], text: str) -> str:
    user_parts = [m.get("content", "") for m in history if m.get("role") == "user"]
    if text not in user_parts:
        user_parts.append(text)
    return "\n".join(user_parts)


def _specialties(tenant: dict) -> list[str]:
    cfg = tenant.get("calendar") or {}
    values = cfg.get("specialties") or _DEFAULT_SPECIALTIES
    return [str(v) for v in values if str(v).strip()]


def _extract_name(text: str) -> str | None:
    patterns = [
        r"nombre(?:\s+completo)?\s*(?:es|:)?\s*([A-Za-zÁÉÍÓÚáéíóúÑñ ]{3,80})",
        r"soy\s+([A-Za-zÁÉÍÓÚáéíóúÑñ ]{3,80})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        raw = re.split(r"\b(?:dni|documento|especialidad|fecha|hora|para|el)\b", m.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        name = " ".join(raw.strip(" .,-").split())
        if len(name) >= 3:
            return name[:80]
    return None


def _extract_document(text: str) -> str | None:
    m = re.search(r"(?:dni|documento|doc)\D*(\d{8,12})", text, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{8})\b", text)
    return m.group(1) if m else None


def _extract_specialty(tenant: dict, text: str) -> str | None:
    normalized = _norm(text)
    for specialty in _specialties(tenant):
        if _norm(specialty) in normalized:
            return specialty
    return None


def _extract_datetime(text: str) -> str | None:
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}:\d{2}))?\b", text)
    if iso:
        hour = iso.group(2) or "09:00"
        return f"{iso.group(1)}T{hour}:00+00:00"
    parsed = dateparser.parse(
        text,
        languages=["es", "en", "pt"],
        settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": True},
    )
    if parsed:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat(timespec="seconds")
    return None


def extract_request(tenant: dict, text: str, history: list[dict]) -> dict:
    combined = _history_text(history, text)
    fields = {
        "patient_name": _extract_name(combined),
        "document_id": _extract_document(combined),
        "specialty": _extract_specialty(tenant, combined),
        "scheduled_for": _extract_datetime(combined),
    }
    missing = [label for label, value in (
        ("nombre completo", fields["patient_name"]),
        ("DNI/documento", fields["document_id"]),
        ("especialidad", fields["specialty"]),
        ("fecha y hora", fields["scheduled_for"]),
    ) if not value]
    return {"fields": fields, "missing": missing}


def missing_reply(missing: list[str]) -> str:
    return "Para agendar la cita me falta: " + ", ".join(missing) + "."


def schedule(tenant: dict, conversation_id: str, user_ref: str, fields: dict) -> dict:
    return db.create_appointment(
        tenant["id"],
        conversation_id,
        user_ref,
        fields["patient_name"],
        fields["document_id"],
        fields["specialty"],
        fields["scheduled_for"],
        {"source": "agent_graph"},
    )


def confirmation(appt: dict) -> str:
    return (
        f"Cita reservada para {appt['patient_name']} en {appt['specialty']} "
        f"el {appt['scheduled_for']}. Documento: {appt.get('document_id') or 'no indicado'}."
    )
