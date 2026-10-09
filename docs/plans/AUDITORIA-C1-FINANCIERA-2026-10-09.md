# Auditoría C1 — Integridad financiera de promociones (2026-10-09)

Repositorio auditado: `com_brasper_api` (FastAPI + SQLAlchemy async). Alcance: cotización, registro, edición y borrado de operaciones y cupones/campañas, y su efecto sobre el registro de usos (`coupons.used_count` + `world_cup.coupon_redemptions`) y sobre el beneficio de primer envío.

Reglas de negocio aplicadas (confirmadas, sin reglas nuevas):

- El descuento es de 0 a 100 % y se aplica **solo sobre la comisión**. Nunca toca el capital ni el tipo de cambio.
- Primer envío y uso de cupón: una operación COMPLETADA lo **consume**, una PENDIENTE lo **reserva** y una FALLIDA lo **libera exactamente una vez**. Cotizar nunca reserva. Un historial desconocido nunca otorga el beneficio. Una operación completada que luego se borra (borrado lógico) sigue contando como consumo.
- Pasar de completada a fallida no libera el beneficio ni borra la evidencia. La reversa financiera queda como TODO comercial.

## 1. Tabla de rutas y casos de uso

| Ruta / caso de uso | Efecto sobre reserva y consumo | Estado |
|---|---|---|
| `POST /brasper/ai/quotes` → `campaign_quote.quote_for_client` / `calculate` | Solo cotiza (`reserved: false`). Ahora también devuelve `discount_state: "quoted"`. Lee el historial (completadas, incluidas las borradas lógicamente; pendientes no borradas) y los usos de cada cliente | OK + campo nuevo |
| Cotización inversa (`mode=receive`) → `inverse_quote` | Resuelve cada tramo lineal (comisión × cupón × tope × mínimo/máximo) con la misma función `calculate`. Si el monto pedido cae en un salto de tramo, lo rechaza y deriva a un asesor | OK (fuzz de 300 casos sin divergencia; test nuevo) |
| `POST /transactions` → `CreateTransactionUseCase._apply_server_financials` | Bloquea al cliente y luego el cupón (`FOR UPDATE`), valida vigencia, par, cupo y límite por usuario, aplica `discount_for` (la misma función que la cotización), suma 1 a `used_count` y crea `CouponRedemption` (reserva) | **Bug corregido**: el tramo de comisión divergía de la cotización |
| `POST /transactions` sin sesión o sin repo de comisiones (camino legacy/tests) | Antes se guardaba `coupon_id` **sin reserva** | **Bug corregido**: ahora se rechaza |
| `POST /transactions/import` → `ImportTransactionsUseCase` | Reutiliza `CreateTransactionUseCase` con sesión: mismo libro de usos | OK |
| `PUT /transactions` → `UpdateTransactionUseCase` | `validate_coupon_edit` bloquea cambios de cupón, cliente, montos, tasa o comisión en operaciones con cupón, y cualquier cambio de estado o de cliente en una completada. Fallida + cupón → `release_coupon_usage` (idempotente). Fallida → no fallida con cupón: rechazado | **Brecha corregida**: no bloqueaba al cliente (ver bug 3) |
| `PUT /transactions/accounting/billing-date` | Solo cambia `billing_date` (la ruta rechaza otros campos) y pasa por el mismo `UpdateTransactionUseCase` | OK |
| `DELETE /transactions/{id}` → `DeleteTransactionUseCase` | Pendiente con cupón: libera y hace borrado lógico. Completada: conserva consumo e historial. Fallida: la liberación ya hecha no se repite | **Brecha corregida**: no bloqueaba al cliente (ver bug 3) |
| `POST /transactions/coupons` → `CreateCouponUseCase` | Rechaza `CAMPAIGN` y `campaign_rules` (deben ir por el editor versionado). Porcentaje validado entre 0 y 100 | OK |
| `PUT /transactions/coupons` → `UpdateCouponUseCase` | Bloquea `CAMPAIGN`, aplica versión optimista y valida el porcentaje | **Bug corregido**: permitía bajar `max_uses` por debajo de `used_count` |
| `DELETE /transactions/coupons/{id}` → `DeleteCouponUseCase` | Borrado lógico. Las operaciones pendientes conservan `coupon_id` y pueden liberarlo después (el lock no filtra `deleted`) | **Bug corregido**: borraba campañas versionadas, saltándose el editor |
| `GET /transactions/coupons/automatic` | Excluye campañas y cupones con `per_user_limit` (necesitan identidad). Solo lectura | OK |
| `POST/PUT /brasper/ai/admin/campaigns…` → `CampaignService.save/publish/disable` | Guardar un borrador no cambia la versión publicada. Publicar exige `max_uses >= used_count` y una fecha de fin futura. Exige el secreto `BRASPER_IA_ADMIN_SECRET`, distinto de `BRASPER_IA_SHARED_SECRET` (si son iguales: 503) | OK |
| WebSocket `transactions_websocket.py` | Solo autentica, responde ping/pong y difunde eventos (`pg_notify`). No modifica operaciones | OK (no muta) |
| Selección de comisión: `coin/domain/commission_selection.select_commission` | Política única de tramos (se mantiene) | OK |

