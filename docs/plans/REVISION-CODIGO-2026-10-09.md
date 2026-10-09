# Revisión del estado actual del plan de código

Fecha: 9 de octubre de 2026, Lima. Revisión de árboles locales y pruebas aisladas. No se modificó implementación, producción ni Meta. Los `.env` de producción no se usaron para ejecutar servicios.

## Conclusión

Hay avances sustanciales posteriores a la revisión de 105 tests, pero el encabezado «código local cerrado» del plan no cumple todavía su propia definición de terminado. C1/C5/C8 conservan validaciones pendientes y se encontraron dos defectos reproducibles no cubiertos por las suites aprobadas.

## Cambios presentes en código

- C1: campañas versionadas, descuento sobre comisión, selección compartida de comisiones, bloqueo/registro de usos, restricciones de edición y eliminación. Auditoría financiera y migraciones 083/084 con runners PGlite.
- C2: API de emisión/canje/revocación, cuenta de servicio JWT + secreto, recepción redactada de códigos, grants cifrados y consulta privada. Portal `com_brasper_www/src/modules/chatlink` implementa inicio, emisión y revocación. La evidencia E2E existente usa portal simulado: no acredita el login y deep-link completos desde la UI.
- C3/C4: idioma ES/PT persistente, onboarding, encuestas, consentimiento y jobs persistentes; recuperación de jobs inciertos.
- C5: contactos/alias/conflictos, conexión de origen, estados de salidas, eventos persistidos/replay e interfaces Coex, revisión de intervención humana.
- C6/C7: biblioteca aprobada/versionada, límites de medios, permisos por canal/conexión/sector, vista `/accesos`, documentos y conflictos de edición.
- C8: runbook e inventario ampliados, migraciones 0009–0011, infraestructura aislada preparada y evidencia PGlite. No certifica funcionamiento de Redis ni psycopg en PostgreSQL 16.

## Hallazgos que deben corregirse

### R1 — No continuar si no se pudo obtener ningún bloqueo

`backend/core/redis_runtime.py`, función `_db_lock`, captura cualquier excepción de la base y devuelve `"local-no-redis"`. `backend/core/engine.py` solo rechaza un token falso: acepta ese texto y ejecuta la conversación. Reproducción aislada: Redis desactivado y `db_lock.acquire` simulado con excepción → token verdadero. Puede haber procesamiento concurrente si falla el respaldo; que un fallo posterior de BD impida alguna escritura no constituye exclusión.

Cerrar: devolver indisponibilidad sin ejecutar el grafo cuando no existe lock, y probarlo. Revisar además exclusión durante recuperación parcial de Redis: un worker con lock Redis y otro con lock BD no comparten el mismo bloqueo. El lease de 45 segundos del engine no se renueva; comprobar procesamiento que exceda ese tiempo y la autorización de salida después de perder el lease. Estos últimos riesgos se identificaron por inspección y necesitan pruebas concurrentes.

### R2 — Ocultar todos los códigos del mensaje

`backend/core/identity_link.py`, `extract_token`, oculta solamente la primera coincidencia. Reproducción con dos códigos sintéticos de 43 caracteres → el segundo permanece en el texto. `agent_graph.py` guarda ese texto como mensaje del usuario. Por tanto un segundo código puede quedar en historial y ser accesible desde el panel; no se afirma que en ese mismo recorrido llegue al LLM.

Cerrar: redactar todas las coincidencias antes de persistir, decidir de forma explícita qué responder ante varios códigos y probar historial, observabilidad y contexto posterior. Nunca incluir códigos reales en tests o informes.

## Pruebas ejecutadas de nuevo en esta revisión

| Verificación | Resultado | Alcance |
|---|---|---|
| Bot `tests/run_checks.py` | 74/74 | SQLite temporal y proveedores simulados; dotenv deshabilitado |
| Bot `tests/evals/run.py` | 57/57 | Determinista, sin modelo real |
| Doctests `core/policies.py` | Aprobado | Reglas puras |
| API `python -m pytest tests -q` | 391 aprobadas | PostgreSQL apuntado a loopback/puerto no operativo; pruebas con mocks |
| Panel `tsc --noEmit` | Aprobado | Tipos; no equivale a interacción de pantallas |
| R1/R2 | Reproducidos | Pruebas sintéticas sin servicios ni datos reales |

No se repitieron build, PGlite, migraciones, E2E completo ni revisión visual en esta revisión. Los resultados anteriores están documentados en sus evidencias y no se presentan como ejecuciones nuevas.

## Lista concreta que falta para cerrar el código

