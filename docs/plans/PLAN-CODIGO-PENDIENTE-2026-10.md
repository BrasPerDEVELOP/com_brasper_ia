# Plan ejecutable de código pendiente — Brasper IA

Actualizado: 9 de octubre de 2026 (Lima). Responsable: una persona o agente de desarrollo. Estado: implementación local completa en C1–C8; R1/R2 y el lease sin renovación de las revisiones corregidos. Siguen pendientes validaciones de infraestructura real (PostgreSQL 16 multisesión, psycopg, Redis) y la prueba de UI del portal de punta a punta. No desplegado.

Revisión vigente: [REVISION-CODIGO-2026-10-09.md](REVISION-CODIGO-2026-10-09.md). Se reprodujeron fallos de exclusión al caer el respaldo de locks y redacción incompleta ante varios códigos de vinculación. Pruebas nuevas: 74 checks, 57 evals, 391 tests API y TypeScript aprobados. El registro de cierre posterior es histórico y no certifica resueltos estos hallazgos ni la infraestructura real pendiente. Actualización 9 oct (tarde): R1 y R2 corregidos con regresiones (checks 70 y 75: 75/75); evals 57/57; E2E API↔bot 47/47 y 42/42. Ver la respuesta en la revisión.

Este documento es la lista de ejecución actual para terminar el trabajo que no necesita cuentas, aprobaciones ni tráfico de terceros. Sustituye como lista de pendientes de código a las tablas históricas del [plan original](PLAN-ATENCION-AUTONOMA-2026-10.md), conservando su alcance. Las dependencias externas están en [otro plan](PLAN-DEPENDENCIAS-EXTERNAS-2026-10.md). Prompt de entrega: [PROMPT-AGENTE-CODIGO-2026-10.md](PROMPT-AGENTE-CODIGO-2026-10.md).

## Alcance y límites

- Trabajar en `C:\Users\USER\Documents\GitHub\com_brasper_ia` y `C:\Users\USER\Documents\GitHub\com_brasper_api`. Revisar sus instrucciones antes de editar. Los cambios actuales están sin commit: inspeccionarlos y preservarlos; no reiniciar ni reconstruir lo ya implementado.
- Completar backend, panel, contratos internos, migraciones, pruebas y documentación. PostgreSQL y Redis locales son parte del trabajo de código, no una dependencia de cuentas externas. Si falta el runtime, preparar un entorno reproducible y registrar por separado cualquier prueba que no se pudo ejecutar.
- No acceder a producción para escribir, desplegar, modificar Umbler/Meta, activar campañas reales, enviar mensajes a clientes ni ejecutar operaciones financieras reales. Usar bases aisladas, datos sintéticos y adaptadores de envío simulados.
- No convertir el producto en menús numerados ni construir un editor visual de flujos. La IA conversa libremente; estados y herramientas internas controlan permisos y operaciones.
- Pago verificado y operación ejecutada por humanos o sistema autorizado. Un comprobante recibido, un chat cerrado o una frase del modelo nunca acredita pago ni completa una transferencia.
- Tasas, cuentas, comisiones y cupones proceden de la autoridad Brasper. El modelo no inventa valores, no altera reglas y no sustituye datos financieros vencidos cuando falla la API.

## Punto de partida: conservar y terminar

Ya existe implementación local de perfiles de agentes versionados y limitados por canal/conexión; historial privado del cliente; cotización oficial de campañas; administración de promociones; biblioteca de imágenes aprobadas; defensas de identidad, timeout e idempotencia. También hay bases anteriores de FAQ, audios, presencia, cola, documentos públicos y routing de conexiones.

Última evidencia registrada: 69/69 checks del bot, 105/105 pruebas seleccionadas de la API y TypeScript correcto. Los 54 escenarios deterministas, doctests y build pasaron en lotes anteriores: deben repetirse tras los cambios finales. Migración SQLite 0006 → 0009 con conservación de datos, repetición y backup/restore aprobada. No equivale a una prueba de LLM real, PostgreSQL/Redis, Coex ni producción. Las migraciones financieras 083 y de identidad 084 están pendientes de validación PostgreSQL. La auditoría conserva la evidencia histórica.

