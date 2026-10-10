# Revisión directa de implementación — 10 de octubre de 2026

Fuente: código y pruebas, sin usar declaraciones de cierre de los planes. No se modificó implementación ni producción.

## Evidencia nueva

- Bot: `tests/run_checks.py` repetido con dotenv deshabilitado y SQLite temporal: 75/75.
- API: suite `tests` repetida con base apuntada a loopback/puerto 1: 391 aprobadas.
- Renovación implementada: `core/lease.py` mantiene un hilo de renovación; engine ejecuta `_process` como tarea y solicita cancelación al perder el lease. Los checks cubren renovación con trabajo lento/bloqueante y fallo durante un `asyncio.sleep`.

## Pendientes de código comprobados

### 1. Monto normalizado antes de elegir comisión

`campaign_quote.calculate` redondea el monto antes de `select_commission`; `CreateTransactionUseCase` usa `float(cmd.origin_amount)` sin normalizarlo antes de seleccionar. El esquema acepta float sin precisión máxima de dos decimales.

Reproducción sin base ni red: tramos [0,1000] al 2% y [1000,2000] al 1%, entrada 1000.004. Cotización elige 2% (monto 1000.00); el selector que usa registro elige 1%. Este es un cambio de tramo, no solo una diferencia de un céntimo. Aplicar una política compartida de precisión/validación antes de seleccionar, calcular y persistir, con regresión en bordes e inversa. La reproducción usa las funciones reales de cotización/selección, no una transacción financiera real.

### 2. Cancelación no garantiza detener nodos síncronos ni hilos de herramientas

El callback de pérdida de lease programa `task.cancel` en el event loop. Un nodo síncrono que lo bloquea continúa hasta devolver o esperar; una herramienta ejecutada en `ThreadPoolExecutor` tampoco se cancela por cancelar la tarea async. `tool_contracts.run` conserva intencionalmente el hilo tras timeout para recuperar el resultado tardío.

Reproducción aislada del motor: TTL .15s, renovación devuelve False, `_process` simulado bloquea .35s y realiza un efecto sintético después. Ese efecto ocurre pese a la pérdida del lease. No se escribió en ninguna base ni se envió un mensaje. El check actual de fallo solo usa espera async: no demuestra el caso bloqueante.

Cerrar con comprobaciones de propietario/revisión en los puntos de escritura y política de escrituras inciertas; no cancelar ciegamente una operación externa que ya pudo ser aceptada. Agregar regresión de pérdida durante nodo síncrono/hilo y recuperación con dos workers. No se requiere volver a implementar la renovación, que ya existe.

## Validación todavía necesaria

- PostgreSQL 16 multisesión, psycopg y Redis reales: locks, transacciones, canjes/reservas concurrentes, caída y recuperación. `infra_checks.py` contiene algunos casos, pero no un ensayo financiero completo entre ambas aplicaciones.
- Recorrido de UI autenticada del portal → emisión → chat → consulta, más regresión del panel por roles y errores. Tipos/build y llamadas directas al engine no sustituyen ese recorrido.
- Migraciones con históricos representativos, recuperación y escenarios financieros de edición sin cupón/consistencia cotización-registro.
- Meta/Coex reales quedan fuera de esta revisión de código.

No se declara una auditoría exhaustiva de todas las líneas. Los resultados aprobados no descartan los dos casos reproducidos fuera de las suites actuales.

## Respuesta — correcciones aplicadas (10 oct)

### 1. Monto normalizado antes de elegir comisión — corregido

- API `app/modules/coin/domain/commission_selection.py`: `normalize_amount` (2 decimales, `Decimal` con redondeo comercial) es la única política de precisión. La usan `campaign_quote.calculate`, la cotización inversa y `CreateTransactionUseCase._apply_server_financials`, que además persiste el monto normalizado como `origin_amount`.
- Regresión `tests/test_c1_financial_integrity.py`: tramos [0,1000] al 2 % y [1000,2000] al 1 % con 1000.004, 1000.005, 999.995 y 1000.0049999; cotización y registro eligen el mismo tramo y comisión, y el monto persistido es el normalizado. Suite API: 396 passed.
- Hallazgo adicional, **no cambiado**: con cuentas destino, el registro valida y guarda el `destination_amount` enviado por el cliente aunque difiera del recalculado por el servidor. Una prueba existente (`test_create_under_100_keeps_calculator_destination_after_server_recalculation`) indica que es una regla operativa intencional (se conserva el total confirmado en la calculadora). Queda como decisión comercial C1, no como corrección de código.

### 2. Escrituras tras perder el lease — corregido

- `core/lease.py`: el lease activo viaja en una `ContextVar` heredada por la tarea del motor y por los hilos de `tool_contracts.run` (`copy_context`). `guard()` lanza `LeaseLost` (hereda de `BaseException`, ningún `except Exception` la absorbe) si el lease se perdió.
- Puntos de escritura con guard: `db.add_message`, `merge_lead_data`, `set_conversation_status`, `assign_conversation`, `claim_conversation`, `engagement.schedule`, `outbound.deliver` y el inicio de toda herramienta con escritura. Una escritura externa ya iniciada no se cancela a ciegas: su resultado tardío se registra (idempotencia/incierto).
- Regresión (check 75): TTL 0,15 s, renovación fallida y nodo síncrono que bloquea 0,35 s y luego escribe → la escritura no ocurre y el mensaje se rechaza; herramienta en hilo que escribe tras la pérdida → no escribe y no se inicia una segunda escritura; otro worker procesa después con normalidad. Control negativo: sin `guard` la prueba falla.
- Repetido: `run_checks` 75/75, evals 57/57, doctests OK, E2E API↔bot 47/47 y 42/42.

Límite que permanece: código síncrono que escriba sin pasar por esos puntos (SQL directo fuera de `db`) no queda protegido; una escritura externa ya aceptada por un proveedor tampoco puede deshacerse. Las validaciones de infraestructura real, UI de punta a punta y migraciones con históricos siguen pendientes.

