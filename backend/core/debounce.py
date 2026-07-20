"""Debounce Redis para rafagas de mensajes por conversacion."""
from __future__ import annotations

import json
import os
import time

import redis

from . import redis_runtime

DUE_KEY = "debounce:due"


def delay_seconds() -> float:
    raw = (os.getenv("CHANNEL_DEBOUNCE_SECONDS") or "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def enabled() -> bool:
    return delay_seconds() > 0 and redis_runtime.configured()


def _base_key(tenant_id: str, channel: str, user_ref: str) -> str:
    return redis_runtime.key(tenant_id, "debounce", channel, user_ref)


def buffer_message(tenant_id: str, channel: str, user_ref: str,
                   text: str, delivery: dict) -> bool:
    r = redis_runtime.client()
    delay = delay_seconds()
    if r is None or delay <= 0:
        return False
    base = _base_key(tenant_id, channel, user_ref)
    payload = {**delivery, "tenant_id": tenant_id, "channel": channel, "user_ref": user_ref}
    due_at = time.time() + delay
    pipe = r.pipeline()
    pipe.rpush(f"{base}:messages", text)
    pipe.set(f"{base}:delivery", json.dumps(payload, ensure_ascii=False))
    pipe.zadd(DUE_KEY, {base: due_at})
    pipe.expire(f"{base}:messages", 3600)
    pipe.expire(f"{base}:delivery", 3600)
    try:
        pipe.execute()
        return True
    except redis.RedisError:
        return False


def pop_due(now: float | None = None) -> dict | None:
    r = redis_runtime.client()
    if r is None:
        return None
    now = now or time.time()
    try:
        keys = r.zrangebyscore(DUE_KEY, 0, now, start=0, num=1)
    except redis.RedisError:
        return None
    if not keys:
        return None
    base = keys[0]
    if not r.zrem(DUE_KEY, base):
        return None
    messages_key = f"{base}:messages"
    delivery_key = f"{base}:delivery"
    messages = r.lrange(messages_key, 0, -1)
    raw_delivery = r.get(delivery_key)
    r.delete(messages_key, delivery_key)
    if not messages or not raw_delivery:
        return None
    delivery = json.loads(raw_delivery)
    return {**delivery, "text": "\n".join(messages)}
