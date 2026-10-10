"""Lease por conversación renovado mientras dura el procesamiento (C5).

La renovación corre en un hilo propio: un nodo que bloquee el event loop (herramienta
síncrona, LLM lento) no la retrasa. Si la renovación falla (base caída o el lease venció
y lo tomó otro proceso) se marca `lost` y se avisa para cancelar el trabajo en curso; la
respuesta nunca se entrega sin propiedad vigente.
"""
from __future__ import annotations

import contextvars
import threading
from typing import Callable

from . import observability, redis_runtime

_active: contextvars.ContextVar["Lease | None"] = contextvars.ContextVar("conversation_lease", default=None)


class LeaseLost(BaseException):
    """Se perdió la exclusión de la conversación. Hereda de BaseException para que un
    `except Exception` de un nodo o herramienta no la trague y siga escribiendo."""


def guard() -> None:
    """Llamar justo antes de cada escritura del procesamiento de un mensaje. Sin lease
    activo (panel, worker de seguimiento, scripts) no hace nada."""
    lease = _active.get()
    if lease is not None and lease.lost:
        raise LeaseLost(lease.name)


def activate(lease: "Lease"):
    return _active.set(lease)


def deactivate(token) -> None:
    _active.reset(token)


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
