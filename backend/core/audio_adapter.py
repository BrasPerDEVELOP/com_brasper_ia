"""Transcripción de audios de canales (WhatsApp/Telegram).

Dos backends, seleccionables por tenant (`config.audio.provider`):
  - "whisper_service": microservicio faster-whisper local (self-hosted, sin costo
    por uso). Portado del enfoque de zefiron.ia: POST multipart a /transcribe.
  - "openai": API compatible con OpenAI (`/audio/transcriptions`, whisper-1).

Por defecto: si hay `service_url`/WHISPER_SERVICE_URL -> whisper_service; si hay
API key -> openai; si no, transcripción deshabilitada (el canal cae a handoff).

Config por tenant (config.audio):
  {
    "enabled": true,
    "provider": "whisper_service" | "openai",
    "service_url": "http://localhost:8090",     # whisper_service
    "language": "es",
    "context": "remesas Perú-Brasil; soles, reales; Yape, Pix",  # initial_prompt
    "api_key_env": "OPENAI_API_KEY", "model": "whisper-1"        # openai
  }
"""
from __future__ import annotations

import os

import httpx

from . import tenants as T
from .whatsapp import GRAPH


def _audio_cfg(tenant: dict) -> dict:
    return tenant.get("audio") or {}


def _api_key(tenant: dict) -> str | None:
    cfg = _audio_cfg(tenant)
    if cfg.get("api_key"):
        return cfg["api_key"]
    env_name = cfg.get("api_key_env") or "OPENAI_API_KEY"
    return os.getenv(env_name)


def _service_url(tenant: dict) -> str:
    # La URL del servicio es infraestructura por entorno: el env manda (dev=localhost,
    # docker=whisper:8090) y cae a la config del tenant si no está seteado.
    return (os.getenv("WHISPER_SERVICE_URL") or _audio_cfg(tenant).get("service_url") or "").rstrip("/")


def _language(tenant: dict) -> str:
    return _audio_cfg(tenant).get("language") or os.getenv("AUDIO_LANGUAGE") or "es"


def _context(tenant: dict) -> str:
    cfg = _audio_cfg(tenant)
    return str(cfg.get("context") or cfg.get("initial_prompt") or "")


def provider(tenant: dict) -> str:
    cfg = _audio_cfg(tenant)
    p = (cfg.get("provider") or os.getenv("AUDIO_PROVIDER") or "").strip().lower()
    if p:
        return p
    if _service_url(tenant):
        return "whisper_service"
    return "openai"


def enabled(tenant: dict) -> bool:
    """¿Hay transcripción utilizable para este tenant? Si no, el audio va a handoff."""
    cfg = _audio_cfg(tenant)
    if cfg.get("enabled") is False:
        return False
    if provider(tenant) == "whisper_service":
        return bool(_service_url(tenant))
    return bool(_api_key(tenant))


def _filename(mime_type: str) -> str:
    if "ogg" in mime_type or "opus" in mime_type:
        return "audio.ogg"
    if "mp3" in mime_type or "mpeg" in mime_type:
        return "audio.mp3"
    if "wav" in mime_type:
        return "audio.wav"
    if "m4a" in mime_type or "mp4" in mime_type:
        return "audio.m4a"
    return "audio.bin"


async def _download_whatsapp_media(tenant: dict, media_id: str) -> tuple[bytes, str]:
    token = T.whatsapp_token(tenant)
    if not token:
        raise RuntimeError(f"Tenant {tenant['id']}: WhatsApp sin token")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=45) as client:
        meta = await client.get(f"{GRAPH}/{media_id}", headers=headers)
        if meta.status_code != 200:
            raise RuntimeError(f"Meta media {meta.status_code}: {meta.text[:160]}")
        data = meta.json()
        media_url = data.get("url")
        mime_type = data.get("mime_type") or "audio/ogg"
        if not media_url:
            raise RuntimeError("Meta media sin url")
        audio = await client.get(media_url, headers=headers)
        if audio.status_code != 200:
            raise RuntimeError(f"Descarga media {audio.status_code}: {audio.text[:160]}")
        return audio.content, mime_type


async def _transcribe_whisper_service(tenant: dict, content: bytes, mime_type: str) -> dict:
    """Envía el audio al microservicio faster-whisper (enfoque zefiron.ia)."""
    url = _service_url(tenant)
    if not url:
        return {"ok": False, "error": "WHISPER_SERVICE_URL/service_url no configurado"}
    filename = _filename(mime_type)
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{url}/transcribe",
                files={"file": (filename, content, mime_type or "audio/ogg")},
                data={"context": _context(tenant), "language": _language(tenant)},
            )
    except httpx.RequestError as e:
        return {"ok": False, "error": f"whisper_service inalcanzable: {e}"}
    if response.status_code != 200:
        return {"ok": False, "status": response.status_code, "error": response.text[:300]}
    text = (response.json().get("text") or "").strip()
    return {"ok": bool(text), "text": text, "model": "faster-whisper", "provider": "whisper_service"}


async def _transcribe_openai(tenant: dict, content: bytes, mime_type: str) -> dict:
    api_key = _api_key(tenant)
    if not api_key:
        return {"ok": False, "error": "AUDIO/OPENAI API key no configurada"}
    cfg = _audio_cfg(tenant)
    base_url = (cfg.get("base_url") or os.getenv("AUDIO_TRANSCRIPTION_BASE_URL")
                or "https://api.openai.com/v1").rstrip("/")
    model = cfg.get("model") or os.getenv("AUDIO_TRANSCRIPTION_MODEL") or "whisper-1"
    data = {"model": model, "language": _language(tenant)}
    if _context(tenant):
        data["prompt"] = _context(tenant)
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files={"file": (_filename(mime_type), content, mime_type)},
            )
    except httpx.RequestError as e:
        return {"ok": False, "error": f"transcripción inalcanzable: {e}"}
    if response.status_code != 200:
        return {"ok": False, "status": response.status_code, "error": response.text[:300]}
    text = (response.json().get("text") or "").strip()
    return {"ok": bool(text), "text": text, "model": model, "provider": "openai"}


async def transcribe_bytes(tenant: dict, content: bytes, mime_type: str = "audio/ogg") -> dict:
    """Transcribe bytes de audio con el backend configurado para el tenant."""
    if provider(tenant) == "whisper_service":
        return await _transcribe_whisper_service(tenant, content, mime_type)
    return await _transcribe_openai(tenant, content, mime_type)


async def transcribe_whatsapp(tenant: dict, media_id: str) -> dict:
    content, mime_type = await _download_whatsapp_media(tenant, media_id)
    return await transcribe_bytes(tenant, content, mime_type)