1. Corregir R1/R2 y agregar regresiones relevantes.
2. Probar PostgreSQL 16 real con múltiples sesiones y el driver psycopg del bot; Redis real, caídas/recuperación, lease, concurrencia financiera, emisión/canje simultáneos y rollback. PGlite de sesión única no sustituye estas pruebas.
3. Completar validación UI del portal autenticado → vinculación → consulta privada, incluidos otros clientes, vencimiento, revocación, errores y regreso al chat. Probar panel con distintos roles, conflictos, guardados y medios; medir Lighthouse de las pantallas pertinentes.
4. Ensayar migración con datos históricos representativos: ids repetidos entre tenants, índice de campaña, backup/restauración y compatibilidad de rollback/flags. No hacerlo en producción durante esta tarea.
5. Resolver o documentar con regla aprobada las brechas C1: operaciones sin cupón editadas/reactivadas/reasignadas, consistencia entre descuento cotizado y registrado y redondeo/precisión. `quote_id` firmado es una propuesta, no una obligación comercial aprobada ni una función ya implementada.
6. Después de las correcciones repetir las verificaciones afectadas, build del panel/portal y actualizar plan, auditoría y runbook con evidencia persistente.

Coex/BSUID reales, textos legales aprobados, recursos/cuentas, publicación y piloto permanecen en el plan externo. Un adaptador local o una suite aprobada no acredita esos requisitos.

## Respuesta — correcciones aplicadas (9 oct, tarde)

- **R1:** `core/redis_runtime.acquire_lock` toma SIEMPRE el lock de `conversation_locks` en la base (exclusión común entre workers que ven Redis caído y sano); Redis, si responde, se suma. Si la base falla devuelve `None` y `engine` rechaza con `ConversationBusyError` sin ejecutar el grafo. `still_held` comprueba el lease al terminar: si venció o lo tomó otro proceso, la respuesta no se entrega (`conversation.lock_lost`). Regresión: check 75 (base caída, Redis mixto, lease vencido).
- **R2:** `identity_link.extract_token` redacta todas las coincidencias y además cualquier secuencia aislada con forma de código; con varios códigos distintos no canjea ninguno y pide enviar solo uno. Regresión: check 70 (historial sin ninguno de los dos códigos, sin canje).
- Repetido tras corregir: `run_checks` 75/75, evals 57/57, E2E API↔bot sobre PGlite 47/47 (`AUTH_REQUIRED=1`) y 42/42 (`0`), API 391 passed.

Siguen abiertos los puntos 2–5 de la lista anterior (PostgreSQL 16 multisesión con psycopg, Redis real, UI del portal de punta a punta, ensayo con datos representativos, reglas comerciales C1). La renovación del lease no se implementó: se eligió no entregar la respuesta si se pierde, que es seguro pero puede dejar una respuesta sin enviar en procesamientos de más de 45 s.


## Segunda revisión independiente — 9 de octubre de 2026

R1 básico y R2 confirmados corregidos con reproducciones sintéticas: fallo de adquisición en BD devuelve None; dos códigos quedan redactados y no se canjea ninguno. Suite completa del bot repetida con dotenv deshabilitado: 75/75 aprobados. No se repitieron API, evals, UI, build o infraestructura; sus resultados anteriores no son ejecuciones nuevas.

Pendiente de código C5: el lease del engine es de 45 segundos, sin renovación, y still_held se comprueba al terminar el grafo. Esa comprobación bloquea la entrega, pero no cancela trabajo ni impide escrituras anteriores. El cliente LLM admite timeout de 60 segundos. Debe probarse procesamiento superior a 45 segundos con dos workers y resolver la exclusión durante toda la operación mediante renovación/propiedad o un mecanismo equivalente. El solapamiento real no se reprodujo en esta revisión: es un riesgo identificado por inspección, no una concurrencia aprobada.

Siguen pendientes PostgreSQL 16 multisesión, psycopg/Redis reales, migraciones/backup con históricos representativos, UI del portal autenticado de punta a punta, validación del panel por roles/Lighthouse y brechas financieras C1. No declarar C1–C8 completamente cerrados con esa evidencia pendiente. Meta/Coex reales permanecen en el plan externo. No se modificó producción ni implementación en esta revisión.

## Respuesta a la segunda revisión — lease renovado (9 oct)

- `core/lease.py`: el lease de la conversación se renueva cada TTL/3 en un **hilo propio** (un nodo síncrono que bloquee el event loop no lo retrasa). La renovación (`redis_runtime.renew_lock` → `db_lock.renew`) solo extiende un lease que sigue siendo nuestro y no venció; Redis se renueva además con un script que compara dueño.
- `core/engine.py`: el procesamiento corre como tarea bajo el lease. Si la renovación falla, la tarea se **cancela** en su siguiente punto de espera (no sigue escribiendo ni genera respuesta) y se devuelve `ConversationBusyError`; al terminar se vuelve a comprobar la propiedad antes de entregar.
- Regresión (check 75): dos workers con procesamiento de 1,6 s y TTL de 0,6 s, tanto con espera asíncrona como con un nodo que bloquea el event loop: los procesamientos no se solapan y A responde. Renovación imposible: el trabajo se cancela antes de terminar y no responde. Control negativo: sin renovación la misma prueba falla.
- Repetido: `run_checks` 75/75, evals 57/57, doctests OK, E2E API↔bot 47/47 y 42/42.

Límite que permanece: una escritura síncrona ya en curso cuando se pierde el lease no se interrumpe (Python no cancela código bloqueante); solo puede ocurrir si la base no responde durante más de un TTL. La prueba con dos procesos reales y PostgreSQL 16 multisesión sigue pendiente junto con el resto de la infraestructura real.

