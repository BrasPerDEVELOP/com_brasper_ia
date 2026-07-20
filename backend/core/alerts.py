"""Alertas operativas derivadas de estado local y metricas."""
from __future__ import annotations

import os

import httpx

from . import db, jobs, redis_runtime

_LEVEL_ORDER = {"info": 1, "warning": 2, "critical": 3}


def _cost_threshold() -> float:
    try:
        return max(0.0, float(os.getenv("COST_ALERT_USD", "0") or 0))
    except ValueError:
        return 0.0


def current_alerts() -> list[dict]:
    alerts: list[dict] = []
    if not db.ping():
        alerts.append({"level": "critical", "code": "db_down", "message": "La base de datos no responde"})
    if redis_runtime.configured() and not redis_runtime.ping():
        alerts.append({"level": "critical", "code": "redis_down", "message": "Redis esta configurado pero no responde"})

    dead = jobs.dead_letter_count()
    if dead:
        alerts.append({"level": "warning", "code": "jobs_dead_letter", "message": "Hay jobs en dead-letter", "count": dead})

    threshold = _cost_threshold()
    if threshold > 0:
        for row in db.usage_summary():
            cost = float(row.get("cost_usd") or 0)
            if cost >= threshold:
                alerts.append({
                    "level": "warning",
                    "code": "tenant_cost_threshold",
                    "tenant_id": row["tenant_id"],
                    "message": "Tenant cerca o sobre el umbral de costo",
                    "cost_usd": round(cost, 6),
                    "threshold_usd": threshold,
                })
    return alerts


def _fingerprint(items: list[dict]) -> str:
    return ";".join(sorted(f"{a.get('code')}:{a.get('tenant_id', '')}" for a in items))


def dispatch_external(min_level: str = "warning") -> dict:
    """Envía las alertas activas a un webhook externo (Slack/Mattermost compatible).

    Config: ALERT_WEBHOOK_URL (incoming webhook), ALERT_COOLDOWN_SECONDS (def. 900).
    No-op sin URL. Evita spam: no reenvía el mismo conjunto dentro del cooldown.
    """
    url = (os.getenv("ALERT_WEBHOOK_URL") or "").strip()
    threshold = _LEVEL_ORDER.get(min_level, 2)
    active = [a for a in current_alerts() if _LEVEL_ORDER.get(a.get("level"), 0) >= threshold]
    if not url:
        return {"sent": False, "reason": "sin ALERT_WEBHOOK_URL", "active": len(active)}
    if not active:
        return {"sent": False, "reason": "sin alertas", "active": 0}

    fp = _fingerprint(active)
    r = redis_runtime.client()
    cooldown_key = redis_runtime.key("_global", "alerts", "last")
    if r is not None:
        try:
            if r.get(cooldown_key) == fp:
                return {"sent": False, "reason": "cooldown", "active": len(active)}
        except Exception:  # noqa: BLE001
            pass

    lines = []
    for a in active:
        line = f"[{str(a.get('level')).upper()}] {a.get('code')}: {a.get('message')}"
        if a.get("tenant_id"):
            line += f" (tenant {a['tenant_id']})"
        if a.get("count"):
            line += f" x{a['count']}"
        lines.append(line)
    text = "Cauce · alertas de plataforma:\n" + "\n".join(lines)
    try:
        resp = httpx.post(url, json={"text": text}, timeout=10)
    except httpx.RequestError as e:
        return {"sent": False, "reason": f"red: {e}", "active": len(active)}
    ok = resp.status_code < 300
    if ok and r is not None:
        try:
            cooldown = int(os.getenv("ALERT_COOLDOWN_SECONDS", "900") or 900)
            r.set(cooldown_key, fp, ex=max(1, cooldown))
        except Exception:  # noqa: BLE001
            pass
    return {"sent": ok, "active": len(active), "status": resp.status_code}
