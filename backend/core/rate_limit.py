"""Rate limiting simple en memoria.

Es deliberadamente pequeño: protege el backend aun antes de poner Redis/WAF.
En despliegues multi-worker debe complementarse con reverse proxy o Redis.
"""
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _limit_for(name: str, default: str) -> int:
    raw = os.getenv(f"RATE_LIMIT_{name.upper()}", default)
    try:
        return max(1, int(raw))
    except ValueError:
        return int(default)


def check(request: Request, bucket: str, limit: int | None = None,
          window_seconds: int = 60) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{ip}"
    max_hits = limit or _limit_for(bucket, "60")
    now = time.time()
    q = _BUCKETS[key]
    while q and q[0] <= now - window_seconds:
        q.popleft()
    if len(q) >= max_hits:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes; intenta de nuevo en un momento")
    q.append(now)