## 2. Bugs corregidos

1. **Divergencia entre cotización y registro en el tramo de comisión.** Archivo: `app/modules/transactions/application/use_cases/transaction_use_cases.py:768`.
   - Antes, el registro aceptaba el `commission_id` del cliente si el monto caía dentro de su rango.
   - En tramos solapados (por ejemplo, 1000 en `[0,1000]` y en `[1000,5000]`) o con un tramo deshabilitado, el cliente podía registrar una comisión distinta de la cotizada.
   - Ahora el tramo se elige **siempre** con `select_commission` sobre los tramos habilitados del par, con `enable=True`, igual que la cotización.
2. **Cupón guardado sin registro de usos.** Archivo: `transaction_use_cases.py:752`. Si faltaban la sesión o el repo de comisiones, `coupon_id` se persistía sin `used_count` ni `CouponRedemption`. Ahora se lanza `ValueError`.
3. **Edición y borrado sin exclusión por cliente.** Archivo: `transaction_use_cases.py:993` (`lock_transaction_owners`), usado en `:1077` (edición) y `:1263` (borrado).
   - Antes, la edición y el borrado bloqueaban solo la operación y el cupón, así que una liberación o reactivación podía competir con un registro de primer envío del mismo cliente.
   - Orden de bloqueo único:
     - Registro: cliente → cupón.
     - Edición y borrado: cliente(s) → operación → cupón.
   - En una reasignación se bloquean ambos clientes en orden determinista por id.
   - Si el dueño cambió entre la lectura y el bloqueo, la operación se rechaza con "cambió de cliente…" (`:1085`, `:1268`).
4. **Cupo editable por debajo de lo usado.** Archivo: `app/modules/transactions/application/use_cases/coupon_use_cases.py:114`. Se aplica la misma regla que al publicar una campaña.
5. **Borrado genérico de campañas.** Archivos: `coupon_use_cases.py:151` y `adapters/router/coupon_routes.py:110` (responde HTTP 409). Las campañas se desactivan desde el editor, no se borran por la ruta genérica.
6. **Estado del descuento explícito en las respuestas:**
   - Cotización: `discount_state: "quoted"` (`app/modules/brasper/application/campaign_quote.py:69`).
   - Operación: campo calculado `coupon_discount_state`, con valores `reserved`, `consumed` o `released` (`application/schemas/transaction_schema.py:905`, implementado en `application/campaign_policy.py:31`).
   - El id y la versión de la campaña ya se propagaban: `coupon_id` y `campaign_version` en la cotización; `coupon_id` y `coupon_campaign_version` en el registro y en `TransactionReadDTO`. Un test nuevo verifica que coinciden.

No se encontró doble liberación: `release_coupon_usage` solo descuenta filas de `CouponRedemption` vivas, y una operación completada lanza error antes de tocar el cupón.

## 3. Tests

- Nuevo archivo `tests/test_c1_financial_integrity.py` con 16 tests:
  - Paridad entre cotización y registro en 5 montos, incluido el borde solapado 1000.
  - Un tramo deshabilitado enviado por el cliente se reemplaza.
  - Cotización inversa → registro idéntico, con salto de tramo derivado a asesor.
  - Un cupón sin libro de usos se rechaza.
  - Orden de bloqueo `User → Coupon` en el registro y reserva de primer envío entre campañas.
  - Fallida → libera una sola vez, aunque después haya otra edición y un borrado. Orden `User → Transaction → Coupon`.
  - Una completada conserva el consumo al editarla o borrarla.
  - Una reasignación bloquea a ambos clientes en orden estable.
  - Se detecta una reasignación concurrente.
  - El cupo no puede quedar por debajo de los usos.
  - No se borra una campaña por la ruta genérica.
  - `discount_state`.
