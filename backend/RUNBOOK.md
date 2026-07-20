# RUNBOOK · Operación e Incidentes

Plataforma multi-tenant de bots (WhatsApp / Telegram / webchat). Stack Docker Compose: `api` (FastAPI, :8002), `worker`, `admin-web` (Next.js), `reverse-proxy` (Caddy, :8080), `postgres` (16), `redis` (7). En producción: `APP_ENV=production`, tenants en Postgres (`TENANTS_SOURCE=database`), secretos por referencia (`*_env`).

Todos los comandos `docker compose` se ejecutan desde la raíz del repo. Los comandos del CLI backend se ejecutan desde `backend/` con `../.venv/bin/python` (o dentro del contenedor con `docker compose exec api python ...`).

---

## 1. Deploy y rollback

### 1.1 Deploy normal

Backup **antes** de cada deploy (ver sección 4):

```bash
docker compose exec api python backup.py create
docker compose exec api python backup.py list
```

Levantar / reconstruir:

```bash
docker compose up -d --build
docker compose logs -f api
```

El contenedor `api` corre `python manage.py migrate` (Alembic upgrade head) automáticamente antes de arrancar Uvicorn (ver `backend/Dockerfile`). Alembic toma la conexión de `DATABASE_URL` en tiempo de ejecución (el valor en `alembic.ini` es solo un placeholder).

Verificar salud tras el deploy:

```bash
curl -s http://localhost:8080/health
curl -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" http://localhost:8080/api/ops/alerts
```

En producción `/health` debe devolver `ok:true`, `db.backend:postgres`, `db.ok:true`, `redis.configured:true`, `redis.ok:true`.

### 1.2 Rollback de aplicación (código)

```bash
# Opción A: revertir el commit problemático conservando historial
git revert <commit-malo>
docker compose up -d --build

# Opción B: volver a un commit anterior conocido
git checkout <commit-anterior>
docker compose up -d --build

docker compose logs -f api
```

Un rollback de código **no** revierte migraciones ya aplicadas. Si el commit revertido incluía una migración incompatible, aplica también el rollback de DB (1.3).

### 1.3 Rollback de base de datos

Bajar una migración con Alembic (solo si la migración tiene `downgrade` y la versión objetivo es compatible con el código desplegado):

```bash
# Revisar versión actual y disponibles
docker compose exec api alembic current
docker compose exec api alembic history

# Bajar un paso, o a una revisión concreta
docker compose exec api alembic downgrade -1
docker compose exec api alembic downgrade 0002_appointments
```

Migraciones disponibles: `0001_production_schema`, `0002_appointments`, `0003_secret_rotations`.

Si el esquema quedó inconsistente o `downgrade` no está soportado, **restaurar desde backup** (ver 4.2), siempre con ventana de mantenimiento:

```bash
docker compose stop api worker admin-web
docker compose run --rm api python backup.py restore /app/backend/backups/ARCHIVO.dump --yes
docker compose up -d
```

### 1.4 Recrear / rotar el admin

Si se pierde el acceso o hay que rotar el token del owner:

```bash
docker compose exec api python manage.py create-admin --email gestion@tu-dominio.com --name "Admin"
```

Imprime el token **una sola vez**; cópialo a `PANEL_ADMIN_TOKEN` en `backend/.env`. Si el email ya existe, rota el token y fuerza rol `owner`. Alternativa idempotente vía variables de entorno: define `PANEL_ADMIN_EMAIL`, `PANEL_ADMIN_TOKEN`, `PANEL_ADMIN_NAME` y reinicia `api` (el arranque siembra el admin). Verificar usuarios:

```bash
docker compose exec api python manage.py list-users
```

Autenticación del panel: header `X-Auth-Token: <token>`, o login con email + `PANEL_LOGIN_CODE`.

---

## 2. Incidentes

### 2.1 Redis caído

Efecto: el sistema **degrada, no cae**. Sin Redis se pierden:

- **Locks de conversación** (`acquire_lock` devuelve `local-no-redis`): sin serialización de mensajes concurrentes del mismo usuario.
- **Debounce** (`enabled()` es false): los mensajes se procesan de inmediato en el webhook, sin agrupar ráfagas.
- **Rate limiting**: sigue funcionando — es **en memoria** (`core/rate_limit.py`), no depende de Redis. En multi-worker cada proceso cuenta por separado.
- **Cola de jobs** (`jobs.enqueue` devuelve false): el worker no recibe trabajo. Los audios de WhatsApp caen al **fallback en línea** (transcripción síncrona dentro del webhook, más lenta pero sin pérdida). Los jobs `tenant.changed`/`audit.event` no se registran vía cola.