No empezar otra implementación paralela de promociones, perfiles o biblioteca: revisar y completar la existente.

## Orden de trabajo y aceptación

### Lista vigente para ejecutar, sin rehacer lo existente

Todas las filas siguen abiertas hasta reunir su evidencia. Las secciones C1–C8 posteriores detallan el alcance y sus criterios; algunas tareas ya tienen implementación parcial.

| Orden | Pendiente de código | Entrega necesaria para cerrarlo |
|---|---|---|
| 1 — C2 | Conectar los códigos de vinculación de la API con la cuenta autenticada del cliente y el bot. Agregar la vista de emisión al portal correspondiente, recepción segura sin enviar códigos al LLM, almacenamiento privado del grant, vencimiento y consulta de operaciones. Mantener derivación si no hay prueba fiable. | Prueba entre ambos servicios: propietario correcto, otro cliente bloqueado, código usado/vencido, grant vencido y timeout sin repetir escrituras. |
| 2 — C1 | Terminar auditoría de todas las rutas de creación/edición/eliminación y probar reserva/consumo/liberación concurrentes; validar migraciones 083/084 y recuperación con datos anteriores. Conservar la selección de comisiones ya unificada. | PostgreSQL real aislado: dos operaciones simultáneas no consumen dos primeros beneficios; backup/restore financiero verificado. |
| 3 — C5 | Crear contactos internos y alias por proveedor/conexión, con teléfono opcional; migrar históricos sin fusiones inseguras. Cerrar duplicación al crear conversaciones concurrentes y manejo de caída de Redis. | Mismo cliente en dos conexiones, identificador opaco sin teléfono, conflicto de alias y eventos simultáneos sin cruces ni duplicados. |
| 4 — C5 | Completar persistencia/replay de sincronización, historial y ecos; revisar pausa humana en texto, audio, medios y worker. Distinguir mensaje enviado, cancelado e incierto. | Simulación local de Coex y API estándar, reinicio, eventos repetidos/fuera de orden y humano durante generación/envío. La compatibilidad real se certifica en el plan externo. |
| 5 — C3/C4 | Cerrar recorridos ES/PT y correcciones; revisar consentimiento explícito, recuperación de jobs reclamados tras caída y retorno al chat durante encuesta. | Recorridos completos con idioma conservado, petición humana prioritaria y recordatorios cancelados o bloqueados correctamente. |
| 6 — C6/C7 | Completar permisos backend por rol/canal/sector y comprobar biblioteca, audios, adjuntos, documentos, asignación y versiones en las pantallas locales. | Un usuario no ve comprobantes ni conversaciones fuera de su permiso; publicación/edición concurrente y errores de medios con comportamiento comprobado. |
| 7 — C8 | Ejecutar infraestructura aislada, integración, checks, evals, doctests, TypeScript/build y revisión autenticada de pantallas. Actualizar runbook, flags e inventario de funciones. | Comandos reproducibles, resultados y limitaciones por requisito. Nada pendiente se marca aprobado por contar tests. |

Para PostgreSQL/Redis existe `docker-compose.validation.yml` y [guía de validación](VALIDACION-INFRA-LOCAL.md). Falta un runtime de pruebas disponible: este equipo no tiene Docker/WSL y Windows bloqueó los binarios PostgreSQL descargados. Es un pendiente de infraestructura de desarrollo, no de Facebook; no usar producción como sustituto.

### C1. Integridad financiera, promociones y migraciones — prioridad máxima

Archivos principales: API `campaign_service.py`, `campaign_quote.py`, `campaign_policy.py`, `transaction_use_cases.py`, modelos/esquemas de transacciones y migración 083; IA `quotes.py`, `brasper_api.py`, `lead_onboarding.py`, `api/campaigns.py` y `/promociones`.

