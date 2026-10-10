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

Autenticación del panel: login con email + contraseña individual (sesión con vencimiento). El header `X-Auth-Token: <token>` sigue aceptando el token de API del owner (`PANEL_ADMIN_TOKEN`) para los `curl` de operación.

### 1.5 Credenciales individuales (transición desde el código compartido)

Desde la migración `0012_panel_user_credentials` cada usuario tiene contraseña propia (scrypt, solo stdlib) y las sesiones se guardan solo como hash SHA-256 con vencimiento (`PANEL_SESSION_HOURS`, 12 h por defecto). Las cuentas existentes quedan **activas y sin contraseña**: nadie pierde acceso.

1. Aplicar la migración (`python manage.py migrate`) y desplegar.
2. Mientras `PANEL_LOGIN_CODE` exista, un usuario **sin contraseña** entra con email + código (modo compatibilidad; el panel muestra el campo «Código de acceso»). Un usuario **con** contraseña ya no puede usar el código.
3. Fijar la contraseña del owner actual (se pide oculta; nunca como argumento):
   ```bash
   docker compose exec api python manage.py set-password --email gestion@tu-dominio.com
   # no interactivo: printf '%s\n' "$NUEVA" | docker compose exec -T api python manage.py set-password --email ... --password-stdin
   ```
   O desde el panel: Usuarios → «Cambiar mi contraseña», usando el código vigente como contraseña actual.
4. El owner crea o resetea las cuentas del equipo en **Usuarios** (contraseña temporal que se muestra una vez; se obliga a cambiarla al entrar).
5. Cuando todos tengan contraseña: **vaciar `PANEL_LOGIN_CODE`** y reiniciar. Revisar con `python manage.py list-users` (columna credencial).
6. `PANEL_ADMIN_TOKEN` queda como token de API de operación del owner: el arranque lo vuelve a escribir en cada reinicio. Para retirarlo, vaciarlo en el entorno y luego «Cerrar sesiones» del owner (invalida el token anterior).

Reglas que aplica el servidor:
- Solo `owner` crea, edita, desactiva/reactiva, resetea contraseñas y cierra sesiones de otros.
- Nunca queda el panel sin owner activo: desactivar o degradar al último owner devuelve 409 (también ante peticiones simultáneas). Nadie se desactiva a sí mismo.
- Desactivar, resetear o «Cerrar sesiones» revoca todas las sesiones y el token estático al instante.
- Login fallido: 401 genérico, límite de 10 intentos/min por IP y evento `auth.login_failed` en auditoría (sin contraseña). Cambios de usuarios: eventos `user.*` sin secretos.
- Recuperación si el único owner perdió la contraseña o quedó desactivado: `python manage.py create-admin --email ...` (rota el token, fuerza `owner` y reactiva) y luego `set-password`.
- En desarrollo, sin `PANEL_LOGIN_CODE`, los usuarios demo sin contraseña siguen entrando por email desde localhost; en producción nunca.

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


---

## 9. Atención autónoma: flags, revisión semanal y reversión

### 9.1 Flags de despliegue gradual

Las capacidades del bot se activan por flag en `tenants.json → tenants.brasper.features`
(Admin API `PATCH /api/admin/tenants` con deep-merge; sin redesplegar). Valores por defecto en
`core/features.py`. Para revertir una capacidad ante un fallo: poner la flag en `false` y
verificar en el panel › Conocimiento (tarjetas "Flags").

| Flag | Qué apaga si va a `false` |
|---|---|
| `knowledge` | FAQ con fuente; las preguntas informativas vuelven al LLM |
| `status_intent` | Derivación con resumen ante "¿ya llegó mi envío?" (vuelve al LLM) |
| `anti_loop` | Límite de repeticiones del bot |
| `audio_confirmation` | Confirmación de cifras ambiguas en audios |
| `webhook_dedup` | Deduplicación por id de mensaje (Meta/Telegram) |
| `presence_required` | Asignar solo a asesores con heartbeat `available` |
| `coex` | Procesar ecos de la app WhatsApp Business (coexistencia) |
| `campaigns` | Promociones de la plataforma IA: oferta en la bienvenida y nota en la cotización (ver §9.9) |
| `operation_status` | Consulta privada de estado de envíos (teléfono verificado por WhatsApp o grant de vinculación) |
| `identity_link` | Vinculación Telegram/webchat desde la cuenta Brasper; además exige `BRASPER_IA_GRANT_KEY` y, en la API, `BRASPER_IA_IDENTITY_LINK_ENABLED=true` |

