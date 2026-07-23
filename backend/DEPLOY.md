# Deploy · Backend De Produccion

Guia operativa para levantar la plataforma con FastAPI, Postgres, Redis, panel Next.js y reverse proxy.

## 1. Variables

```bash
cp backend/.env.example backend/.env
```

Completa como minimo:

| Variable | Obligatoria | Uso |
|---|:--:|---|
| `APP_ENV=production` | Si | Activa modo seguro |
| `DATABASE_URL` | Si | Conexion Postgres |
| `REDIS_URL` | Si | Redis para estado temporal |
| `POSTGRES_DB` | Si | DB del contenedor Postgres |
| `POSTGRES_USER` | Si | Usuario Postgres |
| `POSTGRES_PASSWORD` | Si | Password Postgres |
| `DEEPSEEK_API_KEY` | Si | LLM por defecto de Brasper |
| `PANEL_ADMIN_EMAIL` | Si | Owner inicial |
| `PANEL_ADMIN_TOKEN` | Si | Token opaco del owner |
| `PANEL_LOGIN_CODE` | Si | Codigo temporal de login |
| `SITE_ADDRESS` | Si (prod) | Dominio del panel/API para Caddy + TLS (en `.env` de la raíz) |
| `CORS_ALLOW_ORIGINS` | No* | *Panel y API van en el mismo dominio (mismo origen) → CORS no aplica. Solo si sirves el panel en otro host |
| `META_APP_SECRET` | Canal WA | Firma de WhatsApp |
| `WHATSAPP_VERIFY_TOKEN` | Canal WA | Verificacion de webhook Meta |
| `WHATSAPP_REQUIRE_SIGNATURE=true` | Canal WA | Rechaza webhooks sin firma valida |
| `TELEGRAM_TOKEN` | Canal TG | Token de BotFather |
| `TELEGRAM_SECRET` | Canal TG | Secret del webhook Telegram |

Genera el token admin:

```bash
cd backend
../.venv/bin/python manage.py create-admin --email gestion@tu-dominio.com --name "Admin"
```

Copia el token impreso a `PANEL_ADMIN_TOKEN`.

## 2. Arranque

### Desarrollo local (HTTP, sin dominio)

```bash
docker compose up -d --build
docker compose logs -f api
```

Proxy en `http://localhost:8080` (panel + API en el mismo origen).

### Producción (dominio real + HTTPS automático)

1. Apunta el DNS (A/AAAA) de tu dominio a la IP del servidor.
2. Define el dominio para Caddy (en el `.env` de la raíz o exportando la var):

   ```bash
   echo 'SITE_ADDRESS=panel.tu-dominio.com' >> .env
   ```

3. Despliega usando el script automatizado (que descarga la última versión y reconstruye los contenedores de forma segura):

   ```bash
   cd scripts/
   bash scripts/deploy.sh
   ```

Caddy expone 80/443 y saca/renueva el certificado TLS solo (Let's Encrypt).
El panel y la API quedan en el **mismo dominio**, así que el panel usa rutas
relativas (`NEXT_PUBLIC_API_BASE` vacío) y **no hay CORS que configurar**.

El contenedor `api` ejecuta `python manage.py migrate` antes de iniciar Uvicorn.

El stack levanta:

- `api`
- `worker`
- `admin-web`
- `reverse-proxy`
- `postgres`
- `redis`

URL local del proxy: `http://localhost:8080`.

## 3. Datos Y Migraciones

Produccion usa Alembic. Tambien se conserva un bootstrap idempotente en runtime
para desarrollo/local, pero el camino correcto de deploy es:

```bash
cd backend
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py init
```

En Docker, `manage.py migrate` ya corre al arrancar `api`.

Tablas actuales (Single-Tenant Brasper):

- `panel_users`
- `customers`
- `conversations`
- `messages`
- `quotes`
- `usage_events`
- `audit_events`
- `appointments`
- `secret_rotations`

La configuración del canal se lee estáticamente desde el entorno y `config/tenants.json`.

## 4. Seguridad

Con `APP_ENV=production`:

- No se siembran usuarios demo.
- Se purgan tokens demo si existian.
- Login siempre exige `PANEL_LOGIN_CODE`.
- **El arranque falla (fail-fast)** si `DATABASE_URL` no es Postgres o falta `REDIS_URL` — SQLite queda imposible en produccion.
- `/health` falla si Postgres o Redis no responden.
- Telegram exige secret token por tenant.
- WhatsApp debe exigir firma si `WHATSAPP_REQUIRE_SIGNATURE=true`.

Revisa que estos tokens no funcionen:

```bash
curl -H "X-Auth-Token: demo-owner" http://localhost:8080/api/me
```

Debe responder `401`.

## 5. Canales

### Telegram (canal del lanzamiento inicial)

1. Crea el bot con BotFather y pon su token en `TELEGRAM_TOKEN_<TENANT>`.
2. `TELEGRAM_SECRET_<TENANT>` = cadena aleatoria PROPIA (no el token):
   `openssl rand -hex 32`.
3. Con URL publica registra el webhook:

```bash
POST /api/{tenant}/telegram/set-webhook
{"base_url":"https://<SITE_ADDRESS>"}
```

Webhook publico esperado:

```text
https://<SITE_ADDRESS>/telegram/webhook/{tenant_id}
```

### WhatsApp (diferido)

El código ya cumple la API oficial de Meta; se activa llenando variables.
Instructivo completo paso a paso: **`backend/WHATSAPP_SETUP.md`**.
Webhook público: `https://<SITE_ADDRESS>/webhook`.

## 6. Verificacion

```bash
curl -s http://localhost:8080/health
curl -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" http://localhost:8080/api/ops/metrics
curl -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" http://localhost:8080/api/ops/alerts
cd backend && ../.venv/bin/python tests/run_checks.py
```

En produccion `/health` debe devolver:

- `ok: true`
- `db.backend: postgres`
- `db.ok: true`
- `redis.configured: true`
- `redis.ok: true`

## 7. Backup Y Rollback

Crear backup antes de cada deploy:

```bash
docker compose exec api python backup.py create
docker compose exec api python backup.py list
```

Rollback de aplicacion:

```bash
git checkout <commit-anterior>
docker compose up -d --build
docker compose logs -f api
```

Restore de datos solo con ventana de mantenimiento:

```bash
docker compose stop api worker admin-web
docker compose run --rm api python backup.py restore /app/backend/backups/ARCHIVO.dump --yes
docker compose up -d
```

## 8. Faltante Operativo

Antes de venderlo como plataforma completa de alto volumen faltan:

- Worker avanzado para audios/transcripcion.
- Validaciones de negocio por vertical/canal.
