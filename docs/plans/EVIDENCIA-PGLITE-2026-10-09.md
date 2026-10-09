# Evidencia: migraciones 083/084 de `com_brasper_api` sobre PGlite (2026-10-09)

> **Alcance honesto.** Todo lo de este documento se ejecutó contra **PGlite** (PostgreSQL 18.3 compilado a WASM) servido por protocolo PG con `@electric-sql/pglite-socket`, en una máquina Windows 11 sin PostgreSQL nativo ni Docker. **No sustituye** una prueba en PostgreSQL 16 servidor (versión de producción), **no prueba concurrencia ni bloqueos de fila** y sólo usó datos **sintéticos**. No se conectó a ninguna base de datos remota ni de producción, ni se leyó `.env`.

## 1. Entorno y versiones

| Componente | Versión |
|---|---|
| Motor | `PostgreSQL 18.3 (PGlite 0.5.8) on wasm32-unknown-emscripten ... 32-bit` (salida de `SELECT version()`) |
| Servidor socket | `@electric-sql/pglite-socket` 0.2.11, Node v24.21.0 |
| Python (venv del API) | 3.12.14 — SQLAlchemy 2.0.52, Alembic 1.19.2, asyncpg 0.31.0, pytest 9.1.1 |
| Repo | `com_brasper_api` con trabajo sin commitear (no se hizo reset/checkout/stash) |

Servidores (uno por escenario, todos `memory://`, levantados desde la carpeta donde está instalado PGlite):

```sh
node node_modules/@electric-sql/pglite-socket/dist/scripts/server.js --db=memory:// --port=55433  # A
node node_modules/@electric-sql/pglite-socket/dist/scripts/server.js --db=memory:// --port=55434  # B
node node_modules/@electric-sql/pglite-socket/dist/scripts/server.js --db=memory:// --port=55435  # C
node node_modules/@electric-sql/pglite-socket/dist/scripts/server.js --db=memory:// --port=55436  # D
```

No se tocó el servidor preexistente en `127.0.0.1:55432`.

## 2. Herramienta creada (sin cambiar el comportamiento de producción)

`app/db/migrations/env.py` construye una URL `postgresql+psycopg2://` desde `app.core.settings` (lee `.env`) y psycopg2 está bloqueado por App Control. En vez de modificarlo se añadió en `com_brasper_api`:

| Archivo | Función |
|---|---|
| `scripts/validate_migrations_pglite.py` | CLI: `upgrade/downgrade/current` (Alembic vía `AsyncConnection.run_sync` sobre asyncpg con `ssl=False`, `statement_cache_size=0`, `AUTOCOMMIT` igual que producción), `sql`, `query`, `snapshot` (huella de catálogo y count + md5 por tabla; con `--base` también md5 sólo con las columnas que existían antes), `compare`, `dump` y `restore` (backup lógico) |
| `scripts/pglite_alembic/env.py` | `env.py` alternativo, sólo para laboratorio: replica `run_migrations_online` (esquemas `user`/`blog`, `public.alembic_version`, `search_path`, `render_as_batch`) pero recibe la conexión ya abierta; **no importa settings ni lee `.env`**. Usa las **mismas** versiones de `app/db/migrations/versions` (`version_locations`) |
| `scripts/pglite_alembic/script.py.mako` | Copia de la plantilla (Alembic la exige en `script_location`) |
| `scripts/pglite_alembic/seed_pre_083.sql` | Semilla sintética en 082 |
| `scripts/pglite_alembic/seed_post_084_clean.sql` | Datos en columnas o tablas nuevas que respetan la restricción antigua |
| `scripts/pglite_alembic/seed_post_084_multiuse.sql` | Varios canjes **vivos** del mismo cupón y usuario (sólo posible tras 083) |
| `scripts/pglite_alembic/run_drill.sh` | Orquesta los escenarios A–D |

No se modificó código de la app, migraciones ni tests.

Comando completo (desde la raíz de `com_brasper_api`, con los 4 servidores arriba):

```sh
sh scripts/pglite_alembic/run_drill.sh <out_dir> .venv/Scripts/python.exe
```

