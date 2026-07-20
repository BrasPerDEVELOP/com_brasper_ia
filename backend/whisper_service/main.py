"""Microservicio de transcripción con faster-whisper (self-hosted, sin costo por uso).

Enfoque portado de zefiron.ia y generalizado: recibe un audio por multipart y un
`context` libre (initial_prompt) para mejorar la precisión en jerga del negocio
(p.ej. "remesas Perú-Brasil; soles, reales; Yape, Pix").

Ejecutar:
    pip install fastapi uvicorn faster-whisper python-multipart
    uvicorn main:app --host 0.0.0.0 --port 8090

Variables de entorno:
    WHISPER_MODEL           tamaño del modelo (tiny|base|small|medium|large-v3). Def: small
    WHISPER_DEVICE          cpu|cuda. Def: cpu
    WHISPER_COMPUTE_TYPE    int8|float16|float32. Def: int8
    WHISPER_LANGUAGE        idioma por defecto si el request no lo indica. Def: es
    MAX_WHISPER_CONCURRENCY transcripciones en paralelo (cola por semáforo). Def: 1
    DOWNLOAD_DIR            carpeta temporal. Def: /tmp/cauce-whisper
"""
import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whisper_service")

app = FastAPI(title="Cauce Whisper Service")

_semaphore = None


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        # Por defecto 1: funciona como cola para no asfixiar CPU/RAM.
        _semaphore = asyncio.Semaphore(int(os.getenv("MAX_WHISPER_CONCURRENCY", "1")))
    return _semaphore


logger.info("Cargando modelo faster-whisper...")
model = WhisperModel(
    os.getenv("WHISPER_MODEL", "small"),
    device=os.getenv("WHISPER_DEVICE", "cpu"),
    compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
)
logger.info("Modelo cargado.")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": os.getenv("WHISPER_MODEL", "small")}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    context: str = Form(""),
    language: str = Form(""),
) -> dict:
    lang = (language or os.getenv("WHISPER_LANGUAGE", "es")).strip() or "es"
    prompt = (context or "").strip() or None

    download_dir = os.getenv("DOWNLOAD_DIR", "/tmp/cauce-whisper")
    os.makedirs(download_dir, exist_ok=True)
    suffix = Path(file.filename or "").suffix or ".bin"
    temp_path = os.path.join(download_dir, f"{uuid.uuid4()}{suffix}")

    try:
        def _save():
            with open(temp_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
        await asyncio.to_thread(_save)

        async with _sem():  # cola: una transcripción a la vez por defecto
            def _run():
                segments, _info = model.transcribe(
                    temp_path, language=lang, beam_size=5, initial_prompt=prompt,
                )
                return "".join(seg.text for seg in segments).strip()
            text = await asyncio.to_thread(_run)
        logger.info("Transcripción OK (%d chars)", len(text))
        return {"text": text}
    except Exception as e:  # noqa: BLE001 - devolver error controlado, no 500
        logger.warning("Transcripción falló: %s", e)
        return {"text": None, "error": str(e)[:200]}
    finally:
        def _cleanup():
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
        await asyncio.to_thread(_cleanup)