- Auditar la misma regla en cotización y registro: 0–100% sobre comisión; límites de monto, par, cupos, vigencia, zona horaria, topes, prioridad y exclusividad. Ningún descuento afecta capital ni tipo de cambio. Corregir divergencias de rangos de comisión y cotización inversa.
- Regla confirmada: completadas consumen el beneficio de primer envío; pendientes lo reservan; fallidas/canceladas lo liberan exactamente una vez. Cotizar no reserva. Historial desconocido no autoriza beneficio. Una operación completada eliminada lógicamente conserva su historial.
- Revisar transiciones completada → fallida/cancelada: impedir que una edición libere un beneficio ya consumido o borre la evidencia de primer envío. Si se requiere una reversión financiera especial, dejarla separada y pendiente de regla comercial, sin inventarla.
- Impedir que editar cliente, cupón, monto, moneda o estado de una operación eluda el registro de uso; rechazar cambios incompatibles o recalcularlos atómicamente con autorización. Cubrir también rutas genéricas de cupones y transacciones.
- Comprobar exclusión concurrente por cliente y por cupón, incluso entre campañas distintas y distintos canales; definir orden consistente de bloqueos y rollback. Probar con transacciones reales de PostgreSQL, no solo locks simulados.
- Propagar identificador y versión de campaña aplicada a respuestas autorizadas y ficha de operación. Distinguir descuento cotizado, reservado y consumido en los textos.
- Revisar migración 083 sobre datos anteriores, índices y compatibilidad. El downgrade que recupera una restricción antigua puede fallar con varios usos históricos: documentar y probar una reversión segura mediante backup/restore, sin eliminar registros para forzarla.
- Documentar el secreto administrativo separado del secreto del bot mediante nombres de variables; nunca valores reales. Flags nuevos desactivados por defecto.

Aceptación: sin descuentos inválidos, dobles reservas ni liberación doble; pruebas de pendientes, completadas, fallidas, cancelación, eliminación lógica, modificación y concurrencia entre campañas. Migración ensayada y estrategia de recuperación comprobada localmente.

### C2. Identidad y consulta privada del estado de envíos

Archivos principales: API `ai_routes.py`, `ai_schemas.py`, `ai_service.py`; IA `lead_onboarding.py`, contratos de herramientas, `agent_graph.py` y almacenamiento de identidades.

- Completar el endpoint de estado y su integración con `status.lookup` ya existentes; terminar el recorrido con identidad vinculada para canales sin teléfono verificado. Devolver solamente estados oficiales y datos mínimos, comprobando pertenencia de la operación al cliente autorizado.
- No aceptar nombre, número escrito, documento declarado o conocimiento del identificador de operación como prueba suficiente. El secreto de integración tampoco demuestra por sí solo la identidad del cliente.
- Conservar la vinculación fiable del canal cuando exista. Para Telegram/webchat/identificadores sin teléfono, construir un mecanismo local de vinculación verificable (sesión autenticada o código de un solo uso, con vencimiento, límites, no reutilización y sin enumeración de clientes). El transporte real de códigos, si se necesita, queda en el plan externo; su adaptador y pruebas son locales.
- Mantener derivación humana y conversación útil cuando no se pueda verificar la identidad; no anunciar que una tarea privada se completó.
- Resolver reconciliación de escrituras que terminaron por timeout: consultar resultado persistido sin repetir un alta incierta ni aceptar una coincidencia parcial como éxito.

Aceptación: un cliente no ve operaciones de otro; pruebas de credenciales insuficientes, códigos vencidos/reutilizados, proveedor caído y timeout posterior a escritura. La consulta privada funciona de extremo a extremo entre ambos servicios locales.

### C3. Conversación y onboarding coherentes ES/PT

- Completar traducciones de onboarding, validaciones, cuentas de depósito, errores, cola, derivación, promociones y cierre. Conservar idioma ante mensajes neutros como nombre, documento o monto; permitir cambio explícito.
- Recuperar datos ya dados, corregir monto/destino, cambiar de intención y retomar sesión sin empezar de nuevo. Petición de humano siempre interrumpe la recopilación.
- Validar documentos según tipo sin destruir identificadores alfanuméricos ni confundir documento registrado con verificado. Evitar etapas sin prompt, nombres vacíos y datos de cliente desactualizados durante el avance.
- Verificar agrupación de ráfagas, contexto y límites de repetición. Responder FAQ solo desde versiones aprobadas con fuente/fecha; estilos de agente no amplían herramientas ni acceso a conocimiento.