Comandos individuales equivalentes: `python scripts/validate_migrations_pglite.py --port 55433 upgrade 082`, `... sql scripts/pglite_alembic/seed_pre_083.sql`, `... snapshot X.json [--base Y.json]`, `... compare X.json Y.json`, `... dump DIR`, `... --port 55435 restore DIR`.

## 3. Datos sintéticos (semilla en 082)

- 4 usuarios (uno soft-deleted, uno asesor), 2 bancos, 3 cuentas destino, 1 tasa y 1 comisión.
- 4 cupones: `PRIMERENVIO` (beneficio de primer envío, `per_user_limit=1`), `PROMO3X` (`per_user_limit=3`), `LEGACY5` (sin límite por usuario) y `VIEJOBORRADO` (soft-deleted, `EXPIRED`).
- 12 transacciones con todos los estados del enum (`pending`, `completed`, `failed`, `checked`, `verification`, `verified`). El enum `transaction.transaction_status` **no tiene `cancelled`**: una transacción "cancelada" se representó como `deleted=true` (que es como se libera el canje, según 052).
- Usos históricos múltiples del mismo cupón por el mismo usuario: 3 transacciones `LEGACY5` de Ana sin fila de canje (historia previa a 050) y `PROMO3X` de Ana con 2 canjes soft-deleted y 1 vivo.
- 7 canjes en `world_cup.coupon_redemptions` (4 vivos y 3 soft-deleted).

## 4. Resultados

### Tarea 1 — upgrade 082 → head con datos (escenario A): **OK**

| Verificación | Resultado |
|---|---|
| `upgrade 082` desde BD vacía | `alembic_version = 082` |
| Restricción antigua activa en 082 | Insertar un 2.º canje vivo `PROMO3X`/Ana → `UniqueViolationError ... "uq_coupon_redemptions_coupon_user_live"` (esperado) |
| `upgrade head` | `alembic_version = 084` |
| Datos preservados (md5 de cada tabla calculado sólo con las columnas que existían en 082) | **34/35 tablas idénticas**. La única diferencia es `public.alembic_version` (esperada). `coupons` (4), `transactions` (12), `coupon_redemptions` (7) y `user` (4) mantienen el mismo md5 |
| Columnas nuevas | `coupons.campaign_rules jsonb NULL`, `coupons.campaign_version integer NOT NULL DEFAULT 1` (backfill = 1 en las 4 filas), `coupons.published_version integer NULL`, `transactions.coupon_campaign_version integer NULL` |
| Índices y constraints nuevos | `coupon_campaign_versions_pkey`, `uq_campaign_version UNIQUE (coupon_id, version)`, FK `coupon_id → transaction.coupons(id)`; `ai_identity_links_pkey`, `ai_identity_links_token_hash_key`, `ai_identity_links_grant_hash_key` (UNIQUE), `ix_user_ai_identity_links_user_id` |
| Índice retirado | `uq_coupon_redemptions_coupon_user_live` desaparece; `ix_coupon_redemptions_coupon_user` (no único, de 050) se conserva |
| Re-ejecutar `upgrade head` | No-op: `compare A_head A_head_rerun` → `identical_schema: true`, `identical_data: true` |

### Tarea 2 — downgrade

**(a) Datos limpios (A, con `seed_post_084_clean.sql` cargado en head): OK, con pérdida esperada de los datos nuevos**

- `downgrade 083`: OK; `"user".ai_identity_links` deja de existir (se pierden sus 3 filas).
- `downgrade 082`: OK; se repone `uq_coupon_redemptions_coupon_user_live` y se eliminan `campaign_rules/campaign_version/published_version`, `coupon_campaign_version` y la tabla `coupon_campaign_versions` (se pierden 3 versiones de campaña y las reglas).
- `compare A_082_seeded A_back_to_082`: `identical_schema: true`, `identical_data: true`. Las 35 tablas de 082 tienen el mismo md5 que antes del upgrade.
- Insertar un 2.º canje vivo vuelve a fallar con `UniqueViolationError` (la restricción quedó repuesta).
- Ida y vuelta (`upgrade head` otra vez): `compare A_head A_head_again` → idéntico.

