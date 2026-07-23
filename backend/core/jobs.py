"""Cola liviana Redis para trabajos fuera del request web.

La cola es OPCIONAL: si Redis no está configurado o no responde, cada operación
degrada con gracia (devuelve False/None/0/[]) en vez de tumbar el request web.
Los efectos importantes (auditoría, cambios de tenant) ya se persisten de forma
síncrona en la request; encolar aquí es solo notificación al worker.
"""
from __future__ import annotations

import json
import time
from typing import Any

import redis

from . import redis_runtime
from .util import now_iso as _now
from core import tenants as T

QUEUE = "jobs:default"
SCHEDULED = "jobs:scheduled"
DEAD_LETTER = "jobs:dead_letter"

# ConnectionError (host inalcanzable) es subclase de RedisError; OSError cubre
# fallos de socket que pudieran filtrarse sin envolver.
_REDIS_ERRORS = (redis.RedisError, OSError)


def enqueue(job_type: str, payload: dict[str, Any] | None = None,
            delay_seconds: float = 0, max_attempts: int = 3) -> bool:
    r = redis_runtime.client()
    if r is None:
        return False
    body = {
        "type": job_type,
        "payload": payload or {},
        "created_at": _now(),
        "attempts": 0,
        "max_attempts": max(1, int(max_attempts)),
    }
    raw = json.dumps(body, ensure_ascii=False)
    try:
        if delay_seconds > 0:
            r.zadd(SCHEDULED, {raw: time.time() + delay_seconds})
        else:
            r.rpush(QUEUE, raw)
        return True
    except _REDIS_ERRORS as e:  # Redis caído/inalcanzable: no encola, no rompe.
        print(f"[jobs] Redis no disponible; job '{job_type}' no encolado: {e}")
        return False


def pop(timeout: int = 5) -> dict | None:
    r = redis_runtime.client()
    if r is None:
        return None
    try:
        due = r.zrangebyscore(SCHEDULED, 0, time.time(), start=0, num=1)
        if due:
            raw_due = due[0]
            if r.zrem(SCHEDULED, raw_due):
                return json.loads(raw_due)
        item = r.blpop(QUEUE, timeout=timeout)
        if not item:
            return None
        _, raw = item
        return json.loads(raw)
    except _REDIS_ERRORS:
        time.sleep(1)  # evita busy-loop si Redis cae con el worker corriendo
        return None


def handle_failure(job: dict, error: str, retry_delay_seconds: float = 5) -> bool:
    r = redis_runtime.client()
    if r is None:
        return False
    job = dict(job)
    job["attempts"] = int(job.get("attempts") or 0) + 1
    job["last_error"] = str(error)[:500]
    try:
        if job["attempts"] >= int(job.get("max_attempts") or 3):
            job["failed_at"] = _now()
            r.rpush(DEAD_LETTER, json.dumps(job, ensure_ascii=False))
            return False
        r.zadd(SCHEDULED, {json.dumps(job, ensure_ascii=False): time.time() + retry_delay_seconds})
        return True
    except _REDIS_ERRORS as e:
        print(f"[jobs] Redis no disponible al manejar fallo de job: {e}")
        return False


def dead_letter_count() -> int:
    r = redis_runtime.client()
    if r is None:
        return 0
    try:
        return int(r.llen(DEAD_LETTER))
    except _REDIS_ERRORS:
        return 0


def list_dead_letter(limit: int = 100) -> list[dict]:
    """Contenido del dead-letter (no solo el conteo) para diagnóstico operativo."""
    r = redis_runtime.client()
    if r is None:
        return []
    try:
        raws = r.lrange(DEAD_LETTER, 0, max(0, int(limit) - 1))
    except _REDIS_ERRORS:
        return []
    out: list[dict] = []
    for raw in raws:
        try:
            out.append(json.loads(raw))
        except (ValueError, TypeError):
            out.append({"raw": str(raw)[:200]})
    return out
