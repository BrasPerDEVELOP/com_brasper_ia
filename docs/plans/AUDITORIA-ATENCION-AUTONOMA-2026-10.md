# Auditoría de finalización de atención autónoma

## Estado actualizado de la entrega — 2026-10-08

El usuario solicitó separar desarrollo local de cuentas y dependencias externas. Listas vigentes: [código C1–C8](PLAN-CODIGO-PENDIENTE-2026-10.md), [dependencias externas E1–E5](PLAN-DEPENDENCIAS-EXTERNAS-2026-10.md) y [prompt de entrega](PROMPT-AGENTE-CODIGO-2026-10.md). Esta actualización es documental: no modifica código ni producción.

Después del registro de identidad de abajo se implementaron localmente el catálogo versionado de campañas en la API, cotización individual oficial, vista `/promociones`, biblioteca con aprobación/versiones y vista `/biblioteca`, y entrega de imágenes con deduplicación. La API tiene preparada la migración 083 de campañas. Las reglas de edición/cancelación de operaciones y la concurrencia real requieren el cierre C1; no se certifica todavía el ciclo financiero completo.

Última evidencia registrada: 64/64 checks del bot (log local corroborado), 35/35 pruebas seleccionadas de API y TypeScript/build del panel correctos. Los 54/54 evals y doctests son de un lote anterior y deben repetirse tras los cambios finales. No se ejecutó la migración 083 ni se acreditó PostgreSQL/Redis real, integración Meta o piloto. Las tablas de partida siguientes son historial; sus menciones a catálogo/biblioteca pendientes o conteos menores no describen el último lote.

El estado de envíos en la API propia, ES/PT completo, encuestas/espera, identidad interna, carreras de takeover, permisos, medios y validación local siguen siendo trabajo de código. No se trasladan a «terceros» por conveniencia. Los contratos Meta no confirmados, elegibilidad/cuentas, números reales y aprobaciones/publicación se verifican en el plan externo.

## Registro histórico de la auditoría

Inicio: 2026-10-07 (Lima). Objetivo completo: terminar todos los requisitos de PLAN-ATENCION-AUTONOMA-2026-10.md, incluidas las ampliaciones de Umbler, promociones, medios y perfiles. Producción es de solo lectura: no desplegar, publicar Meta, activar campañas reales ni enviar mensajes a clientes durante esta tarea.

## Evidencia de partida

- Árbol local: al iniciar solo estaba modificado el plan de atención autónoma. Se inspeccionó el código actual, no se tomó la tabla histórica como prueba.
- Suite original ejecutada: 56/56 checks, aislada con SQLite temporal y proveedores simulados. Esto no demuestra funcionamiento real de Meta, Postgres, Redis ni del LLM.
- Existen en código FAQ, onboarding, cotización, medios, presencia, handoff, versiones de documentos, flags, métricas y Coex preliminar. Su cobertura se mantiene bajo auditoría.
- Las skills de auditoría/fintech/brainstorming citadas en AGENTS.md no existen en .agents ni .cursor de este checkout; se siguen las reglas explícitas del repositorio sin atribuir una auditoría a esas skills ausentes.

## Matriz del alcance original