**(b) Varios canjes vivos del mismo cupón y usuario (B): el downgrade a 082 FALLA, como se esperaba**

- Tras `seed_post_084_multiuse.sql`: `PROMO3X` / Ana tiene **3 canjes vivos** (permitido por `per_user_limit=3` después de 083).
- `downgrade 083` (084→083): OK (se pierden las 3 filas de `ai_identity_links`).
- `downgrade 082` (083→082): **exit=1**

  ```
  asyncpg.exceptions.UniqueViolationError: could not create unique index "uq_coupon_redemptions_coupon_user_live"
  DETAIL:  Key (coupon_id, user_id)=(00000000-0000-4000-8400-000000000002, 00000000-0000-4000-8000-000000000001) is duplicated.
  ```
- El estado queda consistente: `alembic_version = 083`, y `compare B_083_after_downgrade B_after_failed_downgrade` → esquema y datos **idénticos**. Como `create_index` es la primera operación del `downgrade()`, nada se aplicó a medias. Los 3 canjes vivos siguen ahí y no se borró ningún registro.
- Conclusión, coherente con el plan: si hay usos múltiples, la reversión segura es **backup/restore** (o desplegar el código anterior manteniendo el esquema 083), **nunca borrar canjes** para forzar el índice. No se modificaron migraciones para borrar datos.

### Tarea 3 — backup/restore (B → C): **OK**

PGlite no trae `pg_dump`. Se usó un **backup lógico reproducible** (`dump`):

1. `manifest.json` con la revisión Alembic (`084`), filas, md5 por tabla y `last_value` de las secuencias.
2. Un `.jsonl` por tabla (`row_to_json`) para las 36 tablas de datos.
3. Restauración (`restore`): en la instancia C vacía, `upgrade head` (esquema desde las migraciones), luego `SET session_replication_role = replica`, `DELETE` de las semillas que crean las migraciones y `INSERT ... SELECT * FROM json_populate_recordset(NULL::tabla, ...)`; después `setval` de las secuencias.

Se tomó en B, en head **con los canjes múltiples**, antes de intentar el downgrade. `compare B_head_multiuse C_restored` → `identical_schema: true`, `identical_data: true` en las 37 tablas. Tablas financieras:

| Tabla | Filas B | Filas C | md5 (igual en B y C) |
|---|---|---|---|
| `transaction.coupons` | 4 | 4 | `e364aa947624ee98b3133fb47a7aad45` |
| `transaction.transactions` | 14 | 14 | `8942e0ed09a1d43e6fc7bb716d0664b6` |
| `world_cup.coupon_redemptions` | 9 | 9 | `5c032ae7f9d237a4a3525281ad1d074d` |
| `transaction.coupon_campaign_versions` | 3 | 3 | `20cbfe4f591c5e188e1e44e25082c933` |
| `"user".ai_identity_links` | 3 | 3 | `7988b152e1e085496ae4f72fdeb34aec` |
| `"user"."user"` | 4 | 4 | `2ed52da892dc202a61da32f711008904` |

El md5 es `md5(string_agg(row_to_json(fila)::text ORDER BY ...))` sobre todas las columnas.

> Este drill valida el procedimiento lógico con PGlite, **no** el `pg_dump -Fc` / `pg_restore` de `scripts/backup.sh` en producción. Ese procedimiento se debe ensayar en un PostgreSQL 16 real antes del deploy.

### Tarea 4 — pytest del API: **OK**

```
.venv/Scripts/python.exe -m pytest -q tests/test_identity_links.py tests/test_brasper_ai_identity.py tests/test_campaigns.py tests/test_commission_selection.py tests/test_coupon_percentage.py tests/test_coupon_concurrency.py tests/test_transactions.py tests/test_brasper_ai_routes.py
105 passed, 8 warnings in 1.27s
```

Son 105, no los 103 del baseline: el árbol de trabajo tiene tests sin commitear que cambiaron después de fijarlo. Las 8 advertencias son deprecaciones de Pydantic y Starlette. Estos tests no usan PGlite.

### Robustez (escenario D) — hallazgo en 083

Sobre una BD en 082 donde `uq_coupon_redemptions_coupon_user_live` **no existe** (borrada a mano para simular un entorno que no la tenga):

