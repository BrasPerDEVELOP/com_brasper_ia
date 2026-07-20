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


def metrics_snapshot() -> dict:
    usage = db.usage_summary()
    tenant_count = len({row["tenant_id"] for row in usage})
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
    }