Aceptación: recorridos completos ES/PT, entradas neutras, correcciones, reinicio del proceso y petición de asesor; sin frases financieras no respaldadas ni promesas de tiempos no configurados.

### C4. Encuesta, reclamos, espera e inactividad

- Implementar encuesta opcional ES/PT después del cierre de atención, una vez por cierre elegible, con puntuación y comentario; permitir omitirla y retomar el chat.
- Registrar reclamos y ofrecer/realizar derivación según petición y reglas aprobadas, con resumen. Separar cierre conversacional de estado financiero.
- Crear configuración de horario, zona horaria, espera, SLA, máximo de recordatorios y consentimiento; no inventar valores comerciales activos. Borradores o funciones desactivadas hasta configuración.
- Implementar trabajos persistentes con deduplicación, vencimiento, cancelación por respuesta/takeover/cierre y recuperación después de reinicio. No emitir mensajes tardíos ni repetidos.
- Diseñar una política de salida que compruebe capacidad del canal, consentimiento, ventana y plantilla autorizada. Si se desconoce alguna condición, bloquear la salida proactiva; no hardcodear reglas Meta no confirmadas. Probar con contratos simulados explícitamente etiquetados.
- Exponer métricas de satisfacción, espera y derivación sin tratar un envío como resolución del problema.

Aceptación: pruebas de horario/DST, duplicados, reinicio, respuesta simultánea, takeover y ausencia de consentimiento/capacidad. Ningún mensaje real durante las pruebas.

### C5. Núcleo multicanal e intervención humana, preparado para Coex

- Separar contacto interno, identidad del proveedor, conexión, teléfono opcional y nombre visible. No deducir un teléfono extrayendo dígitos de un identificador opaco ni vincular por username.
- Implementar migración local de identidades históricas, vínculos trazables y conflictos sin fusionar automáticamente cuentas. Mantener Telegram y clientes previos.
- Aplicar conexión de origen a todas las salidas: texto, imágenes, audio, plantillas, respuesta del asesor, jobs y proxy de medios. Probar aislamiento entre varios números.
- Usar una revisión o mecanismo equivalente por conversación para invalidar respuestas pendientes al intervenir un humano. Volver a comprobar autorización justo antes del envío; contemplar trabajo que ya está en ejecución y reinicios.
- Distinguir y deduplicar ecos propios frente a actividad humana; estados de entrega no generan respuestas. Preparar almacenamiento/replay de eventos e interfaces de sincronización para historial y estado.
- El mapeo exacto de payloads Meta nuevos y la sincronización real quedan sujetos al contrato confirmado en el plan externo. No inventar campos ni llamar «Coex probado» a un simulador. Mantener el adaptador incompleto desactivado, con pruebas de la interfaz interna.

Aceptación: matriz local estándar/Coex simulado/Telegram/webchat; mismo evento repetido, dos conexiones, humano durante generación y antes de envío, caída/reanudación, ecos propios y eventos fuera de orden. Sin respuestas cruzadas ni respuestas iniciadas después de la pausa. Documentar el límite inevitable de un envío ya aceptado por el proveedor.

### C6. Imágenes, audios y adjuntos en todos los recorridos

- Completar la biblioteca existente: permisos, borrador/publicado, versiones, idioma, propósito, vista previa de la versión elegida, retiro, deduplicación y fallo sin perder el texto.
- Verificar envío de imágenes de campañas también en audio, worker, Telegram y atención web. Revisar que los comprobantes privados no entren en la biblioteca comercial.
- Autorizar el acceso a cada medio por conversación/canal/rol; no exponer un comprobante ajeno por conocer una referencia. No permitir que una imagen de cuentas sustituya datos financieros vigentes de la API.
- Aplicar límites de tamaño, tipo y procesamiento en todas las entradas; cubrir archivos corruptos, tipo falso, contenido excesivo y fallos de descarga/transcripción.
- Conservar evidencia del audio y confirmar cifras ambiguas; texto transcrito y documentos recibidos son datos, nunca instrucciones privilegiadas.

