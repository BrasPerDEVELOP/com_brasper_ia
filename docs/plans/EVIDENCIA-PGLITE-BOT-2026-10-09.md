# Evidencia: migraciones Alembic del bot contra PostgreSQL (PGlite) — 2026-10-09

Validación de laboratorio de `backend/migrations/versions` (0001 → 0010_contacts_identity_links) y del SQL
runtime de los módulos nuevos sobre un motor PostgreSQL real (PGlite), en una máquina Windows donde App
Control bloquea PostgreSQL nativo y las DLL de psycopg/psycopg2 (no se intentó saltar ese bloqueo).

## Entorno y versiones

| Pieza | Versión |
|-------|---------|
| Motor | `PostgreSQL 18.3 (PGlite 0.5.8) on wasm32-unknown-emscripten` (`server_version_num=180003`), collation `C` |
| Servidor de protocolo | `@electric-sql/pglite-socket` 0.2.11, Node v24.21.0, `--db=memory://`, puerto 55440 (solo 127.0.0.1) |
| Intérprete | venv de `com_brasper_api`: Python 3.12.14, SQLAlchemy 2.0.52, Alembic 1.19.2, asyncpg 0.31.0 |
| Migraciones | las del repo sin cambios (`backend/migrations/versions/0001…0010`), incluida la versión de 0010 con `outbound_messages` y `channel_events` |

## Herramienta

`backend/tests/pglite_migrations.py` (laboratorio, no es parte de CI ni del runtime):

- No ejecuta `migrations/env.py` (que lee `.env`/`DATABASE_URL`): arma el `EnvironmentContext` de Alembic en
  memoria con la conexión síncrona de `AsyncConnection.run_sync` sobre asyncpg; mismo modo que producción
  (`target_metadata=None`, una transacción para toda la corrida).
- No lee variables de entorno ni `.env`. Rechaza hosts distintos de `127.0.0.1`/`localhost` y bases que no
  empiecen por `postgres`/`brasper_test`. El `drill` borra el esquema `public` entre escenarios.
- Convierte `?` → `$1..$n` (equivalente asyncpg de `db._qmark_to_pg`) y mide `rowcount` con el status de asyncpg
  (`INSERT 0 1`, `UPDATE 0`…).

Comandos:

```bash
node <pglite>/node_modules/@electric-sql/pglite-socket/dist/scripts/server.js --db=memory:// --port=55440
cd backend
C:/Users/USER/Documents/GitHub/com_brasper_api/.venv/Scripts/python.exe tests/pglite_migrations.py \
    --port 55440 drill --out <scratchpad>/pglite_bot_drill.json
```

## Datos sintéticos (semilla en 0006)

Se sube `base → 0006_lead_data` y se reproduce además el esquema que creaba en runtime el commit desplegado
`539bc5d` antes de existir 0009 (`init_db`/`_ensure_columns`/`public_docs.ensure_schema`): columnas
`conversations.connection_id`, `messages.sender`, `messages.agent_email`; tablas `public_documents` (sin índice
único), `deletion_requests`, `idempotency_keys`, `agent_presence`, `conversation_notes`, `conversation_tags`.

Filas: 2 `panel_users`, 1 `tenants`, 5 conversaciones (2 `active`, 1 `handoff` con asesor, 2 `closed`; WhatsApp
en dos conexiones, Telegram, webchat; `lead_data` JSON con acentos), 15 mensajes (uno con `media_json`), uso,
auditoría JSONB, cita, rotación de secreto, historial de `public_documents` (privacidad/es v1–v3,
terminos/es v1, terminos/pt v1), solicitud de eliminación, clave de idempotencia, presencia, nota y etiqueta.

## Resultados

### Paso 2 — upgrade 0006 → head, re-upgrade y preservación — **PASA**