- `upgrade 083` → **exit=1** `UndefinedObjectError: index "uq_coupon_redemptions_coupon_user_live" does not exist`.
- Estado **a medias**: `alembic_version` sigue en `082`, pero las 4 columnas nuevas **y** la tabla `coupon_campaign_versions` ya quedaron creadas.
- Reintentar `upgrade 083` → **exit=1** `DuplicateColumnError: column "campaign_rules" of relation "coupons" already exists`, así que hace falta arreglarlo a mano.

Causa: `app/db/migrations/env.py` ejecuta con `isolation_level="AUTOCOMMIT"`, así que cada DDL se confirma sola y una migración no es atómica. Además, `083.upgrade()` deja el `drop_index` sin `IF EXISTS` al **final**. En producción también es AUTOCOMMIT, así que el comportamiento sería el mismo si el índice no existiera. Antes de desplegar conviene verificar `SELECT 1 FROM pg_indexes WHERE schemaname='world_cup' AND indexname='uq_coupon_redemptions_coupon_user_live'`.

Arreglo sugerido (**no aplicado**): en `2026_10_08_1000_00-083_coupon_campaign_rules.py`, `upgrade()` (línea 33; ver también `app/db/migrations/env.py:74` `AUTOCOMMIT`), reemplazar `op.drop_index(...)` por `op.execute('DROP INDEX IF EXISTS world_cup.uq_coupon_redemptions_coupon_user_live')` y moverlo al principio de la función. Opcionalmente, envolver la migración en una transacción explícita.

## 5. Limitaciones explícitas

1. **PGlite ≠ PostgreSQL 16 servidor.** Es PG 18.3 en WASM de 32 bits, de un solo proceso. Hay diferencias de versión: por ejemplo, PG 18 registra los `NOT NULL` como constraints en `pg_constraint`, cosa que PG 16 no hace. La semántica de DDL e índices únicos usada aquí es estándar, pero el resultado se debe repetir en PG 16 antes del deploy.
2. **Una sola sesión de backend.** Todas las conexiones al socket comparten sesión, así que **no se probó concurrencia**, `SELECT ... FOR UPDATE` ni carreras de canje. `test_coupon_concurrency.py` corre con sus propios dobles, no con PGlite.
3. Datos sintéticos y pequeños (decenas de filas): no miden tiempos de bloqueo ni la duración del `CREATE UNIQUE INDEX` con volumen real.
4. El backup/restore es lógico y propio (JSON + migraciones para el esquema). No ejercita `pg_dump`/`pg_restore` ni los objetos que no crean las migraciones (roles, grants, extensiones).
5. El `env.py` de laboratorio replica el online de producción pero no es el mismo archivo. Se probaron las migraciones, no el arranque de `app/db/migrations/env.py` con psycopg2.
6. Las bases son `memory://` y se pierden al detener el servidor. Los artefactos (snapshots JSON, logs, backup) quedaron en el scratchpad de la sesión, no en el repo.

## E2E vinculación de identidad (C2)

Se probó de punta a punta la vinculación Telegram con la cuenta Brasper usando **los dos servicios reales**: la API `com_brasper_api` (`app.main:app` con uvicorn) y el bot `com_brasper_ia` (`engine.handle_message` → LangGraph → `identity_link` / `operation_status` → `brasper_api` por httpx). La base es PGlite migrado a `head` (084). Todo corre en 127.0.0.1 con datos sintéticos: ninguna BD remota, ningún `.env` leído ni impreso y ninguna llamada a `apibras.finzeler.com`.

### Archivos

| Archivo | Rol |
|---------|-----|
| `com_brasper_api/scripts/e2e_identity_link_pglite.py` | Arnés de la API. Monta la app real sobre PGlite con `pool_size=1, max_overflow=0`, asyncpg `ssl=False`, `statement_cache_size=0`. Siembra clientes y operaciones, y una cuenta de servicio con hash real. Expone rutas de control `/__e2e/*`. |
| `com_brasper_api/scripts/e2e_identity_link_driver.py` | Driver. Arranca PGlite, migra, arranca el arnés, ejecuta el test del bot con su venv y apaga todo. |
| `com_brasper_ia/backend/tests/identity_e2e.py` | Test del bot (venv del bot). No forma parte de `run_checks` porque necesita la API levantada. |

