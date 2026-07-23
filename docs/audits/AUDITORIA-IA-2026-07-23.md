# Auditoría IA Brasper — 2026-07-23

## Resumen ejecutivo

- **CRITICAL corregido:** la migración `0007_remove_multitenant` eliminó
  `tenant_id` en producción, mientras el runtime intentaba insertarlo. Esto
  provocaba HTTP 500 al crear conversaciones y al responder desde el panel.
- **CRITICAL corregido:** cotización, clientes, cuentas de depósito y audio de
  Telegram llamaban adaptadores sin el argumento `tenant`; esos caminos
  terminaban en `TypeError`.
- **HIGH corregido:** el webhook registrado apuntaba a
  `/telegram/webhook/brasper`, pero el backend solo exponía la ruta sin tenant.
  Se preservó compatibilidad y el webhook productivo quedó sin pendientes ni
  último error.
- **HIGH corregido:** se eliminó del tenant productivo el conector demo de
  `httpbin`; las cotizaciones continúan usando exclusivamente la API Brasper.
- **HIGH pendiente:** `backend/tests/run_checks.py` todavía representa la
  arquitectura multi-tenant anterior. El gate reporta fallos de contrato y no
  puede considerarse una barrera de merge confiable hasta migrarlo o revertir
  formalmente la decisión single-tenant.

## Hallazgos

### CRITICAL

1. **Runtime y esquema de producción incompatibles**
   - `backend/migrations/versions/0007_remove_multitenant.py`
   - `backend/core/db.py`
   - Evidencia: PostgreSQL devolvía `UndefinedColumn: tenant_id` en
     `conversations`.
   - Corrección: detección explícita del esquema para soportar temporalmente
     bases históricas y la base single-tenant desplegada.

2. **Adaptadores fintech invocados con firmas incorrectas**
   - `backend/core/quotes.py`
   - `backend/core/lead_onboarding.py`
   - `backend/core/telegram.py`
   - Afectaba tasas, comisiones, cupones, reconocimiento de clientes, cuentas
     de depósito y transcripción de audio.
   - Corrección: restaurar el paso obligatorio de la configuración Brasper.

3. **Respuesta humana desde el panel devolvía HTTP 500**
   - `backend/api/routes.py`
   - `backend/core/db.py`
   - El mensaje del asesor no podía persistirse en el esquema productivo.
   - Corrección validada contra PostgreSQL real: `/reply` devuelve HTTP 200.

### HIGH

1. **Conversión single-tenant incompleta**
   - `backend/core/tenants.py`
   - `backend/core/auth.py`
   - `backend/worker.py`
   - `backend/manage.py`
   - Persistían llamadas a funciones eliminadas o con argumentos obsoletos.
   - Se corrigieron los usos del runtime. Falta decidir y documentar si Cauce
     continuará single-tenant o recuperará el contrato multi-tenant.

2. **Excepciones de Telegram ocultas**
   - `backend/api/routes.py`
   - Un `asyncio.create_task()` sin frontera de errores permitía responder 200
     al webhook mientras el procesamiento fallaba silenciosamente.
   - Se añadió captura, log con traceback y evento
     `telegram.update_failed`.

3. **Gate de producción no representa el runtime actual**
   - `backend/tests/run_checks.py`
   - Mantiene firmas e invariantes del stack multi-tenant eliminado.
   - Debe migrarse antes de usarlo como requisito de deploy.

4. **No hay workflow CI activo**
   - No existen workflows en `.github/workflows` ni `.gitea/workflows`.
   - Un cambio roto pudo llegar directamente a `main`.

### MEDIUM

1. **Archivos centrales demasiado grandes**
   - `backend/api/routes.py`: aproximadamente 900 líneas.
   - `backend/core/db.py`: aproximadamente 900 líneas.
   - Recomendación: separar rutas por canal/administración/conversaciones y
     encapsular la compatibilidad de esquema en un repositorio dedicado.

2. **Migración 0007 es destructiva y sin downgrade**
   - Elimina tablas y columnas multi-tenant con `CASCADE`.
   - No debe repetirse en otros entornos sin backup probado.

3. **Scripts únicos de refactor permanecen dentro del runtime**
   - `backend/refactor.py`, `backend/fix_engine.py`,
     `backend/core/update_db.py`.
   - Deben archivarse o eliminarse después de confirmar que no forman parte del
     procedimiento operativo.

### LOW

1. El build web pasa, pero Next.js advierte que existen varios lockfiles y que
   infiere un workspace root externo.
2. La documentación aún mezcla descripciones multi-tenant con el runtime
   single-tenant.

## Validaciones realizadas

- Webhook Telegram real: URL corregida, cero updates pendientes y sin último
  error.
- `/health` productivo: PostgreSQL y Redis operativos.
- Motor local con SQLite histórico: responde a `hola`.
- Motor local conectado al PostgreSQL productivo: responde a `hola`.
- `/api/conversations/{id}/reply` contra PostgreSQL real: HTTP 200.
- Cotización real Brasper `PEN → BRL`: tasa, comisión y cupón obtenidos por API;
  respuesta con disclaimer y vigencia.
- Smoke HTTP local: chat, listado, detalle, reply, status, advisors, tenants,
  usage y export sin HTTP 500.
- `python -m compileall`: correcto.
- `npm run build`: correcto.

## Plan

### Fase 0 — Unificar

- Declarar formalmente single-tenant o revertir `0007`.
- No mantener simultáneamente dos contratos de funciones.
- Extraer un repositorio de persistencia con un único esquema soportado.

### Fase 1 — Fintech hard

- Mantener cotizaciones, comisiones y cupones exclusivamente vía API Brasper.
- Añadir evals de caída de API, par inexistente y monto alto.

### Fase 2 — RAG

- Mantener FAQ/documentos separados por tenant si se recupera Cauce
  multi-tenant.

### Fase 3 — CI y evals

- Migrar `run_checks.py` al contrato decidido.
- Ejecutar compile, suite backend, evals anti-alucinación y build web en cada PR.

### Fase 4 — Smoke y operaciones

- Smoke post-deploy obligatorio de chat, Telegram, reply humano y cotización.
- Alertar por `telegram.update_failed` y cualquier 5xx del chat.

## Definition of Done para launch

- Producción responde HTTP 200 a chat, Telegram y reply humano.
- Cotización real coincide con la API Brasper y nunca usa tasas locales si la
  API está activa.
- Gate backend y build web completamente verdes.
- CI bloquea merge ante fallos.
- Backup y restore probados antes de nuevas migraciones destructivas.
- Cero secretos versionados y rotación registrada.
- Runbook refleja el esquema y la estrategia de tenancy realmente desplegados.
