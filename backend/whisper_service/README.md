# Whisper Service (transcripción de audios)

Microservicio de transcripción con **faster-whisper** (self-hosted, sin costo por
uso). El backend le manda las notas de voz/audios de WhatsApp/Telegram y devuelve
el texto. Enfoque portado de `zefiron.ia`, generalizado con un `context` libre.

## Levantar (local, sin Docker)

```bash
cd backend/whisper_service
pip install -r requirements.txt          # descarga faster-whisper
uvicorn main:app --host 0.0.0.0 --port 8090
# La primera ejecución descarga el modelo (small ≈ 460 MB) a ~/.cache
```

## Levantar (Docker)

```bash
cd backend/whisper_service
docker build -t cauce-whisper .
docker run -p 8090:8090 cauce-whisper
```

## Conectar el backend

En el `.env` del backend (o en el bloque `audio` del tenant):

```
WHISPER_SERVICE_URL=http://localhost:8090
```

o por tenant (Admin API / tenants.json):

```json
"audio": {
  "enabled": true,
  "provider": "whisper_service",
  "service_url": "http://localhost:8090",
  "language": "es",
  "context": "Remesas Perú-Brasil. Monedas: soles (PEN), reales (BRL). Métodos: Yape, Pix, transferencia."
}
```

Si el servicio no está disponible, el audio **cae a handoff** (un asesor lo revisa):
no rompe la conversación.

## Endpoints

- `GET /health` → `{ok, model}`
- `POST /transcribe` (multipart) → `file`, `context` (opcional), `language` (opcional) → `{text}`

## Variables de entorno

| Variable | Def | Descripción |
|---|---|---|
| `WHISPER_MODEL` | `small` | tiny/base/small/medium/large-v3 |
| `WHISPER_DEVICE` | `cpu` | cpu/cuda |
| `WHISPER_COMPUTE_TYPE` | `int8` | int8/float16/float32 |
| `WHISPER_LANGUAGE` | `es` | idioma por defecto |
| `MAX_WHISPER_CONCURRENCY` | `1` | transcripciones en paralelo |
