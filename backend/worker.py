"""Worker de produccion para jobs livianos en Redis."""
from __future__ import annotations

import logging
import os
import time
import asyncio
from datetime import datetime, timedelta, timezone

import backup
from core import alerts, audio_adapter, audio_flow, auth, db, debounce, engine, jobs, tenants, telegram, whatsapp


def init() -> None:
    # El token del bot de Telegram viaja en la ruta de la URL y httpx la registra
    # en INFO: sin esto el secreto acaba en los logs del worker.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    db.assert_production_infra()   # fail-fast: en produccion exige Postgres + Redis
    db.init_db()
    auth.ensure_schema()


def handle(job: dict) -> None:
    job_type = job.get("type")
    payload = job.get("payload") or {}
    if job_type == "audit.event":
        db.add_audit_event(
            payload.get("actor"),
            payload.get("action", "worker.audit"),
            payload.get("resource"),
            payload.get("metadata"),
        )
        return
    if job_type == "tenant.changed":
        db.add_audit_event(
            payload.get("actor"),
            "worker.tenant_changed",
            f"tenant:{payload.get('tenant_id')}",
            {"source": "redis-job", "action": payload.get("action")},
        )
        return
    if job_type == "whatsapp.audio":
        asyncio.run(transcribe_audio_job({**payload, "_attempt": int(job.get("attempts") or 0)}))
        return
    if job_type == "channel.message":
        asyncio.run(handle_channel_message(payload))
        return
    # Tipo desconocido: no lo descartamos en silencio -> reintenta y va a dead-letter.
    raise ValueError(f"job type desconocido: {job_type}")


async def transcribe_audio_job(payload: dict) -> None:
    tenant = tenants.get_config()
    if not tenant:
        print(f"[worker] tenant inactivo/no encontrado: {payload.get('tenant_id')}")
        return
    conn = tenants.whatsapp_connection_by_id(payload.get("connection_id"), tenant)
    media = {"provider": "whatsapp", "kind": "audio", "ref": payload["media_id"],
             "mime": payload.get("mime_type")}

    async def _send(text: str) -> dict:
        return await whatsapp.send_text(payload["to"], text, connection=conn)

    tr = await audio_adapter.transcribe_whatsapp(tenant, payload["media_id"])
    if not tr.get("ok") or not (tr.get("text") or "").strip():
        if int(payload.get("_attempt") or 0) >= 2:
            # Último intento: conservar la evidencia y derivar en vez de perder el audio.
            await audio_flow.unreadable(channel="whatsapp", user_ref=payload["user_ref"], media=media,
                                        send=_send, error=tr.get("error"))
            return
        raise RuntimeError(f"transcripción de audio falló: {tr.get('error')}")
    # Flujo compartido: evidencia + confirmación de cifras ambiguas + grafo.
    await audio_flow.process_transcript(channel="whatsapp", user_ref=payload["user_ref"],
                                        text=tr["text"].strip(), media=media, send=_send)


async def handle_channel_message(payload: dict) -> None:
    tenant = tenants.get_config()
    if not tenant:
        print(f"[worker] tenant inactivo/no encontrado: {payload.get('tenant_id')}")
        return
    channel = payload["channel"]
    out = await engine.handle_message(
        payload["user_ref"],
        payload["text"],
        channel=channel,
        conversation_id=payload.get("conversation_id"),
    )
    # Bot en pausa (un asesor atiende) o sin texto -> no se envía nada. Sin esto el
    # worker rompía el takeover y mandaba mensajes vacíos al canal.
    if out.get("paused") or not (out.get("response") or "").strip():
        return
    if channel == "whatsapp":
        # La respuesta sale por la conexión (número) que recibió el mensaje.
        conn_id = payload.get("connection_id") or (db.get_conversation(out["conversation_id"]) or {}).get("connection_id")
        await whatsapp.send_text(payload["to"], out["response"],
                                 connection=tenants.whatsapp_connection_by_id(conn_id, tenant))
        return
    if channel == "telegram":
        markup = telegram.build_handoff_markup() if out.get("handoff") else None
        await telegram.send_message(payload["chat_id"], out["response"], reply_markup=markup)
        return
    print(f"[worker] canal sin envio automatico: {channel}")


def handle_due_debounce() -> bool:
    item = debounce.pop_due()
    if not item:
        return False
    asyncio.run(handle_channel_message(item))
    return True


def backup_interval_seconds() -> int:
    raw = os.getenv("AUTO_BACKUP_INTERVAL_SECONDS", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def maybe_backup(last_backup_at: float) -> float:
    interval = backup_interval_seconds()
    if interval <= 0:
        return last_backup_at
    now = time.time()
    if now - last_backup_at < interval:
        return last_backup_at
    path = backup.create_backup()
    print(f"[worker] backup creado: {path}")
    return now


def scheduler_interval_seconds() -> int:
    try:
        return max(0, int(os.getenv("SCHED_INTERVAL_SECONDS", "0").strip()))
    except ValueError:
        return 0


def retention_days() -> int:
    try:
        return max(0, int(os.getenv("RETENTION_DAYS", "0").strip()))
    except ValueError:
        return 0


def run_scheduled(last_run: float) -> float:
    """Tareas periódicas del worker: alertas externas + retención de datos."""
    interval = scheduler_interval_seconds()
    if interval <= 0:
        return last_run
    now = time.time()
    if now - last_run < interval:
        return last_run
    try:
        res = alerts.dispatch_external()
        if res.get("sent"):
            print(f"[worker] alertas externas enviadas ({res.get('active')})")
    except Exception as e:  # noqa: BLE001
        print(f"[worker] alertas error: {e}")
    days = retention_days()
    if days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        try:
            counts = db.purge_old_data(cutoff)
            if counts.get("conversations"):
                print(f"[worker] retención (>{days}d): {counts}")
        except Exception as e:  # noqa: BLE001
            print(f"[worker] retención error: {e}")
    return now


def main() -> int:
    init()
    print("[worker] iniciado")
    last_backup_at = 0.0
    last_sched = 0.0
    while True:
        try:
            last_backup_at = maybe_backup(last_backup_at)
            last_sched = run_scheduled(last_sched)
        except Exception as e:  # noqa: BLE001
            print(f"[worker] tarea periódica error: {e}")
        try:
            # El worker no debe morir por un mensaje agrupado que falle: sin este
            # try el bucle se caía y dejaba de atender la cola entera.
            if handle_due_debounce():
                continue
        except Exception as e:  # noqa: BLE001
            print(f"[worker] error procesando debounce: {e}")
        job = jobs.pop(timeout=5)
        if not job:
            if os.getenv("WORKER_ONCE") == "true":
                return 0
            time.sleep(0.2)
            continue
        try:
            handle(job)
        except Exception as e:  # noqa: BLE001 - el worker no debe morir por un job
            print(f"[worker] error procesando job: {e}")
            jobs.handle_failure(job, str(e), retry_delay_seconds=5)


if __name__ == "__main__":
    raise SystemExit(main())
