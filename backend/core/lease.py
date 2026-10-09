"""Lease por conversación renovado mientras dura el procesamiento (C5).

La renovación corre en un hilo propio: un nodo que bloquee el event loop (herramienta
síncrona, LLM lento) no la retrasa. Si la renovación falla (base caída o el lease venció
y lo tomó otro proceso) se marca `lost` y se avisa para cancelar el trabajo en curso; la
respuesta nunca se entrega sin propiedad vigente.
"""
from __future__ import annotations

import threading
from typing import Callable

from . import observability, redis_runtime


class Lease:
    def __init__(self, name: str, token: str, ttl_seconds: int, on_lost: Callable[[], None] | None = None):
        self.name, self.token, self.ttl = name, token, ttl_seconds
        self.on_lost = on_lost
        self.lost = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"lease:{name}", daemon=True)

    def start(self) -> "Lease":
        self._thread.start()
        return self

    def _run(self) -> None:
        interval = max(0.05, self.ttl / 3)
        while not self._stop.wait(interval):
            if not redis_runtime.renew_lock(self.name, self.token, self.ttl):
                self.lost = True
                observability.event("conversation.lease_lost", lock=self.name)
                if self.on_lost:
                    self.on_lost()
                return

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def held(self) -> bool:
        return not self.lost and redis_runtime.still_held(self.name, self.token)