| Requisito y prueba necesaria | Evidencia actual | Estado / siguiente trabajo |
|---|---|---|
| Etapa 0: versión desplegada vs repo, 30 chats anonimizados, matriz endpoints y permisos | Documento ETAPA-0 y lectura previa de 5 historiales, 20 resúmenes, 7 flujos Umbler | Incompleto. Faltan comparación de artefactos desplegados y muestra 30. No abrir chats que cambien leído sin autorización; obtener exportación autorizada de solo lectura. |
| Etapa 1: FAQ ES/PT aprobada, fuente, contexto, agrupación, aclaraciones, límite de repetición | knowledge.py, agent_graph.py, debounce.py y checks 47/49; 54 evals deterministas | Parcial. Confirmar aprobación comercial real; evaluar naturalidad con LLM y conversaciones reales. |
| Etapa 2: contratos, timeout real, idempotencia concurrente, identidad y permisos, resultados verificados | tool_contracts.py, idempotency.py, lead_onboarding.py, checks 38–42/55/59 | Parcial. Corregidos timeout real, reserva atómica previa y persistencia de resultados tardíos; check 59 prueba concurrencia local. Pendientes identidad/permisos, reconciliación de escrituras inciertas y prueba Postgres. |
| Consulta del estado de operación con verificación de pertenencia | status.lookup declara unavailable y deriva | Falta endpoint autorizado e integración; handoff es alternativa operativa, no cumplimiento del endpoint. |
| Etapa 3: audio ES/PT, confirmación de cifras, evidencia, límites y comprobante humano | audio_flow.py, audio_review.py, rutas/worker y checks 28/32/53 | Base presente; falta acreditar límites de tamaño en todos los canales y validación de adjuntos adversos; ampliar pruebas según hallazgos. |
| Etapa 4: presencia/cola, asignación concurrente, contexto, etiquetas, búsqueda, emojis, takeover | auth.py, presence.py, rutas/panel, checks 25–27/46/51/52/56 | Base presente. Corregido en esta auditoría: pedir humano durante onboarding tenía menor prioridad que pedir documento. Faltan prueba de concurrencia real y permisos por canal/sector. |
| Etapa 5: métricas costes/tiempos/satisfacción, piloto, backups/rollback ensayado, revisión semanal | observability.py, RUNBOOK y CI | No completo. Faltan satisfacción, piloto, eval LLM real, infra real, evidencia de restauración y métricas acordadas. |
| Identidad WA: contrato vigente, BSUID sin teléfono, migración, cambios de identidad | Parser conserva datos adicionales pero identifica por from; customers exige teléfono | No completo. Confirmar contrato Meta y adaptar identidad sin inferir campos. Conservar campos desconocidos no basta. |
| Coex: elegibilidad, Embedded Signup, eventos de celular, sincronización, invalidación de IA pendiente, aislamiento | Conexiones y ecos preliminares tras flag; check 50 | Parcial. history/state_sync solo se registran; faltan sincronización requerida, carreras de trabajos pendientes y prueba con número elegible. |
| API estándar/Coex y varios números: matriz de recepción/envío/media/estados, corte/reconexión, reversión | Registro y routing local de conexiones | Parcial. Verificar todas las salidas incluyendo plantillas/media proxy; falta matriz real y reversión. |
| Documentos públicos: editor, versiones, ES/PT, permisos, borradores privados, solicitud rastreable | public_docs.py y páginas; check 54 | Base técnica presente. Falta contenido aprobado, concurrencia de versiones, verificación pública desplegada y URL exactas en Meta. No publicar texto legal sin aprobación. |
| Promociones: identidad/historial, reglas, catálogo, límites, reserva/consumo, imágenes y pruebas | API Brasper tiene Coupon y redemption; validación 0–100; IA filtra automatic; nuevo historial privado distingue completados y pendientes, verificando cliente/teléfono. No vincula ni ofrece banner por coincidencia de nombre | No completo. Falta catálogo y selección individual de campañas, reserva/consumo/reversa concurrentes con la regla aprobada. El historial calcula elegibilidad, todavía no reserva beneficios. No hay campaña real activada. |
| Personalidades: versiones, canal/número, conocimiento y herramientas | Implementado en esta auditoría: agent_profiles.py, api/profiles.py, /agentes y conexión al grafo | Validar UI y regresión final. Borrador/publicación, historial/restauración, concurrencia optimista, scope por canal/conexión, versión fijada por conversación, capacidades y FAQ limitadas; sin perfiles sigue el prompt general. |
| Biblioteca: material aprobado, idioma, propósito, versión, vista previa, evitar duplicados, fallos de imagen | Envío URL/upload existe; catálogo no | Pendiente. Separar promociones/cuentas oficiales de comprobantes privados. |
| Encuestas y reclamos: ES/PT, comentario, no duplicados, derivación con resumen | Umbler inspeccionado; sin módulo equivalente propio | Pendiente. |
| Espera/inactividad: horario, zona, SLA, recordatorios limitados, permisos del canal, contexto | Cola básica y plantillas existentes | Pendiente de implementación integral y validación de reglas Meta. |
| Atención libre: datos ya dados, cambios de intención, correcciones, ES/PT consistente | Grafo determinista + LLM; prioridad de humano corregida | Parcial. Onboarding aún tiene textos fijos ES; revisar retornos PT y continuidad de todos los recorridos. |
| Evaluación final: pruebas fintech en run_checks, evals, tipado/build, migraciones, Postgres/Redis, Lighthouse, smoke | Suites presentes; se ejecutan tras cambios relevantes | Pendiente de certificar alcance completo. Lighthouse actual solo mide shell/login, no bandeja autenticada. |

## Cambios y validación en curso