| Verificación | Resultado |
|--------------|-----------|
| `upgrade 0006_lead_data` | OK |
| `upgrade head` (0007→0010 en una transacción) | OK → `0010_contacts_identity_links` |
| `upgrade head` otra vez | no-op: huella de columnas, índices y constraints idéntica (md5) y datos idénticos |
| Preservación (count + md5 de `row_to_json` de las columnas originales, sin `tenant_id`/`tenant_scope` que 0007 quita por diseño) | 13/13 tablas iguales: conversations 5, messages 15, panel_users 2, public_documents 5, etc. `tenants`/`channel_configs`/`connector_configs` eliminadas por diseño (0007) |
| Tablas nuevas | `contacts`, `contact_aliases`, `contact_conflicts`, `identity_grants`, `conversation_locks`, `outbound_messages`, `channel_events` + las de 0009 (`public_document_heads`, `agent_profiles*`, `media_library*`, `engagement_*`, `satisfaction`, `channel_receipts`) |
| Columnas | `conversations.contact_id` (NULL en históricos; lo asigna `contacts.backfill()`), `conversations.human_revision` (`integer NOT NULL DEFAULT 0`, valor 0 en todas), `connection_id` existente se respeta (0009 no la re-crea; valores `pnid-1/pnid-2/NULL` intactos) |
| Índices | `public_documents_version` (UNIQUE), `contacts_phone`, `contact_aliases_contact`, `engagement_jobs_due`, `outbound_provider`, `outbound_inflight`, `channel_events_state` y PKs |
| Backfill 0009 | `public_document_heads` = MAX(version) por slug/lang (privacidad/es 3, terminos/es 1, terminos/pt 1); `engagement_settings` id=1 versión 0 con payload JSON válido |
| `tenant_id` en `conversations/messages/usage_events/audit_events` | eliminado |

### Paso 3 — downgrade rechazado — **PASA**

| Caso | Resultado |
|------|-----------|
| head → `downgrade 0009_autonomous_attention` | `RuntimeError` de 0010; `alembic_version` sigue en 0010; esquema y datos idénticos |
| head → `downgrade base` | se detiene en 0010 con el mismo error; esquema idéntico |
| 0009 → `downgrade 0008_brasper_modeling` (escenario B) | `RuntimeError` de 0009; versión sigue 0009; esquema y datos idénticos; después `upgrade head` OK |

### Paso 4 — SQL runtime sobre la BD migrada — **PASA** (58 sentencias, 0 inválidas)

| Módulo | Comprobado |
|--------|-----------|
| `contacts.py` | `ensure_schema` no-op; alias `ON CONFLICT(provider, connection_id, external_id) DO NOTHING`: 1 al crear, **0** en el duplicado (conserva el primer contacto); `INSERT INTO contacts`; `INSERT INTO contact_conflicts VALUES (…,NULL,NULL)` = 1; `attach` 1 y luego 0; `backfill`, `conflicts`, `resolve_conflict` = 1 |
| `db_lock.py` | `ON CONFLICT(name) DO UPDATE … WHERE conversation_locks.expires_at < $4`: libre `INSERT 0 1`, tomado `INSERT 0 0` (dueño sigue `tok-A`), vencido `INSERT 0 1` (dueño pasa a `tok-C`); `release` con token ajeno 0, propio 1. Orden texto ISO = cronológico (collation `C`) |
| `identity_link.py` | upsert `ON CONFLICT(conversation_id) DO UPDATE SET … excluded.*`: 1 y 1 (valores actualizados); `grant_for` select; `revoke` 1 |
| `db._creation_lock` | `SELECT pg_advisory_xact_lock(hashtext($1))` válido; 1 lock advisory dentro de la transacción, reentrante, 0 tras el commit |
| `outbound.py` | `ensure_schema` no-op; `deliver` INSERT de 13 columnas (también con `human_revision` NULL); `in_flight`; `_set` con `COALESCE(?, provider_message_id)` (NULL conserva el id); `apply_status` select por `(connection_id, provider_message_id)`, avance sent→delivered→read y `failed` (Telegram con `connection_id=''`); `for_conversation` |
| `channel_events.py` | `ensure_schema` no-op; `record` `ON CONFLICT(provider, connection_id, event_id) DO NOTHING`: nuevo 1, reintento **0**, mismo `event_id` en otra conexión 1, Telegram con `connection_id=''` 1; `replay`, `reconcile_echoes`, `mark` 1; `sweep_stale_echoes` select y `UPDATE outbound_messages … 'uncertain'` 1 |

## Hallazgos

