"""Long polling de Telegram para desarrollo local (sin dominio público).

Uso (desde backend/, con el venv del repo):
    ../.venv/bin/python dev_telegram.py

Requisitos:
  1. Crear un bot con @BotFather y copiar el token.
  2. En backend/.env poner el token del tenant, p.ej.:
        TELEGRAM_TOKEN_BRASPER=123456:ABC...
     (opcional para webhook en prod: TELEGRAM_SECRET_BRASPER=una-cadena-larga)
  3. Escribirle al bot en Telegram: cada mensaje pasa por engine.handle_message
     igual que WhatsApp/webchat (mismo LLM, mismo handoff, mismo metering).

Esto NO usa el servidor FastAPI: hace getUpdates directamente. Para producción,
usa el endpoint POST /api/{tenant_id}/telegram/set-webhook en su lugar.
"""
import asyncio

from core import telegram
from core import tenants as T


async def main() -> None:
    cfg = T.get_config()
    configured = [cfg] if T.telegram_token(cfg) else []
    if not configured:
        print("No hay tenants con Telegram configurado.")
        print("Agrega TELEGRAM_TOKEN_<TENANT> en backend/.env y reintenta.")
        return

    print("Tenants con Telegram:", ", ".join(t["id"] for t in configured))
    for t in configured:
        me = await telegram.get_me()
        who = (me.get("result") or {}).get("username") if me.get("ok") else me.get("reason")
        print(f"  · {t['id']}: @{who}")

    tasks = [asyncio.create_task(telegram.poll_loop()) for t in configured]
    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nDeteniendo pollers…")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