### Comandos

```
# desde com_brasper_api
.venv/Scripts/python.exe scripts/e2e_identity_link_driver.py --pglite <scratchpad>/pglite --logs <scratchpad>/e2e_identity --auth-required 1
.venv/Scripts/python.exe scripts/e2e_identity_link_driver.py --pglite <scratchpad>/pglite --logs <scratchpad>/e2e_identity --auth-required 0
```

El driver genera, en cada corrida, un secreto de integración y una contraseña de la cuenta de servicio aleatorios y sintéticos con `secrets.token_urlsafe`. Los pasa a los dos procesos por variables de entorno (`E2E_SHARED_SECRET`, `E2E_SERVICE_USERNAME=svcbrasperiae2e`, `E2E_SERVICE_PASSWORD`) y no los imprime. El bot recibe además:

- `BRASPER_IA_SERVICE_USERNAME` / `BRASPER_IA_SERVICE_PASSWORD` con esos valores. Siempre se fijan, para que el `.env` local no los aporte.
- Una `BRASPER_IA_GRANT_KEY` Fernet generada en el momento.
- Un `tenants.json` temporal que apunta `quote.api.base_url` a `http://127.0.0.1:8010` y activa `identity_link` y `operation_status`.

### Datos sintéticos

- Dueño `0e2e…0001`: cliente activo `+51 900000001` con `E2E-OWN-001` (verification), `E2E-OWN-002` (completed) y `E2E-OWN-DEL` (failed, `deleted=true`).
- Otro cliente `0e2e…0002`: `+55 11900000002` con `E2E-OTH-001` (failed) y `E2E-OTH-002` (verified).
- Cuenta de servicio `0e2e…00a1`:
  - `user.auth_login` con el hash Argon2 generado por el código real del API, `SecurityUtils.hash_password`.
  - `user.user` con rol `user`, sin teléfono, así que no es un cliente.
  - El bot entra por el **`POST /auth/login` real**: sesión en `user.auth_session`, evento en `audit.login_event` y JWT validado por `_verify_jwt`.
- Mínimo de FKs: un banco, una cuenta destino por cliente, un `tax_rate` y una `commission` PEN→BRL.

### Resultados

| Modo | Resultado | Duración |
|------|-----------|----------|
| `AUTH_REQUIRED=1` (obligatorio fuera de desarrollo) | **46/46 PASS** | ~29 s |
| `AUTH_REQUIRED=0` (ENVIRONMENT=development) | **42/42 PASS** | ~25 s |

En el modo 0 no corren S4–S7 (servicio rechazado), porque sin `AUTH_REQUIRED` el middleware no valida el Bearer.

