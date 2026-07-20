# Cauce · Plataforma IA Multi-Tenant

Plataforma gestionada por agencia para operar bots de clientes en WhatsApp, Telegram y webchat desde un panel interno. La base funcional ya esta cerrada; este repo queda orientado a produccion.

## Ejecutar en desarrollo (un comando)

```bash
./scripts/dev.sh           # backend :8002 + poller Telegram + panel :3000
./scripts/dev.sh --audio   # además el microservicio Whisper :8090 (transcripción)
./scripts/stop.sh          # detiene todo
```

Requisitos: Postgres corriendo (`brew services start postgresql@16`) y el venv en `.venv/`.
**Importante:** el bot de Telegram solo responde si el **poller** (`dev_telegram.py`) está
activo — `dev.sh` lo levanta. Probar: escribe al bot en Telegram, o abre el panel en
http://localhost:3000 (`owner@agencia.com` / `demo1234`) → Conversaciones → Brasper.
Logs en `.logs/`.

## Stack

| Capa | Tecnologia |
|---|---|
| API | FastAPI + Python |
| Panel | Next.js + TypeScript |
| Datos | Postgres en produccion, SQLite solo local/tests |
| Temporal | Redis |
| Proxy | Caddy |
| IA | LangGraph + adapter LLM por tenant |
| Migraciones | Alembic |
| Deploy | Docker Compose |

## Estructura

```text
backend/              API, auth, tenants, canales, persistencia
web/                  panel interno Next.js
maqueta/              maqueta navegable de producto/operacion
docker-compose.yml    stack local/produccion base
Caddyfile             rutas del proxy
PLAN_PLATAFORMA.md    plan de produccion por fases
```

## Ejecutar

```bash
cp backend/.env.example backend/.env
# completa credenciales y passwords
docker compose up --build
```

Abre:

```text
http://localhost:8080
```

## Verificar Backend

```bash
cd backend
../.venv/bin/python tests/run_checks.py
```

## Documentos Clave

- `AGENTS.md`: skills y flujo para agentes (bot / fintech IA).
- `PLAN_PLATAFORMA.md`: ruta de produccion.
- `backend/DEPLOY.md`: deploy y variables obligatorias.
- `backend/README.md`: API y endpoints.
- `web/README.md`: panel.

## Skills (Cursor / agentes)

En `.agents/skills/` y `.cursor/skills/`:

| Skill | Uso |
|---|---|
| `brasper-ia-audit` | Auditoria pre-launch / dual stack |
| `brasper-fintech-ia` | Cotizaciones, tools, anti-alucinacion, RAG |
| `brainstorming` | Features nuevas |
| `thermo-nuclear-code-quality-review` | Review estricto de graph/orchestrators |

## Mejoras para launch (fases)

| Fase | Doc |
|---|---|
| **0** Unificar Brasper en `backend/` (CRITICAL) | [docs/plans/FASE-0.md](docs/plans/FASE-0.md) |
| 1 Vertical Remesas + anti-alucinacion | [docs/plans/FASE-1.md](docs/plans/FASE-1.md) |
| 2 CI + evals + smoke | [docs/plans/FASE-2.md](docs/plans/FASE-2.md) |
| 3 FAQ / RAG ligero | [docs/plans/FASE-3.md](docs/plans/FASE-3.md) |
| 4 Launch ops | [docs/plans/FASE-4.md](docs/plans/FASE-4.md) |

Indice: [`docs/plans/00-ROADMAP.md`](docs/plans/00-ROADMAP.md) · Prompts: [`docs/PROMPT-FASES.md`](docs/PROMPT-FASES.md) · Mapa: [`FEATURE_MAP.md`](FEATURE_MAP.md)

Empezar por Fase 0: el Docker actual no usa el motor de cotizaciones real de `app/`.

## Estado Honesto

Ya existen base multi-tenant, panel, auth, uso, WhatsApp, Telegram, Postgres/Redis en Compose, worker, Alembic, Admin API de tenants, panel de administracion de clientes, LangGraph, ToolRouter, citas, debounce Redis, logs/metricas/alertas, backup/restore, rotacion de secret refs y hardening inicial.

Todavia faltan para produccion completa: worker para audios/transcripcion y validaciones de negocio por vertical.