Aceptación: material no aprobado o retirado no se envía; un fallo conserva texto y evidencia; no hay duplicados, filtraciones ni confirmación automática de pago.

### C7. Panel, permisos, documentos públicos y operación

- Revisar UI real local de `/agentes`, `/promociones`, `/biblioteca`, conversaciones y documentos públicos, incluyendo estados vacíos, errores, guardado, publicación, restauración y cambios sin guardar. Para imágenes/versiones, mostrar exactamente lo que se publica.
- Verificar permisos del backend por rol, canal y sector; presencia con vencimiento, asignación concurrente y cola. El frontend oculto no es autorización.
- Corregir carreras de versión en documentos públicos; borradores privados, contenido sanitizado, vista pública sin login y solicitudes de eliminación rastreables sin borrado automático. Usar contenido de prueba claramente identificado, no texto legal inventado como aprobado.
- Mantener secret references y permisos de configuración; registrar auditoría sin datos sensibles. Medir errores, tareas verificadas, tiempos y costes por flujo.
- Documentar flags, configuración, migraciones, soporte de fallos y rollback. Incorporar métricas y páginas nuevas al inventario de funcionalidades.

Aceptación: revisión de pantallas autenticadas con roles diferentes; conflictos de edición explícitos; páginas públicas sin fuga de borradores y sin redirección indebida; ninguna asignación doble o fuera de permisos.

### C8. Validación integrada y cierre del trabajo de código

- Bot: desde `com_brasper_ia/backend`, ejecutar `..\.venv\Scripts\python.exe tests/run_checks.py`, doctests de `core/policies.py` y `tests/evals/run.py`. Ampliar escenarios ante cambios relevantes, incluidos Telegram y ES/PT.
- API: ejecutar las pruebas financieras/identidad/campañas existentes y las de las rutas modificadas; ampliar cobertura de transiciones, estado privado y concurrencia real.
- Panel: TypeScript y build, pruebas de comportamiento relevantes y revisión visual local autenticada. Lighthouse debe medir las pantallas pertinentes, no solo login/shell.
- Ejecutar integración de ambos servicios con PostgreSQL/Redis aislados, migraciones sobre datos previos y worker. Ensayar backup, restauración y reversión de flags/código compatibles con esquema.
- Ejecutar escenarios deterministas sin red. Preparar, pero no declarar ejecutadas, evaluaciones con modelo real o proveedor que requieran cuenta, coste o credenciales externas.
- Actualizar auditoría y esta lista por requisito con evidencia: archivos, comando, resultado y limitaciones. No basta contar tests ni afirmar «no rompe producción» porque compila.

## Definición de terminado

El trabajo local se cierra cuando C1–C8 tienen implementación y evidencia aplicable; no quedan tareas de código renombradas como «externas» para cerrar el plan. Cada contrato de tercero aún no confirmado conserva una interfaz, pruebas locales y una limitación explícita en el plan externo. Si no se pudo ejecutar una prueba local de infraestructura, se informa como pendiente local, no como aprobada.

La entrega debe incluir resumen de cambios, pruebas ejecutadas, fallos o límites, instrucciones reproducibles y pendientes externos concretos. No publicar, desplegar, activar ni afirmar compatibilidad real con Meta. El plan completo del producto solo se cierra después del plan externo y el piloto autorizado.

## Avance verificado — 9 de octubre de 2026

Este registro sustituye los conteos históricos anteriores; no declara cerrado C1–C8.