Las tres últimas vienen en `false`. Activarlas en este orden y solo tras validar la API en un entorno aislado.

### 9.2 Revisión semanal de fallos (piloto)

Cada semana, con `GET /api/ops/metrics` y los eventos estructurados del log:

1. `flows`: conteo, errores y p50/p95 por flujo (`quote`, `info`, `status`, `handoff`, `llm`...).
2. `knowledge.miss`: preguntas sin respuesta aprobada → candidatas a nuevas entradas (PR a `data/knowledge/brasper/faq.json`).
3. `conversation.handoff` por `reason`: distribución de motivos de derivación; `no_advisor_available` indica cola sin cobertura.
4. `bot.repetition`, `audio.ambiguous`, `audio.transcription_failed`, `webhook.duplicate`, `tool.timeout`, `tool.idempotent_replay`.
5. `web_vitals` p75 (panel) y Lighthouse en CI.
6. Correr `python tests/evals/run.py`; añadir un escenario por cada fallo real observado (anonimizado).

Meta del piloto: 80 % de resolución autónoma en tareas elegibles (cotizar, FAQ aprobada,
identificación, cuentas) con cero fallos críticos de permisos, duplicación o datos financieros sin
respaldo. Una respuesta enviada no cuenta como tarea completada.

### 9.3 Documentos públicos y solicitudes de borrado

Las páginas `/privacidad`, `/terminos` y `/eliminacion-de-datos` sirven **solo** versiones publicadas
(`public_documents`). Borrador → revisión → publicar desde el panel › Documentos públicos
(rol con `tenants:write`); cada versión queda auditada (`document.draft`, `document.publish`).
Las solicitudes de eliminación (`deletion_requests`) no borran nada: se verifican y se cierran a
mano desde el mismo panel. Las URL exactas se registran en la app de Meta solo después de publicar.

### 9.4 Coexistencia WhatsApp (cuando se habilite)

Antes de poner `features.coex=true` y `whatsapp.connections[].mode="coex"`: confirmar en la cuenta de
Meta el contrato real de `smb_message_echoes`, `history` y `smb_app_state_sync` (ver plan de
atención autónoma). Los eventos de historial/sincronización nunca disparan respuestas; un eco del
celular pausa el bot y se guarda como actividad humana (`sender=agent`, `agent_email=whatsapp-app`).

### 9.5 Vinculación de chats (Telegram/webchat) y estado privado

1. API: `BRASPER_IA_IDENTITY_LINK_ENABLED=true`. Bot: `BRASPER_IA_GRANT_KEY` (clave Fernet), `features.identity_link=true`,
   `features.operation_status=true` y `quote.api.identity_link_url` con la URL https del portal (`…/vincular-chat`).
   Portal: `VITE_TELEGRAM_BOT_USERNAME` para el botón de Telegram.
2. Recorrido: el cliente pregunta por su envío → el bot deriva y envía el enlace del portal → el cliente inicia sesión
   y toca «Vincular este chat» → el token (5 min, un uso) vuelve al chat por deep-link `/start` o pegado → grant de 30 min
   cifrado en `identity_grants`. El token se redacta antes de guardar el mensaje y nunca llega al LLM.
3. Incidentes: rotar `BRASPER_IA_GRANT_KEY` invalida todos los grants (los clientes vuelven a vincular). El cliente puede
   retirar sus vínculos desde el portal (`DELETE /brasper/identity-links`). Un timeout del canje no se reintenta.

4. Con `AUTH_REQUIRED=true` en la API, todo `/brasper/ai/*` exige JWT + secreto: definir
   `BRASPER_IA_SERVICE_USERNAME` / `BRASPER_IA_SERVICE_PASSWORD` (cuenta de servicio dedicada, rotación como cualquier
   secreto). Sin ellas, la integración privada responde 401 y el bot deriva a asesor (evento
   `brasper_api.service_auth_failed`).