| # | Aserción | auth=1 | auth=0 |
|---|----------|--------|--------|
| 00 | Flags activas y `base_url` local | PASS | PASS |
| 01 / 01b | Sin vínculo: «¿ya llegó mi envío?» deriva a asesor sin estados y ofrece el enlace del portal con la referencia en el fragmento `#` | PASS | PASS |
| 02 / 02b / 02c | El portal emite un token de 43 caracteres; rechaza `tg:-100` (422) y no emite sin sesión (401) | PASS | PASS |
| 03 – 03e | `/start <token>` responde «vinculado». El token queda redactado en los mensajes, el grant se guarda cifrado y atado al dueño, sin texto en claro en SQLite ni en `lead_data`, y la API marca el vínculo como consumido | PASS | PASS |
| 04 / 04b / 04c | Estado oficial del dueño (`E2E-OWN-001: en verificación`, `E2E-OWN-002: completada`). No aparecen `E2E-OTH-*` ni la operación eliminada. `usage=None` | PASS | PASS |
| S1 | Un solo login de servicio hasta ese punto: el token queda cacheado | PASS | PASS |
| S2 / S3 | Sesión de servicio revocada a mitad de corrida (`/__e2e/service/revoke-sessions` → `auth_session.revoked_at`). La consulta siguiente sigue funcionando. Con auth=1 hay **exactamente 1 re-login** (`logins_ok` 1→2, una sesión activa); con auth=0 hay 0 re-logins, porque el middleware ignora el Bearer inválido | PASS | PASS |
| S4 | Servicio rechazado (usuario de servicio con `enable=false`: el JWT deja de validar y el reintento también recibe 401 con `WWW-Authenticate`). La consulta deriva sin estados y **el grant no se olvida** | PASS | — |
| S5 | Servicio rechazado: `/start` responde «No pude verificar», **no** «no es válido» | PASS | — |
| S6 | Servicio rechazado: el token no se consumió en la API | PASS | — |
| S7 | Servicio rehabilitado: la consulta vuelve a funcionar | PASS | — |
| 05 – 05d | Token reutilizado. El bot responde «no es válido» desde otro chat. En la API (llamada directa con secreto + Bearer de servicio), la ruta responde 401 sin `WWW-Authenticate` para: otro chat, un segundo canje en el chat original y canje sin secreto | PASS | PASS |
| 06 – 06d | La API devuelve 200 con su chat. La ruta responde 401 con el grant desde otro chat y contra el otro `user_id`. En el bot, una fila de grant copiada a otra conversación se descarta y deriva | PASS | PASS |
| 07 | Token vencido (`expires_at` al pasado en BD): «no es válido» y sin grant | PASS | PASS |
| 08 – 08c | Grant vencido en la API: llega un 401 de la ruta, el bot olvida el grant y deriva | PASS | PASS |
| 08d / 08e | Grant vencido localmente (SQLite): se borra y deriva | PASS | PASS |
| 09 – 09e | `DELETE /brasper/identity-links` revoca. La consulta deriva y el bot olvida el grant. Revocar al otro cliente devuelve `revoked: 0` | PASS | PASS |
| 10 – 10e | API detenida: deriva sin excepción y conserva el grant. Un `/start` con la API caída responde «No pude verificar» | PASS | PASS |
| 11 | El guardia de sockets no registró ninguna conexión fuera de loopback | PASS | PASS |

Contadores de servicio en el modo auth=1 (`audit.login_event` y `user.auth_session`):

| Momento | Logins correctos | Sesiones activas |
|---------|------------------|------------------|
| Tras S3 | 2 | 1 |
| Con el servicio deshabilitado | 4 | 3 |
| Final | 4 | 3 |

Con el servicio deshabilitado, cada petición que falla hace un único re-login (la consulta en S4 y el `/start` en S5), nunca un bucle. Al rehabilitarlo, el bot reutiliza el último token cacheado sin hacer un nuevo login. Ningún login falló.

**Resultado de la corrección del bot (`core/brasper_api.py`, login de servicio + Bearer):** el hallazgo anterior queda resuelto. Antes, con `AUTH_REQUIRED=1`, el middleware cortaba todas las llamadas a `/brasper/ai/*` (28/39). Ahora la vinculación y la consulta de estados funcionan igual que en desarrollo. La renovación tras revocar el token es de un único reintento, y una falla de la sesión de servicio ya no se confunde con «código inválido» ni revoca grants.

### Observaciones encontradas al probar (no corregidas)

1. **API — login de usuario deshabilitado.** `app/modules/auth/application/use_cases/auth_use_cases.py:49-58`: `LoginUseCase` no comprueba `user.enable` ni `user.deleted` antes de emitir el token y la sesión. Un usuario deshabilitado sigue haciendo login con éxito y deja sesiones activas que no sirven, porque `_verify_jwt` las rechaza. En S4/S5 quedaron 2 sesiones huérfanas. Arreglo sugerido: rechazar el login cuando `not user.enable or user.deleted`.
2. **API — detalle interno en 401.** `app/modules/auth/adapters/router/auth_routes.py:416-421`: cualquier `ValueError` del login, incluido un `ValidationError` de Pydantic al construir `UserInfoDTO`, se devuelve como 401 con `str(e)`. Se observó con un correo de dominio reservado (`@example.invalid`): la contraseña era correcta, pero el login falló y la respuesta mostró el error de validación. Un usuario real con un correo que `email-validator` rechace tampoco podría entrar.
3. **API — formato del usuario de servicio.** `Credentials` exige un usuario alfanumérico o un correo: `svc-brasper-ia` (con guiones) falla en `get_by_username`. Hay que tenerlo en cuenta al crear la cuenta de servicio de producción.
4. **Bot — sin caché negativa.** `core/brasper_api.py:154-177` (`_service_token`): si el login de servicio falla, no se cachea el fallo. Cada llamada de integración vuelve a intentar el login, lo que cuesta Argon2 en la API, hasta que las credenciales se corrigen. No es un bucle por petición, pero conviene un backoff corto.