`/health` en producción devuelve **503** si `redis.configured` pero `redis.ok:false`. `/api/ops/alerts` emite `{"code":"redis_down","level":"critical"}`.

Diagnóstico y recuperación:

```bash
docker compose ps redis
docker compose logs --tail=100 redis
docker compose exec redis redis-cli ping        # espera PONG
docker compose restart redis
curl -s http://localhost:8080/health
```

Redis usa `--appendonly yes` con volumen `redis-data`, así que la cola persiste a reinicios del contenedor.

### 2.2 Postgres caído

Efecto: **el servicio no funciona**. Sin DB no hay tenants, conversaciones, usage ni auth.

- `/health` devuelve **503** (`db.ok:false`).
- `/api/ops/alerts` emite `{"code":"db_down","level":"critical"}`.

Diagnóstico y recuperación:

```bash
docker compose ps postgres
docker compose logs --tail=100 postgres
docker compose exec postgres pg_isready -U cauce -d cauce
docker compose restart postgres
curl -s http://localhost:8080/health
```

Si el volumen `postgres-data` está dañado, restaurar desde backup (sección 4.2). El contenedor `api` depende de `postgres` sano (`condition: service_healthy`); no arrancará hasta que Postgres pase el healthcheck.

### 2.3 Jobs atascados / dead-letter

Un job que agota `max_attempts` (3 por defecto) va a la lista `jobs:dead_letter` en Redis. Los reintentos se reprograman en `jobs:scheduled` con delay. Tipos de job desconocidos también reintentan y terminan en dead-letter (por diseño, no se descartan en silencio).

Revisar:

```bash
curl -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" "http://localhost:8080/api/ops/dead-letter?limit=100"
```

Devuelve `count` y `jobs` (cada job trae `type`, `payload`, `attempts`, `last_error`, `failed_at`) para diagnóstico. `/api/ops/metrics` también muestra `jobs.dead_letter`. La alerta `jobs_dead_letter` (warning) aparece en `/api/ops/alerts` mientras haya elementos.

No existe endpoint de purga/reencolado; se opera directamente sobre Redis (keys `jobs:dead_letter`, `jobs:default`, `jobs:scheduled`):

```bash
# Inspeccionar
docker compose exec redis redis-cli LLEN jobs:dead_letter
docker compose exec redis redis-cli LRANGE jobs:dead_letter 0 -1

# Reencolar el primero de dead-letter a la cola de trabajo
docker compose exec redis redis-cli RPOPLPUSH jobs:dead_letter jobs:default

# Purgar todo el dead-letter (tras confirmar que no se recupera nada)
docker compose exec redis redis-cli DEL jobs:dead_letter
```

Antes de reencolar, corrige la causa (`last_error`); si el job apunta a un tenant inactivo/eliminado, el worker lo ignora sin error. Revisar el worker:

```bash
docker compose logs --tail=200 worker
docker compose restart worker
```

### 2.4 Tenant con costo disparado

Pausar el tenant de inmediato (deja de resolverse en webhooks/chat; `_tenant_or_404` devuelve 404 para el tenant inactivo):

```bash
curl -X POST -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" \
  http://localhost:8080/api/admin/tenants/{tenant_id}/pause
```

Reanudar cuando esté controlado:

```bash
curl -X POST -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" \
  http://localhost:8080/api/admin/tenants/{tenant_id}/resume
```

Investigar el consumo real:

```bash
curl -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" \
  "http://localhost:8080/api/admin/tenants/{tenant_id}/usage?limit=100"   # summary + events
curl -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" http://localhost:8080/api/tenants   # costo/fee/margen por cliente
```

Prevención: define `COST_ALERT_USD` (>0) para que `/api/ops/alerts` emita `tenant_cost_threshold` (warning) al superar el umbral. Pausar/reanudar y los cambios de config quedan en `audit_events` y encolan un job `tenant.changed`.

### 2.5 Proveedor LLM caído