- Ajustes de fixtures, porque el registro ahora siempre lista los tramos:
  - `tests/test_coupon_concurrency.py`: `commission_repo.list`.
  - `tests/test_transactions.py`: `commission_repo.list` en 3 tests y `session.scalar` en el test de etiquetas. No cambió ninguna aserción.

## 4. Comandos y resultados (en `com_brasper_api`)

```
.venv/Scripts/python.exe -m pytest -q tests/test_campaigns.py tests/test_commission_selection.py tests/test_coupon_percentage.py tests/test_coupon_concurrency.py tests/test_transactions.py tests/test_brasper_ai_routes.py tests/test_brasper_ai_identity.py tests/test_identity_links.py
  línea base: 105 passed
.venv/Scripts/python.exe -m pytest -q <mismo set> tests/test_c1_financial_integrity.py
  después: 121 passed
.venv/Scripts/python.exe -m pytest -q tests
  387 passed, 1 failed (preexistente, ajeno a C1; ver abajo)
```

Fallo preexistente: `tests/test_phase4_mutation_audit.py::test_all_openapi_mutations_match_audited_inventory_and_routes_have_audit_dependency`.

- Faltan en `app/modules/audit/infrastructure/audited_routes_inventory.py` las rutas nuevas sin commitear: `/brasper/ai/quotes`, `/brasper/ai/admin/campaigns*`, `/brasper/ai/identity-links/redeem` y `/brasper/identity-links`.
- No lo provoca este cambio. Se resuelve agregando esas rutas al inventario, decisión que queda para quien es dueño de esas rutas.

## 5. Limitaciones y brechas abiertas

- **Sin prueba real de concurrencia en PostgreSQL.** En esta máquina no hay PostgreSQL.
  - Los tests verifican el orden y la forma (`FOR UPDATE`) de los bloqueos con sesiones falsas, más la lógica con `asyncio.Lock` del test de concurrencia ya existente.
  - No queda demostrado:
    - la exclusión efectiva entre transacciones;
    - la ausencia de deadlocks bajo carga;
    - el rollback real.
  - Pendiente: un drill con PostgreSQL (p. ej. dos sesiones reales y `pg_locks`).
- **TODO comercial — reversa financiera completada → fallida/cancelada.** Hoy está bloqueada por completo, sin liberar ni borrar evidencia. Si se necesita, debe definirse como un flujo explícito aparte.
- **Reactivar una fallida sin cupón, o reasignar a otro cliente una pendiente sin cupón.**
  - Ambos casos están permitidos. Si el cliente destino ya tiene una operación pendiente con beneficio de primer envío, terminaría con dos operaciones.
  - Ahora la carrera está serializada por el bloqueo de cliente, pero falta una regla comercial: rechazar o recalcular.
- **Edición de montos en operaciones sin cupón.** El servidor no recalcula las cifras (comisión, total, destino) al editar operaciones sin cupón: las fija el asesor. Es comportamiento previo. Se recomienda recalcular de forma atómica o exigir autorización.
- **Aplicación automática.**
  - La cotización elige la mejor campaña (prioridad, ahorro, id; exclusiva).
  - El registro aplica solo el `coupon_id` que se le envía.
  - Si el asesor no envía el cupón cotizado, el cliente no recibe el descuento. No existe un endpoint de registro desde el bot.
  - Propuesta: un `quote_id` firmado o persistido.
- **Redondeo.** La cotización redondea el monto a céntimos y el registro usa `origin_amount` tal cual. Con montos de más de 2 decimales puede haber una diferencia de ±0,01.
- **Precisión de la cotización inversa.** Puede devolver un monto a recibir distinto del objetivo hasta `max(0,02; 2 %·tasa)`. En un salto de tramo, deriva al asesor.
- **Zona horaria de la campaña.** `campaign_rules.timezone` se valida, pero la vigencia se evalúa con las fechas `start_date`/`end_date`, que ya tienen zona horaria. No es un error, pero el campo es solo informativo.
- **Cupones heredados.** Operaciones heredadas con cupón y sin fila `CouponRedemption` nunca descuentan `used_count` al fallar. Es conservador: no hay doble liberación.
- **Secretos.**
  - Variables involucradas, solo por nombre: `BRASPER_IA_SHARED_SECRET` (bot), `BRASPER_IA_ADMIN_SECRET` (administración de campañas, debe ser distinto) y `BRASPER_IA_IDENTITY_LINK_ENABLED` (por defecto `False`).
  - Esta tarea no agrega flags nuevos.
- **Migraciones.** No se editaron migraciones ni `scripts/pglite_alembic/*`.