### Qué se simuló o desactivó en el arnés

- **Sesión del portal del cliente (simulada).** `TokenAuthMiddleware._authenticate_token` acepta además `Bearer e2e-portal.<uuid>` como «el cliente X inició sesión». Equivale a sobrescribir `get_current_user`. Cualquier otro token sigue la ruta real. **La cuenta de servicio del bot no se simula**: usa el login real y el JWT real.
- **`lifespan` real reemplazado.** El original verifica Cloudflare R2 (red externa) y abre el listener LISTEN/NOTIFY de transacciones (una segunda conexión que PGlite no admite). El nuevo solo siembra datos.
- **Sin `.env`.** El arnés hace `chdir` a una carpeta temporal antes de importar la app y fija la configuración con valores sintéticos. `app.db.base.engine` y `AsyncSessionLocal` se reemplazan por el engine de PGlite. La auditoría real sigue activa: mutaciones fallidas y `login_event`.
- **Rutas `/__e2e/*`.** Solo existen en el arnés y van protegidas con `X-E2E-Control`. Sirven para mover vencimientos de tokens y grants, revocar sesiones o deshabilitar la cuenta de servicio, consultar contadores de login y sesión, listar vínculos sin hashes y apagar el servidor. El bot no puede abrir una segunda conexión a PGlite.

### Limitaciones

1. **PGlite, sesión única.** Una sola conexión: no se prueban concurrencia, carreras de canje, el `SELECT … FOR UPDATE` de la emisión ni logins de servicio simultáneos desde varios workers. Es PG 18 WASM, no PostgreSQL 16 servidor.
2. **Portal simulado.** No se ejercitan el login del cliente, la UI «Vincular chat» ni el deep-link real.
3. **Sin Telegram real.** No hay webhook ni Bot API: se llama a `engine.handle_message("tg:<id>", …, channel="telegram")` directamente. Redis está apagado (lock local), el LLM es un stub que falla si se invoca y la BD del bot es SQLite temporal.
4. **Vencimiento del JWT por tiempo.** No se esperó a que el JWT de servicio venza por TTL (15 min): se forzó con la revocación de la sesión, que produce el mismo 401 del middleware.
5. La caída de la API se probó deteniendo uvicorn (conexión rechazada), no con timeouts lentos ni respuestas 5xx.
6. Logs y `results_auth{0,1}.json` quedaron en el scratchpad de la sesión, no en el repo.

### Re-ejecución tras correcciones (9 oct, tarde)

Cambios aplicados después de los hallazgos del E2E:

- API `auth_use_cases.py`: `LoginUseCase` ya no emite sesión para cuentas deshabilitadas o eliminadas. `auth_routes.py`: el 401 de login solo devuelve mensajes propios, nunca errores internos de validación. Pruebas en `tests/test_login_account_state.py`; suite API 391 passed.
- Bot `core/brasper_api.py`: backoff de 30 s tras un login de servicio fallido (`SERVICE_LOGIN_BACKOFF_SECONDS`), check 74 ampliado; `run_checks` 74/74.
- `identity_e2e.py`: S6b comprueba el backoff; S7 simula que venció antes de rehabilitar.

Resultado: `--auth-required 1` → **47/47 PASS** (con la cuenta deshabilitada: 1 login fallido y ninguna sesión nueva); `--auth-required 0` → **42/42 PASS**.

Pendiente menor: la API normaliza `X-Client-App` a `backoffice`/`www`, así que las sesiones del bot se atribuyen a `backoffice` en auditoría.