### 9.6 Alcance por canal, número y sector

Panel › Accesos (o `python manage.py set-scope --email … --channels telegram --connections conn-a --sectors empresas`).
Vacío = sin restricción. El backend filtra bandeja, detalle, adjuntos, respuestas, asignación y derivación automática.
Los adjuntos que envía el cliente (comprobantes, documentos, audios) requieren además el permiso `media:private`
(owner, admin y agent). Un alcance ilegible en la base cierra el acceso en vez de abrirlo.

### 9.7 Salidas inciertas, ecos diferidos y Redis caído

- `outbound_messages`: cada respuesta automática queda `sent`, `cancelled` (intervino un humano antes de enviar),
  `failed` (4xx) o `uncertain` (timeout/5xx/caída). Las inciertas se ven en la ficha del cliente y **no** se reintentan.
- Un eco Coex que llega mientras nuestro envío está en vuelo se difiere y se resuelve por id del proveedor; si el
  envío termina incierto o el proceso cae, el worker lo trata como actividad humana a los 60 s.
- `history` / `smb_app_state_sync` se guardan en `channel_events` (estado `stored`) para replay cuando el contrato Meta
  esté confirmado; hoy no se procesan.
- El lock por conversación vive siempre en `conversation_locks` (Redis se suma si responde). Si la base no responde,
  el mensaje se rechaza como "ocupado" en vez de procesarse sin exclusión. El lease (45 s) se renueva cada 15 s
  mientras se procesa; si la renovación falla se cancela el trabajo y no se responde (evento
  `conversation.lease_lost`).

### 9.8 Contactos

`contacts` + `contact_aliases` (proveedor, conexión, identificador). El mismo teléfono verificado por WhatsApp en dos
números es un solo contacto; un BSUID sin teléfono es un contacto propio; nunca se vincula por nombre o username. Los
choques quedan en Panel › Accesos › Contactos por revisar y no se fusionan automáticamente. El backfill de
conversaciones históricas corre al iniciar y es idempotente.

### 9.9 Promociones (campañas en la plataforma IA)

- Se administran en Panel › Promociones y se guardan en la base IA (migración `0013_ia_campaigns`). La API financiera no se modifica ni se usa para administrarlas; solo se consultan tasas/rutas, cliente e historial.
- Ciclo: borrador → publicar (valida rutas contra `/coin/tax-rate`, imágenes aprobadas en su idioma, vigencia y cupo) → desactivar. Publicar no envía mensajes masivos: la oferta solo acompaña la respuesta a un mensaje del cliente.
- Beneficios: el asesor los reserva desde el **expediente** de la ficha (promoción y versión aceptadas por el cliente, ruta y monto compatibles) con la referencia de la operación registrada en Brasper; si Brasper no confirma la elegibilidad debe escribir la verificación humana. Consumir exige la referencia oficial registrada en el expediente y una nota (el depósito confirmado no basta); liberar o vencer también piden nota. Todo queda en `campaign_benefit_events` y auditoría.
- `tenants.brasper.campaigns.discount_applicable` (por defecto `false`): activarlo solo cuando el responsable de Brasper confirme que el asesor puede registrar el importe con el descuento de IA. Mientras sea `false`, el bot no promete el ahorro (evento `campaign.discount_not_applicable`).
- Migrar campañas del diseño anterior: exportarlas de la base financiera (consulta de solo lectura en `docs/plans/RETIRADA-CAMPANAS-API-2026-10-10.md`) e importar con `python manage.py import-campaigns --file export.json`. Quedan como borradores para revisión. La API ya no expone su administración.
- Migración `0014`: repara una tabla `campaign_offers` del diseño anterior (ofertas antiguas quedan `legacy_unverified`, sin reenvío) y agrega el desglose y la evidencia a los beneficios.
- Expediente: al pasar al pago con una cotización vigente se abre en la ficha; los comprobantes se enlazan; el asesor verifica el depósito, genera la transacción en Brasper y registra la referencia. IA nunca confirma pagos.