- API: 105 pruebas seleccionadas aprobadas (campañas, comisiones, cupones, transacciones, identidad y contratos privados). La selección de comisión ahora es compartida por cotización y registro; los huecos internos sin comisión se rechazan.
- Bot: última ejecución registrada 69/69 checks; 54/54 escenarios deterministas y doctests anteriores al último lote. TypeScript aprobado; falta repetir build y evaluar las últimas pantallas.
- SQLite: migración con datos sintéticos históricos 0006 → 0009, repetición y copia/restauración aprobadas. No acredita las migraciones financieras 083/084 de PostgreSQL.
- Vinculación segura: API local emite códigos de un uso de cinco minutos desde la sesión del cliente; grants de treinta minutos vinculados a cliente/canal/referencia, guardados como hashes. Consulta privada de operaciones exige grant válido e integración. Flag BRASPER_IA_IDENTITY_LINK_ENABLED desactivado por defecto. Falta portal para emitir, integración del bot, almacenamiento privado del grant y pruebas de concurrencia real: C2 sigue parcial.
- Documentos: se evita guardar una respuesta antigua sobre otra selección; hay control de cambios sin guardar. Medios limitados a 20 MiB durante descarga, origen WhatsApp validado y caché privada descartada al cerrar sesión.
- PostgreSQL/Redis: runner aislado preparado en docker-compose.validation.yml. No ejecutado; equipo sin Docker/WSL y Windows bloquea los binarios descargados. No se modificó esa protección.

Pendientes locales principales: identidad de extremo a extremo; contactos y alias canónicos; sincronización Coex/reconciliación; permisos por canal/sector; carreras de entrega y caída de Redis; validación PostgreSQL/Redis, migraciones financieras, build y comprobación de pantallas. Los requisitos externos permanecen en el plan separado. Producción no fue modificada durante este avance.

## Cierre de código — 9 de octubre de 2026 (tarde)

Trabajo hecho en `com_brasper_ia`, `com_brasper_api` y `com_brasper_www` (portal de clientes, necesario para emitir la vinculación). Sin commits, sin despliegue, sin tocar producción ni Meta. Todos los datos de prueba son sintéticos.