1. **0009 aborta si el historial de `public_documents` tiene versiones duplicadas** (escenario C).
   `backend/migrations/versions/0009_autonomous_attention.py:28` crea
   `UNIQUE INDEX public_documents_version (slug,lang,version)` sobre una tabla que el runtime desplegado
   (`539bc5d`, `public_docs.create_draft`: `MAX(version)+1` sin lock) pudo llenar con duplicados por dos
   borradores simultáneos. Resultado en PG: `UniqueViolationError [23505] … Key (slug, lang, version)=(privacidad, es, 3) is duplicated`;
   la transacción entera se revierte (queda en 0006, sin pérdida de datos), pero el deploy no avanza. El mismo
   `CREATE UNIQUE INDEX` en `backend/core/public_docs.py:37` haría fallar `init_db` en el arranque.
   Mitigación: antes del deploy correr
   `SELECT slug, lang, version, count(*) FROM public_documents GROUP BY 1,2,3 HAVING count(*) > 1;`
   y, si hay filas, renumerar (o una migración 0011 previa al índice que renumere duplicados con
   `version = MAX+n` conservando todas las filas). No se editó 0009.
2. **`db.create_appointment` y `db.add_secret_rotation` fallan en una BD construida por migraciones.**
   0007 (`backend/migrations/versions/0007_remove_multitenant.py:49`) solo quita `tenant_id` de
   `conversations/messages/usage_events/audit_events`; `appointments.tenant_id` y `secret_rotations.tenant_id`
   siguen `NOT NULL` (de 0002/0003). Los INSERT de `backend/core/db.py:1083` y `backend/core/db.py:1168` no
   envían `tenant_id` → `NotNullViolationError [23502]` en ambas. Afecta a `POST` de rotación de secretos
   (`api/routes.py:584`) y a `core/calendar_adapter.py:122`. Preexistente (también en `HEAD`), no lo introduce
   0009/0010. Arreglo sugerido: migración nueva `ALTER TABLE appointments DROP COLUMN IF EXISTS tenant_id; ALTER TABLE secret_rotations DROP COLUMN IF EXISTS tenant_id;`
   (o `ALTER COLUMN tenant_id SET DEFAULT 'brasper'`), sin tocar 0007.
3. **Riesgo de 0007 en bases multi-tenant antiguas** (escenario D): si el mismo `conversations.id` existe en
   dos tenants, `ALTER TABLE conversations ADD PRIMARY KEY (id)`
   (`0007_remove_multitenant.py:47`) falla con `UniqueViolationError … Key (id)=(c-active01) is duplicated`;
   se revierte todo y queda en 0006. Solo aplica a una BD que aún no pasó 0007; comprobar con
   `SELECT id FROM conversations GROUP BY id HAVING count(*) > 1;`.
4. Nota de herramienta (no del bot): tras un error dentro de la transacción, PGlite responde al `ROLLBACK` sin
   tag de comando y asyncpg lanza `AttributeError: 'NoneType' object has no attribute 'decode'`; el runner guarda
   el error original de la migración. El rollback sí ocurre (versión, esquema y filas verificados).

## Limitaciones

- PGlite es PostgreSQL **18.3** compilado a WASM (32 bits), no el servidor PostgreSQL 16 de producción.
  Diferencias de versión menores (planner, mensajes) no se cubren.
- **Una sola sesión de backend** compartida y un cliente a la vez: no hay concurrencia real. No se probaron
  bloqueos entre sesiones (advisory lock esperando a otra sesión, carrera de `ON CONFLICT` entre dos webhooks,
  takeover de `conversation_locks` en paralelo). Las semánticas de `rowcount` sí son las de PostgreSQL.
- El driver del runtime del bot es **psycopg 3**, que no carga en esta máquina; aquí se usó asyncpg. psycopg envía
  `str` con tipo `unknown` y asyncpg exige tipos exactos (por eso los `TIMESTAMPTZ` se pasan como `datetime` en la
  prueba de `appointments`/`secret_rotations`). El error de `tenant_id` es independiente del driver.
- Alembic corre con SQLAlchemy + asyncpg vía `run_sync`, no con `postgresql+psycopg` como en `migrations/env.py`.
- Antes del deploy real sigue siendo necesario un ensayo en PostgreSQL 16 (Docker/CI) con copia de producción.
