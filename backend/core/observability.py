"""Logs estructurados y metricas operativas basicas."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from . import db, jobs

SENSITIVE = ("token", "secret", "api_key", "password", "authorization")
logger = logging.getLogger("cauce")


def _sensitive_key(key: str) -> bool:
    key = key.lower()
    if key in {"token", "secret", "api_key", "password", "authorization"}:
        return True
    return key.endswith("_token") or key.endswith("_secret") or key.endswith("_api_key")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, nested in value.items():
            if _sensitive_key(str(key)):
                out[key] = "***"
            else:
                out[key] = _redact(nested)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def event(name: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": name,
        **_redact(fields),
    }
    logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))


# --- Core Web Vitals reportados por el panel (ventana en memoria por proceso) ---
_VITALS_MAX = 500
_vitals: dict[str, list[float]] = {}
_vitals_meta: dict[str, dict[str, int]] = {}


def record_web_vital(name: str, value: float, path: str = "", rating: str = "") -> None:
    bucket = _vitals.setdefault(name, [])
    bucket.append(float(value))
    if len(bucket) > _VITALS_MAX:
        del bucket[: len(bucket) - _VITALS_MAX]
    meta = _vitals_meta.setdefault(name, {"good": 0, "needs-improvement": 0, "poor": 0})
    if rating in meta:
        meta[rating] += 1
    event("web_vital", metric=name, value=round(float(value), 3), path=path, rating=rating)


def _p75(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(0.75 * (len(ordered) - 1))))
    return round(ordered[idx], 3)


def web_vitals_snapshot() -> dict:
    return {name: {"samples": len(vals), "p75": _p75(vals), "ratings": _vitals_meta.get(name, {})}
            for name, vals in _vitals.items()}


# --- Métricas por flujo del bot (conteo, errores, duración p50/p95 por proceso) ---
_FLOWS: dict[str, dict] = {}
_FLOW_MAX = 500


def record_flow(flow: str, duration_ms: float, ok: bool = True) -> None:
    f = _FLOWS.setdefault(flow, {"count": 0, "errors": 0, "durations": []})
    f["count"] += 1
    if not ok:
        f["errors"] += 1
    f["durations"].append(float(duration_ms))
    if len(f["durations"]) > _FLOW_MAX:
        del f["durations"][: len(f["durations"]) - _FLOW_MAX]


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
    return round(ordered[idx], 1)


def flows_snapshot() -> dict:
    return {name: {"count": f["count"], "errors": f["errors"],
                   "p50_ms": _pct(f["durations"], 0.5), "p95_ms": _pct(f["durations"], 0.95)}
            for name, f in _FLOWS.items()}


def metrics_snapshot() -> dict:
    usage = db.usage_summary()
    # usage_summary() sin filtro no trae tenant_id (single-tenant): cuenta filas con consumo.
    tenant_count = sum(1 for row in usage if int(row.get("calls") or 0) > 0)
    total_calls = sum(int(row.get("calls") or 0) for row in usage)
    total_cost = round(sum(float(row.get("cost_usd") or 0) for row in usage), 6)
    return {
        "usage": {
            "tenants_with_usage": tenant_count,
            "calls": total_calls,
            "cost_usd": total_cost,
            "by_tenant": usage,
        },
        "conversations": {
            "by_tenant": db.count_by_tenant("conversations"),
        },
        "messages": {
            "by_tenant": db.count_by_tenant("messages"),
        },
        "appointments": {
            "by_tenant": db.count_by_tenant("appointments"),
        },
        "jobs": {
            "dead_letter": jobs.dead_letter_count(),
        },
        "web_vitals": web_vitals_snapshot(),
        "flows": flows_snapshot(),
    }
