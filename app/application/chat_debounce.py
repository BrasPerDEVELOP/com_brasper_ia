"""
Acumula mensajes por usuario y llama al chat una sola vez tras un silencio (debounce).
Reduce llamadas al LLM cuando el usuario envía varias líneas seguidas.

Los fragmentos se unen con línea en blanco entre sí (no con un solo espacio), para que cada
burbuja o línea del usuario siga distinguible al procesarlos "de uno en uno".

Variables de entorno:
- CHAT_DEBOUNCE_SECONDS: segundos de espera (0 = desactivado, comportamiento anterior).
- CHAT_DEBOUNCE_IMMEDIATE_MIN_WORDS: si el mensaje tiene al menos N palabras, sin debounce (respuesta inmediata).
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from typing import Any, Awaitable, Callable, Optional

ExecuteFn = Callable[[str, str], str]

# Separador entre mensajes acumulados: evita pegar frases distintas en un solo párrafo ilegible.
_MESSAGE_JOINER = "\n\n"


def _join_buffered_messages(parts: list[str]) -> str:
    return _MESSAGE_JOINER.join(p.strip() for p in parts if p and str(p).strip()).strip()


def _debounce_seconds() -> float:
    raw = (os.getenv("CHAT_DEBOUNCE_SECONDS") or "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _immediate_min_words() -> int:
    raw = (os.getenv("CHAT_DEBOUNCE_IMMEDIATE_MIN_WORDS") or "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


class ChatDebouncer:
    """Debounce en memoria (mismo proceso / worker uvicorn)."""

    def __init__(
        self,
        execute_sync: ExecuteFn,
        debounce_seconds: Optional[float] = None,
        immediate_min_words: Optional[int] = None,
    ):
        self._execute = execute_sync
        self._debounce = debounce_seconds if debounce_seconds is not None else _debounce_seconds()
        self._immediate_min_words = (
            immediate_min_words if immediate_min_words is not None else _immediate_min_words()
        )
        self._buffers: dict[str, list[str]] = defaultdict(list)
        self._tasks: dict[str, asyncio.Task] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

        self._buffers_wa: dict[str, list[str]] = defaultdict(list)
        self._tasks_wa: dict[str, asyncio.Task] = {}
        self._wa_phone: dict[str, str] = {}

    def _immediate(self, message: str) -> bool:
        if self._immediate_min_words <= 0:
            return False
        return len(message.split()) >= self._immediate_min_words

    async def add_and_wait(self, user_id: str, message: str) -> str:
        """HTTP: espera a la ventana de silencio y devuelve una sola respuesta."""
        loop = asyncio.get_running_loop()
        if self._debounce <= 0:
            return await loop.run_in_executor(None, lambda: self._execute(user_id, message))
        if self._immediate(message):
            return await loop.run_in_executor(None, lambda: self._execute(user_id, message))

        async with self._lock:
            self._buffers[user_id].append(message)
            if user_id not in self._futures or self._futures[user_id].done():
                self._futures[user_id] = loop.create_future()
            fut = self._futures[user_id]

            if user_id in self._tasks:
                self._tasks[user_id].cancel()

            self._tasks[user_id] = asyncio.create_task(self._flush_http(user_id))

        return await fut

    async def _flush_http(self, user_id: str) -> None:
        try:
            await asyncio.sleep(self._debounce)
        except asyncio.CancelledError:
            return

        async with self._lock:
            messages = self._buffers.pop(user_id, [])
            self._tasks.pop(user_id, None)
            fut = self._futures.get(user_id)

        if not messages:
            if fut and not fut.done():
                fut.set_exception(RuntimeError("buffer vacío tras debounce"))
            return

        full = _join_buffered_messages(messages)
        if not full:
            if fut and not fut.done():
                fut.set_exception(RuntimeError("mensaje vacío"))
            return

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: self._execute(user_id, full))
            if fut and not fut.done():
                fut.set_result(result)
        except Exception as e:
            if fut and not fut.done():
                fut.set_exception(e)

    async def enqueue_whatsapp(
        self,
        user_id: str,
        phone_number_id: str,
        message: str,
        send_message: Callable[..., Awaitable[Any]],
    ) -> None:
        """WhatsApp: acumula y envía una sola respuesta por ráfaga (no bloquea el webhook)."""
        loop = asyncio.get_running_loop()
        if self._debounce <= 0:
            try:
                text = await loop.run_in_executor(None, lambda: self._execute(user_id, message))
                await send_message(text, user_id, phone_number_id)
            except Exception as e:
                print(f"[whatsapp debounce] {e}")
            return
        if self._immediate(message):
            try:
                text = await loop.run_in_executor(None, lambda: self._execute(user_id, message))
                await send_message(text, user_id, phone_number_id)
            except Exception as e:
                print(f"[whatsapp debounce] {e}")
            return

        async with self._lock:
            self._buffers_wa[user_id].append(message)
            self._wa_phone[user_id] = phone_number_id
            if user_id in self._tasks_wa:
                self._tasks_wa[user_id].cancel()
            self._tasks_wa[user_id] = asyncio.create_task(
                self._flush_whatsapp(user_id, send_message)
            )

    async def _flush_whatsapp(
        self,
        user_id: str,
        send_message: Callable[..., Awaitable[Any]],
    ) -> None:
        try:
            await asyncio.sleep(self._debounce)
        except asyncio.CancelledError:
            return

        async with self._lock:
            messages = self._buffers_wa.pop(user_id, [])
            self._tasks_wa.pop(user_id, None)
            phone_number_id = self._wa_phone.pop(user_id, None)

        if not messages or not phone_number_id:
            return

        full = _join_buffered_messages(messages)
        if not full:
            return

        loop = asyncio.get_running_loop()
        try:
            text = await loop.run_in_executor(None, lambda: self._execute(user_id, full))
            await send_message(text, user_id, phone_number_id)
        except Exception as e:
            print(f"[whatsapp debounce] {e}")
