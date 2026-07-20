# Backend · Plataforma IA Multi-Tenant

Servicio FastAPI para operar bots por cliente desde una plataforma gestionada por agencia. Maneja tenants, auth/RBAC, conversaciones, uso, webhooks de WhatsApp, webhooks de Telegram y chat de prueba.

## Arquitectura Actual

| Pieza | Estado |
|---|---|
| API | FastAPI en `backend/main.py` |
| Auth | Token opaco + RBAC + scope por tenant |
| Tenants | Postgres en produccion; `backend/config/tenants.json` como bootstrap/local |
| Datos | Postgres si `DATABASE_URL` existe; SQLite solo fallback local/tests |
| Temporal | Redis si `REDIS_URL` existe; obligatorio en `APP_ENV=production` |
| Canales | WhatsApp Cloud API, Telegram Bot API y webchat/API |
| IA | LangGraph en `core/agent_graph.py` |
| Worker | `worker.py` + cola Redis `jobs:default` |
| Observabilidad | Logs JSON + `/api/ops/metrics` |
| Seguridad | Sin tokens demo en produccion, firma WhatsApp, secret Telegram, rate limit basico |

## Ejecutar Local

```bash
cd backend
../.venv/bin/python -m uvicorn main:app --port 8002
```

Sin `DATABASE_URL`, el backend usa SQLite local en `backend/data/plataforma.db`.

## Ejecutar Con Contenedores

```bash
cp backend/.env.example backend/.env
# completa backend/.env
docker compose up --build
```

Servicios esperados:

- `api`: FastAPI, puerto interno `8002`.
- `worker`: jobs livianos desde Redis.
- `admin-web`: panel Next.js, puerto interno `3000`.
- `reverse-proxy`: Caddy en `http://localhost:8080`.
- `postgres`: fuente de verdad.
- `redis`: estado temporal, health, locks, debounce y cola del worker.

## Backups

```bash
cd backend
../.venv/bin/python backup.py create
../.venv/bin/python backup.py list
```

En Docker:

```bash
docker compose exec api python backup.py create
```

Postgres usa `pg_dump/pg_restore`; local/tests con SQLite copia `backend/data/plataforma.db`.

## Endpoints Principales

- `GET /health`
- `POST /api/login`
- `GET /api/me`
- `GET /api/tenants`
- `POST /api/{tenant}/chat`
- `GET /api/{tenant}/conversations`
- `GET /api/{tenant}/conversations/{conversation_id}`
- `GET /api/{tenant}/appointments`
- `GET /api/usage?tenant_id=...`
- `GET /api/ops/metrics`
- `GET /api/ops/alerts`
- `GET/POST /api/{tenant}/connectors...`
- `GET/POST /api/{tenant}/templates...`
- `GET/POST /webhook`
- `POST /telegram/webhook/{tenant_id}`
- `POST /api/{tenant}/telegram/set-webhook`
- `POST /api/{tenant}/telegram/delete-webhook`
- `GET /api/{tenant}/telegram/info`

## Alta De Un Cliente

1. En produccion usa `POST /api/admin/tenants` con token `owner/admin`.
2. Define variables del cliente en `backend/.env`: proveedor IA, WhatsApp, Telegram y secrets.
3. Referencia secretos con `*_env`; no guardes valores crudos.
4. Verifica `/api/admin/tenants`, `/api/tenants`, `/health` y el webhook del canal.

`backend/config/tenants.json` queda como bootstrap inicial y fallback local.

## Reglas De Produccion

- `APP_ENV=production`.
- `DATABASE_URL` debe apuntar a Postgres.
- `REDIS_URL` debe estar definido y responder.
- `PANEL_ADMIN_EMAIL`, `PANEL_ADMIN_TOKEN` y `PANEL_LOGIN_CODE` deben existir.
- `WHATSAPP_REQUIRE_SIGNATURE=true` con `META_APP_SECRET` para WhatsApp.
- Cada tenant de Telegram debe tener `TELEGRAM_SECRET_*`.
- `CORS_ALLOW_ORIGINS` debe apuntar al dominio real del panel.

## Admin API De Tenants

- `GET /api/admin/tenants`
- `POST /api/admin/tenants`
- `PATCH /api/admin/tenants/{tenant_id}`
- `POST /api/admin/tenants/{tenant_id}/pause`
- `POST /api/admin/tenants/{tenant_id}/resume`
- `POST /api/admin/tenants/{tenant_id}/secrets`
- `GET /api/admin/tenants/{tenant_id}/secrets/rotations`
- `GET /api/admin/tenants/{tenant_id}/usage`

En `APP_ENV=production`, el backend rechaza secretos directos como `api_key`,
`token`, `bot_token` o `secret_token`. Usa rutas de secret refs, por ejemplo:

```json
{
  "refs": {
    "llm.api_key_env": "OPENAI_API_KEY_CLIENTE"
  }
}
```

## Pendiente Para Produccion Completa

La base funcional esta cerrada, pero todavia faltan piezas de operacion avanzada:

- Worker avanzado para audios/transcripcion.
- Validaciones de negocio por vertical/canal.
- Runbooks de incidentes.