| Fila | Estado | Evidencia |
|---|---|---|
| 1 — C2 identidad | Hecho | Bot: `core/identity_link.py` (token por `/start`/`vincular`, redactado antes de guardar y del LLM; grant Fernet en `identity_grants`; canje idempotente sin repetir escrituras tras timeout), `operation_status` con grant, flag `identity_link`. API: revocación `DELETE /brasper/identity-links`, rutas en el inventario de auditoría, `grant` redactado. Portal: `/vincular-chat` → `/dashboard/vincular-chat`. Cuenta de servicio del bot (JWT + secreto) para `AUTH_REQUIRED=true`. Checks 70 y 74; E2E real API↔bot sobre PGlite 47/47 con `AUTH_REQUIRED=true` y 42/42 sin ella (login deshabilitado y fuga de errores en `/auth/login` corregidos en la API): ver [evidencia](EVIDENCIA-PGLITE-2026-10-09.md#e2e-vinculación-de-identidad-c2). |
| 2 — C1 financiero | Hecho salvo concurrencia real | [Auditoría C1](AUDITORIA-C1-FINANCIERA-2026-10-09.md): 5 bugs corregidos (comisión distinta entre cotización y registro, cupón sin reserva, ediciones sin lock del cliente, `max_uses` < usados, borrado de campaña versionada). Migración 083 corregida (DROP INDEX sin `IF EXISTS` dejaba la base a medio migrar). 083/084 con datos, repetición, downgrade y backup/restore en PGlite: [evidencia](EVIDENCIA-PGLITE-2026-10-09.md). |
| 3 — C5 contactos | Hecho | `core/contacts.py` (alias por proveedor/conexión, teléfono solo si el canal lo entrega, conflictos sin fusión, backfill idempotente), lock de creación de conversación, lock en base si Redis cae (`core/db_lock.py`). Check 71. |
| 4 — C5 sincronización | Hecho con interfaz; mapeo Meta externo | `core/outbound.py` (enviado/cancelado/incierto/fallido; estados que solo avanzan), `core/channel_events.py` (history/state_sync guardados para replay; ecos en vuelo diferidos y resueltos por id; barrido tras caída), `core/coex.py`. Check 72. |
| 5 — C3/C4 | Hecho | Jobs reclamados y caídos → incierto (nunca se reenvían); pregunta durante la encuesta vuelve al chat; consentimiento con puntuación; «¿ya llegó mi envío PxB-77?» ya no se cotiza. Checks 67, 65; evals 57/57. |
| 6 — C6/C7 permisos | Hecho | `core/access.py`: alcance por canal/número/sector en bandeja, detalle, adjuntos, respuestas, asignación y derivación automática; comprobantes con `media:private`; un asesor ya no reasigna conversaciones ajenas. Panel `/accesos` y avisos de envíos sin confirmar en la ficha. Check 73; revisión visual local autenticada. |
| 7 — C8 validación | Parcial: falta infraestructura real | Ver comandos abajo. Migraciones del bot 0001→0011 en PGlite ([evidencia](EVIDENCIA-PGLITE-BOT-2026-10-09.md)); 0009 ahora renumera versiones duplicadas de documentos y 0011 corrige `tenant_id NOT NULL` que rompía citas y rotación de secretos. |

Comandos y resultados (Windows, 9 oct):

- Bot, desde `backend/`: `..\.venv\Scripts\python.exe tests\run_checks.py` → 75/75; `tests\evals\run.py` → 57/57; `python -m doctest core/policies.py` → OK; `tests\sqlite_migration_checks.py` → 0006→0011 con datos, repetición y backup/restore.
- API: `.venv\Scripts\python.exe -m pytest -q tests` → 391 passed.
- Panel: `npx tsc --noEmit` y `npx next build` → OK. Portal: `vue-tsc --noEmit` y `vite build` → OK.
- PostgreSQL: PGlite (PostgreSQL 18.3 en WASM) vía asyncpg con los runners `com_brasper_api/scripts/validate_migrations_pglite.py` y `backend/tests/pglite_migrations.py`.

Límites que siguen abiertos (infraestructura local, no cuentas externas):

- PGlite es una sola sesión: no prueba bloqueos entre transacciones simultáneas (reservas de cupón, advisory lock, `FOR UPDATE`). Ensayo pendiente en PostgreSQL 16 real con Docker o servidor autorizado, usando `docker-compose.validation.yml`.
- El driver del bot en runtime (psycopg) y Redis real no se pudieron ejecutar en este equipo (App Control).
- Antes de migrar producción: comprobar ids de conversación repetidos entre tenants (riesgo de 0007) y el índice de 083 con las consultas de las evidencias.
- Reglas comerciales pendientes señaladas por la auditoría C1 (reversión completada→fallida, `quote_id` firmado, redondeo).

Los requisitos de Meta (contrato Coex/BSUID real), FAQ comercial, textos legales y piloto siguen en el [plan externo](PLAN-DEPENDENCIAS-EXTERNAS-2026-10.md).


## Segunda revisión independiente — 9 de octubre de 2026

R1 básico y R2 confirmados corregidos con reproducciones sintéticas: fallo de adquisición en BD devuelve None; dos códigos quedan redactados y no se canjea ninguno. Suite completa del bot repetida con dotenv deshabilitado: 75/75 aprobados. No se repitieron API, evals, UI, build o infraestructura; sus resultados anteriores no son ejecuciones nuevas.

Pendiente de código C5: el lease del engine es de 45 segundos, sin renovación, y still_held se comprueba al terminar el grafo. Esa comprobación bloquea la entrega, pero no cancela trabajo ni impide escrituras anteriores. El cliente LLM admite timeout de 60 segundos. Debe probarse procesamiento superior a 45 segundos con dos workers y resolver la exclusión durante toda la operación mediante renovación/propiedad o un mecanismo equivalente. El solapamiento real no se reprodujo en esta revisión: es un riesgo identificado por inspección, no una concurrencia aprobada.

Siguen pendientes PostgreSQL 16 multisesión, psycopg/Redis reales, migraciones/backup con históricos representativos, UI del portal autenticado de punta a punta, validación del panel por roles/Lighthouse y brechas financieras C1. No declarar C1–C8 completamente cerrados con esa evidencia pendiente. Meta/Coex reales permanecen en el plan externo. No se modificó producción ni implementación en esta revisión.