- Nueva administración de perfiles de agente con borradores, publicación por versión, historial y desactivación para nuevas conversaciones. Conversaciones en curso conservan la versión seleccionada. Las capacidades del perfil solo restringen las capacidades existentes; no crean permisos financieros.
- Restricción de FAQ también se aplica al seleccionar su traducción, evitando salir de la lista permitida.
- Prioridad de solicitud de humano sobre onboarding; no se guarda el texto de esa petición como documento de identidad.
- Timeout devuelve al vencer el plazo sin esperar al worker; reserva atómica evita repetir escrituras concurrentes y conserva resultados tardíos. Las claves de herramientas no se purgan automáticamente: requiere reconciliación/retención específica antes de lanzamiento, para no repetir una escritura cuyo resultado sea incierto.
- API Brasper local: 0–100% finito validado en alta/edición de cupones y al consumir cupones antiguos. El cálculo de la IA descarta porcentajes inválidos, verifica alcance/par, vigencia y cupos; usa la ruta pública `/transactions/coupons/automatic`. Cupones con límites personales esperan integración de elegibilidad autorizada; no se prometen a clientes anónimos.
- Caché financiera vencida deja de usarse cuando falla la API. La caché vigente conserva el TTL configurado; una cotización no reserva usos de cupón y el backend debe volver a validar al registrar la operación.
- Evidencia actual local: 61/61 checks del bot, 54/54 evals deterministas y doctests. Build/TypeScript pasó tras añadir capacidades y alcance FAQ a perfiles. API Brasper: 17/17 tests de porcentajes y concurrencia simulada; no demuestra bloqueo en Postgres real. No se desplegó ni se ejecutaron pagos o mensajes reales.

### Continuación 2026-10-08 (Lima): identidad e historial

- La API privada incluye `/brasper/ai/clients/{user_id}/history`, protegida por secreto y coincidencia de cliente/teléfono. Cuenta completados y operaciones pendientes. No envía números de documento, saldos ni detalle de operaciones. Un completado incluso eliminado lógicamente conserva el historial, para que borrar registros no reinicie beneficios.
- El bot consulta ese historial únicamente con vínculo de teléfono proveniente del canal. Telegram/webchat con teléfono escrito por el usuario requieren un mecanismo adicional de verificación, todavía pendiente. Datos de historial inválidos o inaccesibles invalidan la elegibilidad anterior explícitamente.
- Nombre coincidente ya no vincula un cliente; nombre no encontrado ya no anuncia primer envío. Identificadores opacos de WhatsApp no se convierten en teléfono extrayendo sus dígitos. Falta aún verificar e implementar el contrato Meta vigente de BSUID.
- Documento capturado se marca registrado, no verificado. El upsert devuelve el cliente coincidente sin sobrescribir nombre/documento/contacto y rechaza coincidencias parciales que podrían reasignar una identidad. Corregir datos de un cliente existente queda para la ruta autenticada/humana.
- El timeout de alta ya no se da por resuelto porque una búsqueda por teléfono encuentre a alguien: se conserva la reserva y se espera resultado verificable o revisión humana.
- Pruebas API: 28/28 de contratos privados, identidad, porcentajes y concurrencia simulada. Bot: 62/62 checks y 54/54 evals deterministas. No hay despliegue.

No se considera alcanzado el objetivo. Este documento conserva los pendientes de todas las etapas; completar un módulo no reduce el alcance original.

## Avance verificado — 9 de octubre de 2026

Este registro sustituye los conteos históricos anteriores; no declara cerrado C1–C8.

- API: 105 pruebas seleccionadas aprobadas (campañas, comisiones, cupones, transacciones, identidad y contratos privados). La selección de comisión ahora es compartida por cotización y registro; los huecos internos sin comisión se rechazan.
- Bot: última ejecución registrada 69/69 checks; 54/54 escenarios deterministas y doctests anteriores al último lote. TypeScript aprobado; falta repetir build y evaluar las últimas pantallas.
- SQLite: migración con datos sintéticos históricos 0006 → 0009, repetición y copia/restauración aprobadas. No acredita las migraciones financieras 083/084 de PostgreSQL.
- Vinculación segura: API local emite códigos de un uso de cinco minutos desde la sesión del cliente; grants de treinta minutos vinculados a cliente/canal/referencia, guardados como hashes. Consulta privada de operaciones exige grant válido e integración. Flag BRASPER_IA_IDENTITY_LINK_ENABLED desactivado por defecto. Falta portal para emitir, integración del bot, almacenamiento privado del grant y pruebas de concurrencia real: C2 sigue parcial.
- Documentos: se evita guardar una respuesta antigua sobre otra selección; hay control de cambios sin guardar. Medios limitados a 20 MiB durante descarga, origen WhatsApp validado y caché privada descartada al cerrar sesión.
- PostgreSQL/Redis: runner aislado preparado en docker-compose.validation.yml. No ejecutado; equipo sin Docker/WSL y Windows bloquea los binarios descargados. No se modificó esa protección.

Pendientes locales principales: identidad de extremo a extremo; contactos y alias canónicos; sincronización Coex/reconciliación; permisos por canal/sector; carreras de entrega y caída de Redis; validación PostgreSQL/Redis, migraciones financieras, build y comprobación de pantallas. Los requisitos externos permanecen en el plan separado. Producción no fue modificada durante este avance.
