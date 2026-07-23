"""Conector a la API real de Brasper (apibras.finzeler.com).

Permite cotizar con el TIPO DE CAMBIO EN VIVO del día — lo que hoy los asesores
escriben a mano en cada chat. Endpoints (GET, públicos):
  /coin/tax-rate           -> tasas por par (coin_a, coin_b, tax)
  /coin/commission         -> comisiones por rango (percentage, min/max_amount)
  /transactions/coupons/   -> cupones activos

Diseño:
  - Caché en memoria con TTL corto (por defecto 180s ≈ la "reserva de TC" del
    proceso comercial): evita golpear la API en cada mensaje y da vigencia estable.
  - Degradación segura: si la API falla, devuelve el último valor cacheado o None.
    El cotizador nunca sustituye una tasa Brasper por una tasa local.

Config por tenant (config.quote.api):
  { "enabled": true, "base_url": "https://apibras.finzeler.com" }
o por entorno: BRASPER_API_BASE_URL, BRASPER_API_TTL.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx

from . import observability

_DEFAULT_BASE = os.getenv("BRASPER_API_BASE_URL", "https://apibras.finzeler.com").rstrip("/")
_TTL = int(os.getenv("BRASPER_API_TTL", "180"))
_cache: dict[str, tuple[float, list]] = {}


def _api_cfg(tenant: dict) -> dict:
    return ((tenant.get("quote") or {}).get("api")) or {}


def _base_url(tenant: dict) -> str:
    return (_api_cfg(tenant).get("base_url") or _DEFAULT_BASE).rstrip("/")


def enabled(tenant: dict) -> bool:
    """¿Usar la API en vivo para este tenant? Explícito por config; si no, apagado."""
    return bool(_api_cfg(tenant).get("enabled"))


def _norm(value) -> str | None:
    return str(value).strip().upper() if value not in (None, "") else None


def _fetch(url: str) -> list | None:
    now = time.time()
    cached = _cache.get(url)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, headers={"accept": "application/json"})
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        observability.event("brasper_api.error", url=url, error=str(e)[:160])
        return cached[1] if cached else None  # sirve caché viejo si existe
    if isinstance(data, list):
        payload = data
    elif isinstance(data, dict):
        payload = next((data[k] for k in ("results", "items", "data") if isinstance(data.get(k), list)), [])
    else:
        payload = []
    _cache[url] = (now, payload)
    return payload


def rate_for(tenant: dict, origin: str, destination: str) -> float | None:
    """Tasa EN VIVO para el par, o None si la API no la tiene/falla."""
    rows = _fetch(f"{_base_url(tenant)}/coin/tax-rate") or []
    for item in rows:
        if _norm(item.get("coin_a")) == origin and _norm(item.get("coin_b")) == destination:
            try:
                rate = float(item.get("tax", 0))
            except (TypeError, ValueError):
                return None
            return rate if rate > 0 else None
    return None


def live_rates(tenant: dict) -> list[dict]:
    """Tasas publicadas por Brasper, normalizadas para consumo del panel."""
    rows = _fetch(f"{_base_url(tenant)}/coin/tax-rate")
    if rows is None:
        return []
    out: list[dict] = []
    for item in rows:
        origin = _norm(item.get("coin_a"))
        destination = _norm(item.get("coin_b"))
        try:
            rate = float(item.get("tax", 0))
        except (TypeError, ValueError):
            continue
        if origin and destination and rate > 0:
            out.append({
                "origin": origin,
                "destination": destination,
                "pair": f"{origin}->{destination}",
                "rate": rate,
                "updated_at": item.get("updated_at"),
            })
    return out


def commission_ranges(tenant: dict, origin: str, destination: str) -> list[dict]:
    """Rangos de comisión EN VIVO en el formato que usa quotes.py: {min,max,rate}."""
    rows = _fetch(f"{_base_url(tenant)}/coin/commission") or []
    out: list[dict] = []
    for item in rows:
        if _norm(item.get("coin_a")) != origin or _norm(item.get("coin_b")) != destination:
            continue
        try:
            out.append({
                "min": float(item.get("min_amount", 0)),
                "max": float(item.get("max_amount", 0)),
                "rate": float(item.get("percentage", 0)) / 100,
            })
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda r: r["min"])
    return out


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _integration_secret(tenant: dict) -> str | None:
    api = _api_cfg(tenant)
    return os.getenv(api.get("integration_secret_env") or "BRASPER_IA_SHARED_SECRET")


def _integration_request(tenant: dict, method: str, path: str, **kwargs) -> dict:
    secret = _integration_secret(tenant)
    if not secret:
        return {"ok": False, "error": "integración IA no configurada"}
    headers = {"accept": "application/json", "X-Brasper-IA-Secret": secret}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.request(method, f"{_base_url(tenant)}{path}", headers=headers, **kwargs)
            response.raise_for_status()
            return {"ok": True, "data": response.json()}
    except (httpx.HTTPError, ValueError) as exc:
        observability.event("brasper_api.integration_error", path=path, error=str(exc)[:160])
        return {"ok": False, "error": str(exc)[:160]}


_DOC_TYPES = {"dni", "ce", "cpf", "cnpj", "ruc", "passport", "other"}


def upsert_client(tenant: dict, lead: dict) -> dict:
    """Crea o actualiza un cliente mediante la integración privada e idempotente."""
    email = (lead.get("correo") or "").strip()
    doc_type = str(lead.get("tipo_documento") or "").strip().lower()
    if doc_type not in _DOC_TYPES:
        doc_type = "other"
    phone_digits = "".join(ch for ch in str(lead.get("telefono") or "") if ch.isdigit())
    payload = {
        "names": (lead.get("nombres") or "").strip(),
        "lastnames": (lead.get("apellidos") or "").strip(),
        "document_type": doc_type,
        "document_number": (lead.get("numero_documento") or "").strip(),
        "code_phone": (lead.get("codigo_telefono") or "+51").strip(),
        "phone": int(phone_digits) if phone_digits else None,
    }
    if email:
        payload["email"] = email
    if not phone_digits:
        return {"ok": False, "error": "Falta el teléfono del cliente"}
    return _integration_request(tenant, "POST", "/brasper/ai/clients/upsert", json=payload)


def find_client(tenant: dict, *, phone: str | None = None, code_phone: str | None = None,
                full_name: str | None = None) -> dict:
    """Busca un cliente puntualmente mediante la integración privada."""
    params: dict[str, object] = {}
    if phone:
        params["phone"] = "".join(ch for ch in str(phone) if ch.isdigit())
        if code_phone:
            params["code_phone"] = code_phone
    elif full_name:
        params["full_name"] = " ".join(full_name.split())
    else:
        return {"ok": False, "error": "Falta teléfono o nombre"}
    result = _integration_request(
        tenant, "GET", "/brasper/ai/clients/lookup", params=params)
    if not result.get("ok"):
        return result
    body = result.get("data") or {}
    return {
        "ok": True,
        "data": body.get("client") if body.get("found") else None,
        "ambiguous": bool(body.get("ambiguous")),
    }


def deposit_accounts(tenant: dict, currency: str) -> dict:
    """Lista cuentas oficiales Brasper por moneda; no son cuentas del cliente."""
    return _integration_request(
        tenant, "GET", "/brasper/ai/deposit-accounts", params={"currency": currency.upper()}
    )


def best_coupon(tenant: dict, origin: str, destination: str) -> dict | None:
    """Mejor cupón activo y vigente para el par: {code, discount_percentage}."""
    rows = _fetch(f"{_base_url(tenant)}/transactions/coupons/") or []
    now = datetime.now(timezone.utc)
    best = None
    for item in rows:
        if not item.get("is_active"):
            continue
        co, cd = _norm(item.get("origin_currency")), _norm(item.get("destination_currency"))
        if co and co != origin:
            continue
        if cd and cd != destination:
            continue
        start, end = _parse_dt(item.get("start_date")), _parse_dt(item.get("end_date"))
        if start and start > now:
            continue
        if end and end < now:
            continue
        try:
            disc = float(item.get("discount_percentage", 0))
        except (TypeError, ValueError):
            continue
        if best is None or disc > best["discount_percentage"]:
            best = {"code": item.get("code"), "discount_percentage": disc}
    return best