El engine lanza `LLMError` cuando falta API key o el proveedor responde con error/timeout. En el endpoint de chat webchat esto se traduce a **HTTP 502** (`/api/{tenant_id}/chat`). En canales (WhatsApp/Telegram), el fallo se registra en logs/worker y el mensaje al usuario no se envía; en el worker el job puede reintentar y, si persiste, ir a dead-letter (2.3).

Diagnóstico:

```bash
docker compose logs --tail=200 api worker | grep -i "LLM\|502"
```

Acciones:

- Verificar la key del proveedor por defecto (`DEEPSEEK_API_KEY`) y las referencias `*_env` por tenant.
- Confirmar que el tenant tiene LLM configurado: en `/api/tenants`, campo `llm_key_configured:true`.
- Si el proveedor tiene una caída prolongada y hay adapter alternativo por tenant, reapuntar el modelo con un PATCH de config y encolar el cambio:

```bash
curl -X PATCH -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"config":{"llm":{"model":"...","api_key_env":"OTRA_ENV"}}}' \
  http://localhost:8080/api/admin/tenants/{tenant_id}
```

Recuerda: en producción no se aceptan secretos en claro en el body (`api_key`, `token`, `bot_token`, `secret_token` → 422). Usa referencias `*_env` y registra la rotación con `POST /api/admin/tenants/{tenant_id}/secrets`.

---

## 3. Monitoreo

| Qué | Endpoint / fuente | Notas |
|---|---|---|
| Salud del sistema | `GET /health` | Público. 200 si ok; **503** si falta DB o (en prod) Redis o el backend no es postgres. Muestra `db`, `redis`, `env`, nº de tenants. |
| Métricas operativas | `GET /api/ops/metrics` | Requiere auth (`usage:read`). Usage por tenant (calls, cost_usd, tokens), conteos de conversaciones/mensajes/citas, `jobs.dead_letter`. |
| Alertas | `GET /api/ops/alerts` | Requiere auth. `db_down`/`redis_down` (critical), `jobs_dead_letter` y `tenant_cost_threshold` (warning). |
| Dead-letter | `GET /api/ops/dead-letter?limit=N` | Requiere auth. `count` + jobs con `last_error`. |
| Logs | `docker compose logs -f api worker` | JSON estructurado (una línea por evento, con `ts`/`event`). Secretos redactados automáticamente (`token`/`secret`/`api_key`/`password`/`authorization` → `***`). |

```bash
curl -s http://localhost:8080/health | jq
curl -s -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" http://localhost:8080/api/ops/metrics | jq
curl -s -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" http://localhost:8080/api/ops/alerts | jq
docker compose logs -f --tail=100 api worker
docker compose ps       # estado de contenedores y healthchecks
```

El healthcheck de Docker de `api` golpea `http://127.0.0.1:8002/health`; `postgres` usa `pg_isready`; `redis` usa `redis-cli ping`.

---

## 4. Backups

Herramienta: `backend/backup.py`. Detecta Postgres vs SQLite por `DATABASE_URL`. Con Postgres usa `pg_dump --format=custom` (archivo `.dump`) y `pg_restore --clean --if-exists` (requiere `postgresql-client`, ya instalado en la imagen). Los backups se guardan en `backend/backups/` (`/app/backend/backups` dentro del contenedor).

### 4.1 Crear y listar

```bash
docker compose exec api python backup.py create      # imprime la ruta del backup
docker compose exec api python backup.py list
```

### 4.2 Restaurar (con ventana de mantenimiento)

`restore` exige `--yes` para evitar ejecuciones accidentales. Detiene los servicios que escriben antes de restaurar:

```bash
docker compose stop api worker admin-web
docker compose run --rm api python backup.py restore /app/backend/backups/ARCHIVO.dump --yes
docker compose up -d
curl -s http://localhost:8080/health
```

### 4.3 Backups automáticos

El `worker` crea backups periódicos según `AUTO_BACKUP_INTERVAL_SECONDS` (segundos; `0` = desactivado, p.ej. `86400` para diario). Requiere que el worker esté corriendo. Cada backup automático imprime su ruta en los logs del worker:

```bash
docker compose logs worker | grep "backup creado"
```

Recomendación: copiar `backend/backups/` a almacenamiento externo fuera del host (el volumen local no protege ante pérdida del servidor).
