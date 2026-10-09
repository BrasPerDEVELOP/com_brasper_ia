# Plan de mejora: atención autónoma Brasper

## Plan de ejecución actualizado — 8 de octubre de 2026

El alcance se conserva, pero el trabajo se divide para poder entregar el desarrollo a una persona o agente sin esperar acceso a terceros:

- **Código y pruebas locales:** [PLAN-CODIGO-PENDIENTE-2026-10.md](PLAN-CODIGO-PENDIENTE-2026-10.md). Lista vigente C1–C8 con archivos, orden y criterios de aceptación; incluye lo que falta en nuestra API de Brasper.
- **Cuentas, contratos y pruebas externas:** [PLAN-DEPENDENCIAS-EXTERNAS-2026-10.md](PLAN-DEPENDENCIAS-EXTERNAS-2026-10.md). Meta, Coex real, Kommo, aprobaciones de contenido, modelo real y piloto.
- **Prompt para entregar al desarrollador:** [PROMPT-AGENTE-CODIGO-2026-10.md](PROMPT-AGENTE-CODIGO-2026-10.md).

Estas listas reemplazan los estados históricos de las secciones siguientes como guía de ejecución. Promociones, perfiles y biblioteca ya tienen implementación local; todavía necesitan los cierres y pruebas indicados. No están desplegados. Terminar el plan de código no equivale a haber validado las cuentas o la integración real de Coex.

## Alcance original y antecedentes

Fecha: 7 de octubre de 2026. Estado: **en implementación y auditoría; no terminado ni desplegado**. La sección «Estado de ejecución» es una fotografía anterior a las ampliaciones de promociones y agentes, no una certificación del alcance completo. Ver [AUDITORIA-ATENCION-AUTONOMA-2026-10.md](AUDITORIA-ATENCION-AUTONOMA-2026-10.md) para evidencia, trabajo pendiente y condiciones externas.

## Objetivo y alcance

La IA debe completar la atención habitual de principio a fin: entender la necesidad, resolver dudas, cotizar, reunir datos, ejecutar acciones habilitadas y comunicar resultados comprobados. El panel sirve para supervisar y atender excepciones. Recibir un audio no implica derivación automática.

Este plan complementa PLAN-MEJORAS-2026-10.md. Sus diagnósticos históricos y conteos de tests deben verificarse antes de tratarlos como estado actual. La revisión realizada confirma en el código local asignación por menor carga sin presencia, procesamiento de audios y una bandeja básica. No se ha comprobado equivalencia entre ese código y la versión desplegada.

## Principios

- Una conversación coherente para el cliente; rutas especializadas para cotización, onboarding, soporte y seguimiento.
- Tasas, comisiones, cupones y cuentas exclusivamente desde herramientas/API Brasper. Nunca calcularlos ni inventarlos con el LLM.
- Información del negocio desde fuentes aprobadas, versionadas y con fecha de revisión.
- Separar interpretar una solicitud de autorizar y ejecutar una acción. Texto, audio y documentos del cliente no pueden alterar permisos ni instrucciones del sistema.
- Confirmar datos y consentimiento antes de acciones que comprometan al cliente. No afirmar éxito hasta recibir y verificar el resultado de la API.
- El comprobante recibido no acredita por sí mismo un pago. La confirmación debe venir del sistema autorizado.
- Registrar acciones, errores y versiones; minimizar datos personales y excluir secretos de logs.
- Mantener al cliente informado ante fallos, demoras y derivación. Evitar respuestas repetitivas y bucles.

## Etapas y criterios de aceptación

| Etapa | Entregables | Criterio para avanzar |
|---|---|---|
| 0. Diagnóstico y línea base | Comparar versión desplegada con repo; inventario de herramientas, canales y permisos; revisar 30 conversaciones anonimizadas; matriz de tareas y endpoints disponibles | Cada tarea queda clasificada como operativa, incompleta o sin API; se conocen causas reales de fallos y derivación |
| 1. Conocimiento y conversación | FAQ aprobada ES/PT; recuperación con fuente; contexto persistente y datos estructurados; agrupar mensajes; aclaraciones puntuales; límite de repeticiones | Preguntas reales se responden con fuente o incertidumbre explícita; conserva monto, moneda y etapa; no inventa información |
| 2. Herramientas y flujos completos | Contratos tipados y validados; cotización, identificación, registro y consulta de estado según capacidades de la API; estados persistentes; confirmación de acciones | Recorrido completo en entorno de prueba, con resultado verificable; una petición repetida no duplica operaciones |
| 3. Audios y adjuntos | Transcripción ES/PT; confirmar cifras ambiguas; reproducir audio en panel; conservar evidencia y estado de procesamiento; límites de tamaño y tipo | Audio legible continúa con IA; audio ambiguo solicita aclaración; adjunto no se pierde; comprobante nunca se confunde con pago confirmado |
| 4. Excepciones y CRM | Presencia con heartbeat y vencimiento; disponible/ocupado/ausente; asignación por carga con protección de concurrencia; cola si no hay asesores; resumen y motivo de derivación; filtros, etiquetas, búsqueda y emojis | No asigna a un asesor ausente; bot se pausa durante takeover; dos asignaciones simultáneas no provocan conflicto; asesor recibe contexto completo |
| 5. Piloto y operación | Evaluaciones, alertas, costes y tiempos por flujo; despliegue gradual con flags; backup y rollback; revisión semanal de fallos | Piloto cumple métricas acordadas, sin fallos críticos de autorización, datos o duplicación; reversión ensayada |

Orden: 0 → 1 → 2 → 3 → 4 → 5. El panel puede avanzar junto con audios después de cerrar contratos y estados. Las etapas son dependencias, no una estimación de fechas.

## Reglas de ejecución

Cada herramienta debe tener entradas permitidas, permisos, timeout, salida estructurada y errores distinguibles. Usar claves de idempotencia y deduplicación de webhooks; reintentos limitados solo cuando sean seguros. Si una escritura vence por timeout, consultar su resultado antes de repetirla. Verificar identidad y pertenencia antes de mostrar datos de una operación.

La IA deriva cuando el cliente lo pide, necesita una acción no habilitada, persiste una ambigüedad tras aclaraciones o falla un sistema necesario. La transferencia incluye resumen, datos verificados, pasos realizados y pendiente. Si nadie está disponible, conservar la solicitud en cola y explicar la espera. No derivar por el mero hecho de recibir audio.

Grupos de WhatsApp y edición de mensajes enviados quedan en investigación: comprobar la integración concreta y documentación vigente del proveedor antes de incluirlos como entregables. Editar un borrador y editar un mensaje ya enviado son capacidades distintas.

## Validación y métricas

Construir un conjunto inicial de 50 escenarios ES/PT a partir de conversaciones anonimizadas: cotizar, cambiar monto, retomar sesión, documentos, audio, estado, asesor, caída de API, webhook duplicado, timeout tras escritura e intento de cambiar instrucciones. Separar pruebas deterministas con stubs de evaluaciones del LLM real y de smoke controlado sin movimientos financieros reales.

Cada regla fintech nueva requiere un caso en backend/tests/run_checks.py. CI debe validar backend, migraciones relevantes, tipado y build del panel. Verificar Postgres/Redis y smoke tras despliegue.

Medir: tareas elegibles completadas sin asesor, exactitud por flujo, operaciones duplicadas, afirmaciones sin respaldo, motivos de derivación, tiempo p50/p95, coste por resolución y satisfacción. Una respuesta enviada no cuenta como tarea completada. Propuesta de meta para piloto: 80% de resolución autónoma en tareas elegibles; ajustar después de medir línea base. Gates obligatorios: ningún fallo crítico de permisos, ninguna duplicación en escenarios de prueba y todos los datos financieros respaldados por herramientas. No prometer 100% de autonomía ni confundir una muestra sin errores con garantía absoluta.

## Primer lote concreto

1. Auditar versión y 30 conversaciones; producir matriz de tareas/API y línea base.
2. Aprobar FAQ ES/PT y contratos de cotización, onboarding y seguimiento.
3. Implementar un flujo completo prioritario: cotizar → confirmar datos → siguiente acción disponible → verificar resultado.
4. Añadir audios y pruebas de errores/repetición a ese flujo.
5. Pilotearlo y usar los fallos observados para ordenar el siguiente lote.

## Referencias

- Umbler, buenas prácticas de agentes IA: objetivos específicos, etapas de conversación, fuentes actualizadas, agrupación de mensajes, límites de respuesta, pruebas reales e integraciones pertinentes: https://help.umbler.com/hc/pt-br/articles/42630599181453-Agente-de-IA-no-Talk-Boas-pr%C3%A1ticas-de-atendimento-e-uso
- Repo: AGENTS.md; backend/core/auth.py; backend/api/routes.py; web/app/conversaciones/page.tsx; docs/plans/PLAN-MEJORAS-2026-10.md.

Las medidas de idempotencia, permisos, verificación financiera y despliegue gradual son propuestas específicas para Brasper; no se atribuyen a Umbler.

## Actualización: identidad WhatsApp Cloud API y BSUID

Consulta: 7 de octubre de 2026. Meta confirma usernames y Business Scoped User ID (BSUID) en su publicación oficial del 16 de junio de 2026: https://developers.meta.com/resources/videos/whatsapp-usernames/ . El teléfono no debe suponerse disponible para usuarios que adoptan usernames. Username visible y BSUID técnico son conceptos distintos. Meta también menciona regla de visibilidad de 30 días, Contact Book y REQUEST_CONTACT_INFO.

Hallazgos locales: whatsapp.py fija Graph v21.0, parse_incoming conserva from pero no identidades adicionales, los envíos usan to; routes.py genera wa:{from}; customers exige phone_number UNIQUE NOT NULL. Esto requiere revisión antes de conectar Cloud API en producción; no prueba que toda recepción actual falle.

Añadir como condición de etapa 0/2:
- Confirmar versión Graph soportada y contrato directo de Cloud API con documentación y payloads reales de la cuenta. No copiar campos de Twilio/otros BSP como si fueran Meta.
- Separar contacto interno, BSUID con alcance de portfolio, teléfono opcional, username de presentación e identidad verificada en Brasper.
- Adaptar recepción, envíos de texto/media/templates, estados de entrega y eventos de cambio de identidad según contrato confirmado.
- Migrar clientes históricos sin perder conversación ni crear duplicados; solo vincular identidades con evidencia fiable. Username no es clave estable ni prueba de identidad financiera.
- Si falta teléfono y una tarea realmente lo requiere, solicitarlo con consentimiento mediante función soportada; el chat debe continuar sin exigirlo por defecto.
- Casos: teléfono con BSUID, BSUID sin teléfono, cambio de username, cambio de identidad, texto/audio/adjuntos, replies del asesor, historial previo y webhooks repetidos.

Limitación de consulta: la página detallada de BSUID de developers.facebook.com devolvió HTTP 429; no se consideran confirmados aquí los nombres exactos de todos los campos ni sus fechas de disponibilidad por cuenta. Referencia a validar: https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids . No se ha cambiado código ni servidor.

## Coexistencia: WhatsApp Business del celular + API oficial

Objetivo: conservar el número operativo en la app del celular y permitir atención de la IA desde nuestro backend, con una conversación coherente y control de intervención humana.

### Estado observado en Meta (7 de octubre de 2026)

- Portfolio BrasPer transferencias: empresa verificada desde el 3 de mayo de 2026.
- Contact Book habilitado.
- Cuenta WhatsApp 430159343521708: identificada como App de WhatsApp Business, verificada y aprobada.
- Número +51 926 032 463: conectado, calidad alta; Kommo aparece como socio con control total.
- Estos datos no confirman por sí solos el modo Coex, la elegibilidad para otro onboarding ni permisos de nuestra app. No se modificó configuración.

### Decisión de conexión (etapa 0)

1. Revisar app de Meta, permisos, titularidad, suscripciones de webhook y modalidad actual de Kommo mediante consulta. Confirmar restricciones del número y procedimiento oficial vigente antes de cualquier cambio.
2. Evaluar dos caminos: proveedor compatible con Coex y con integración para nuestro backend; o conexión propia mediante app de Meta y Embedded Signup para WhatsApp Business App.
3. Para conexión propia, comprobar requisitos vigentes de Tech Provider, revisión de app, acceso a permisos whatsapp_business_messaging/whatsapp_business_management y configuración de Facebook Login for Business. La verificación empresarial de Brasper no equivale a aprobación de la app.
4. Documentar camino elegido, costes, permisos, responsable de facturación, coexistencia con proveedor actual y reversión. No asumir que una segunda integración puede añadirse sin migración ni conflicto.

### Requisitos de Brasper

- Número activo en WhatsApp Business del celular, acceso al dispositivo y versión compatible según documentación vigente.
- Administrador autorizado del portfolio y activos WhatsApp; comprobar permisos efectivos.
- Elegibilidad del número/cuenta/país para el flujo Coex y requisitos actuales del proveedor o Meta.
- Completar autenticación, consentimiento y conexión por el flujo específico de coexistencia. No borrar la cuenta del celular ni registrar el número por el flujo estándar como sustituto de Coex.
- Confirmar facturación y condiciones aplicables antes de habilitar tráfico de producción.

### Adaptaciones del sistema (etapas 2 a 4)

- Integrar onboarding cuando corresponda; almacenar tokens exclusivamente en backend, gestionar renovación/revocación y permisos mínimos.
- Procesar mensajes entrantes, estados de envío y eventos de coexistencia. Validar en documentación y cuenta los contratos de smb_message_echoes, smb_app_state_sync e history antes de implementarlos.
- Guardar mensajes enviados desde el celular como actividad humana en la conversación correcta; deduplicar por identificador de mensaje y distinguir origen celular/API/cliente.
- Implementar control persistente IA/humano: un mensaje humano pausa el bot, invalida respuestas pendientes y revalida propiedad antes de enviar. Definir devolución explícita a la IA y evitar que un eco de la propia API active takeover.
- Sincronizar contactos e historial solo dentro del alcance autorizado y soportado; no prometer sincronización completa de grupos, llamadas, mensajes antiguos ni todas las funciones de la app.
- Aplicar modelo de identidad con BSUID, teléfono opcional, alcance empresarial y vinculación verificada al cliente Brasper.
- Conservar validación de firma, deduplicación, cola, reintentos seguros y observabilidad. Los eventos de historial no deben disparar respuestas automáticas.
- Mostrar en panel origen del mensaje, responsable actual, estado de sincronización y acción para devolver al bot.

### Pruebas y aceptación de Coex (etapa 5)

Probar con cuenta/número de prueba elegible: cliente → IA, IA → cliente, celular → cliente, panel → cliente, audio/adjuntos, eco repetido, entrega fuera de orden, reconexión, importación de historial, BSUID sin teléfono y respuesta de IA en curso cuando interviene un humano.

Criterios: celular permanece operativo; mensajes soportados aparecen una sola vez; la IA no responde a historial ni a ecos propios; intervención humana impide respuestas pendientes del bot; retomar IA requiere la política acordada; fallos quedan registrados y el cliente no recibe confirmaciones falsas.

Preparar respaldo y procedimiento documentado de reversión del proveedor/configuración. El piloto comienza con un alcance acotado; el número principal se conecta solo después de verificar requisitos y pruebas. La aprobación de cambios externos queda fuera de esta revisión de solo lectura.

Referencias a validar antes de implementación:
- Meta, Embedded Signup: https://www.postman.com/meta/whatsapp-business-platform/overview
- Meta, onboarding WhatsApp Business App: https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users
- Meta, Tech Provider: https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-customers-as-a-tech-provider

La documentación detallada de Meta estuvo limitada por HTTP 429 durante la consulta. Requisitos, campos y disponibilidad deben confirmarse de nuevo al implementar; no se presentan aquí como contratos ya validados.

## Varios números: conexión API estándar y Coex

Objetivo: permitir que Brasper conecte varios números y seleccione para cada uno API estándar (por ejemplo, un número nuevo) o coexistencia (un número elegible ya activo en WhatsApp Business). Ambas modalidades usan Cloud API. El soporte de varios números dentro de Brasper no implica convertir la plataforma en multiempresa.

### Trabajo necesario

- Inventariar número, phone_number_id, WABA, portfolio, modalidad, app/proveedor, permisos y estado de cada conexión.
- Confirmar procedimiento vigente de alta de números nuevos y onboarding Coex; incluir migración de números existentes como caso independiente sujeto a restricciones verificadas.
- Reemplazar la configuración de un único número por un registro de conexiones de Brasper. Mantener secretos en entorno o almacén seguro; la base guarda referencias.
- Resolver cada webhook por phone_number_id y seleccionar credenciales, destino y modalidad de la conexión correcta para todas las rutas, jobs y respuestas del asesor.
- Persistir conexión de origen por conversación. Una respuesta debe salir por el número que recibió el mensaje; no cambiar de número implícitamente.
- Mantener identidad del contacto por alcance de portfolio/BSUID y contexto de atención por conexión. Si el mismo cliente escribe a dos números, enlazarlo solo con evidencia fiable; no mezclar conversaciones ni datos automáticamente.
- Aplicar sincronización y takeover del celular únicamente donde Coex esté habilitado; API estándar conserva takeover desde panel.
- Mostrar número/canal y modalidad en bandeja, filtros y estado de conexión. Permitir políticas de atención por número conservando la configuración general de Brasper.

### Matriz de pruebas

| Escenario | Resultado esperado |
|---|---|
| Número nuevo conectado mediante API estándar | Recibe y responde por Cloud API; no se presupone uso simultáneo de la app |
| Número existente elegible conectado por Coex | App y API funcionan; intervención desde celular pausa IA |
| Dos números API simultáneos | Cada respuesta utiliza su conexión de origen |
| Dos números Coex simultáneos | Ecos, historial y takeover se aplican a la conversación correcta |
| API estándar y Coex simultáneos | Comparten servicios Brasper sin cruzar mensajes ni credenciales |
| Mismo cliente escribe a dos números | Contextos de conversación separados; vínculo de cliente verificado |
| Conexiones en portfolios distintos con BSUID | Identidades aisladas por alcance; sin asumir equivalencia |
| Credencial revocada o conexión caída | Se identifica conexión afectada y otras continúan operativas |
| Duplicados, jobs demorados y cambios de configuración | No duplican envíos ni redirigen una respuesta a otro número |

### Ejecución y aceptación

Primero probar en entorno controlado con recursos de prueba compatibles. Un número sandbox de Cloud API no demuestra elegibilidad Coex: esa modalidad requiere una cuenta/número elegible y completar el flujo real. Después pilotear al menos una conexión API estándar y una Coex; ampliar a varios números al pasar pruebas de aislamiento y concurrencia.

Registrar evidencias: modalidad confirmada, identificadores de prueba, recepción/envío y estados, ausencia de respuestas cruzadas, takeover y resultado de reversión. No enviar mensajes a clientes reales como parte del test. Las altas externas, permisos, condiciones y costes se revisan antes de activarlas. Estado actual: agregado al plan; no se han creado números ni ejecutado estas pruebas.

Dependencias: etapa 0 confirma recursos y requisitos; etapa 2 incorpora registro y enrutamiento; etapas 3/4 extienden medios y takeover; etapa 5 ejecuta la matriz y el piloto.

## Páginas públicas y vista de administración para Meta

Estado: pendiente de implementación y aprobación de contenido. No existen todavía URLs verificadas para completar los campos legales de la app.

### Ubicación propuesta

- Decisión del usuario: publicar en Brasper IA las rutas https://ia.finzeler.com/privacidad, https://ia.finzeler.com/terminos y https://ia.finzeler.com/eliminacion-de-datos como páginas públicas por HTTPS sin login. Son rutas propuestas, no páginas existentes.
- ia.finzeler.com/conversaciones: mantener como panel privado de atención. No usar esta URL como política de privacidad ni instrucciones de eliminación.
- El frontend y backend de Brasper IA alojan documentos y solicitudes. Implementar layout público separado del control de sesión de AppFrame; las páginas legales no deben redirigir al login. La vista de administración y conversaciones conserva autenticación y permisos. No se requieren cambios en brasper.com.

### Contenido y proceso

- Identificar entidad responsable, contacto de privacidad validado y alcance: sitio, chatbot, WhatsApp, panel e integraciones Meta.
- Documentar datos recogidos, fines, proveedores/procesadores de IA y mensajería, accesos, retención real, derechos y proceso para solicitar eliminación. No inventar plazos ni compromisos que el sistema no cumpla.
- Explicar qué datos puede eliminar Brasper y qué registros requieren conservación conforme a obligaciones confirmadas por la empresa. Revisar contenido con el responsable designado antes de publicarlo.
- Ofrecer instrucciones y un canal operativo de solicitud. No exigir login para leerlas. Validar identidad antes de ejecutar una eliminación y evitar exponer información de clientes a terceros.
- No confundir URL de instrucciones con callback de eliminación de Meta; usar inicialmente la opción de instrucciones. Si se implementa callback, diseñar y validar su contrato por separado.

### Vista para administrar y publicar

Añadir en panel una sección Documentos públicos, accesible a roles autorizados: editar contenido ES/PT, previsualizar página, guardar borrador, revisar y publicar versión aprobada. Registrar autor, fecha, versión e historial. Mostrar URL pública y estado de publicación.

El contenido público debe limitarse a los documentos y excluir configuración, tokens o datos de conversaciones. Preferir texto/Markdown sanitizado; no aceptar HTML ejecutable. Si se permite subir PDF, restringir tamaño/tipo, validar archivo y servirlo como documento estático sin ejecución. Mantener una página HTML accesible con instrucciones y enlace al PDF opcional.

Mantener edición y publicación dentro de Brasper IA, con autorización de backend y sin credenciales en el navegador. Las páginas públicas leen únicamente versiones publicadas. Determinar almacenamiento, canal de despliegue y rol editor/revisor antes de implementar.

### Aceptación y configuración de Meta

- URLs públicas devuelven HTTP 200 sin autenticación en móvil y escritorio; enlaces del footer y navegación disponibles.
- Borradores no son públicos; solo roles autorizados publican; versiones y cambios quedan auditados.
- Formulario/canal de eliminación funciona y permite seguimiento interno sin ejecutar borrados automáticos por una solicitud no verificada.
- Revisar coherencia con tratamiento y retención reales, y aprobación del responsable de Brasper.
- Solo tras publicación verificada, completar en app Meta las URLs exactas de privacidad, condiciones e instrucciones de eliminación. Esto no publica la app Meta.

Dependencias: etapa 0 define responsable/contacto y tratamiento real; etapa 4 implementa vista y páginas; antes de solicitar revisión o publicar app Meta deben existir documentos aprobados y accesibles. No está autorizado aquí publicar textos legales todavía inexistentes; esta sección incorpora el trabajo al plan.


## Estado de ejecución (2026-10-07)

Validación: `run_checks.py` 56/56 · `tests/evals/run.py` 54/54 escenarios ES/PT · panel `tsc` + `next build` en verde · todo bajo flags (`tenants.json → features`) para despliegue gradual y reversión.

| Etapa | Hecho en el repo | Pendiente [externo] |
|---|---|---|
| **0. Diagnóstico y línea base** | Inventario de canales/herramientas/permisos, matriz tarea↔endpoint (operativa / incompleta / sin API), causas de derivación instrumentadas y línea base técnica: [ATENCION-AUTONOMA-ETAPA-0.md](ATENCION-AUTONOMA-ETAPA-0.md). `GET /api/tools` expone los contratos y su disponibilidad real. | Comparar versión desplegada con el repo; revisar 30 conversaciones anonimizadas; confirmar con Meta la configuración de la cuenta/app. |
| **1. Conocimiento y conversación** | FAQ ES/PT con fuente y fecha (`backend/data/knowledge/brasper/faq.json`, 13 aprobadas + 3 borradores que el bot no sirve), recuperación determinista (`core/knowledge.py`), ruta `handle_info` con incertidumbre explícita cuando no hay respuesta aprobada, contexto persistente (`lead_data`), agrupación de ráfagas (debounce Redis existente), aclaraciones puntuales del cotizador, **límite de repeticiones** (`_anti_loop`: aviso y luego asesor). Panel › Conocimiento. | Aprobación comercial de horarios, tiempos de acreditación y límites (borradores). |
| **2. Herramientas y flujos completos** | Contratos tipados con entradas permitidas, permiso, timeout, salida validada y errores distinguibles (`core/tool_contracts.py`); **idempotencia** del alta de cliente y **consulta tras timeout** antes de repetir (`lead_onboarding`); **deduplicación de webhooks** por id (`core/idempotency.py`); consulta de estado: la API IA no la expone → `handle_status` deriva con resumen en vez de inventar. Recorrido cotizar → identificar → cuentas oficiales → comprobante validado por humano cubierto por `run_checks` 38–41, 55. | Exponer una API de estado de operación en la integración IA (hoy `status.lookup` = sin API). |
| **3. Audios y adjuntos** | Flujo compartido WA/Telegram/worker (`core/audio_flow.py`): transcripción ES/PT, **revisión de cifras ambiguas** → confirmación (`core/audio_review.py`), evidencia (audio original + transcripción, reproducible en el panel), estado de procesamiento, audio no transcribible → asesor sin perder el archivo; límites de tipo (imagen/PDF = comprobante; video/sticker = cortesía); el comprobante **nunca** se confunde con pago confirmado (`proof_validated=false`, ack explícito). Recibir un audio ya no deriva automáticamente. | — |
| **4. Excepciones y CRM** | Presencia con heartbeat y vencimiento (`core/presence.py`, `POST /api/presence`, selector Disponible/Ocupado/Ausente en el panel), asignación por carga que excluye ausentes con `presence_required`, **cola** cuando no hay asesores (aviso al cliente), **claim atómico** (409 ante doble toma), **resumen y motivo de derivación** (`core/handoff_summary.py`) visible en la ficha; filtros por canal/etiqueta, **etiquetas** (`conversation_tags`), búsqueda y emojis en el panel; origen humano (celular/API) y conexión visibles. | Horario/SLA del equipo para calibrar la cola. |
| **5. Piloto y operación** | Evaluaciones: 54 escenarios (`tests/evals/scenarios.json` + `run.py`) en CI; métricas por flujo (conteo, errores, p50/p95) en `/api/ops/metrics`; alertas existentes; **flags** por capacidad (`core/features.py`); backup/rollback y **revisión semanal** documentados en `backend/RUNBOOK.md` §9. | Ejecutar el piloto con tráfico real, medir la línea base y la meta (80 % de resolución autónoma en tareas elegibles). |
| **Identidad WhatsApp (BSUID/usernames)** | `parse_incoming` conserva `id`, `timestamp`, `contacts[].profile.name`, `wa_id` y **cualquier campo adicional** en `lead_data.wa_identity` sin asumir su semántica; estados de entrega procesados sin responder; el teléfono sigue siendo `from`. | Confirmar con Meta nombres de campo y disponibilidad por cuenta; migración de `customers.phone_number NOT NULL` solo con contrato confirmado. |
| **Coexistencia** | Registro de conexiones (`whatsapp.connections`, modo `standard`/`coex`), `connection_id` por conversación y respuestas por el número de origen; ecos `smb_message_echoes` = actividad humana (pausa el bot, `sender=agent`, `agent_email=whatsapp-app`, dedup por id, sin eco de la propia API); `history`/`smb_app_state_sync` solo se registran. Todo tras `features.coex`. | Elegibilidad, Embedded Signup/Tech Provider, facturación y pruebas con número elegible (ver sección Coex). |
| **Varios números** | Resolución de webhook por `phone_number_id`, credenciales por conexión en envíos de texto/media/upload, inventario `GET /api/whatsapp/connections` (sin secretos), número visible en bandeja y ficha. | Alta real de números y matriz de pruebas con recursos de Meta. |
| **Páginas públicas y vista Meta** | Rutas públicas sin login `/privacidad`, `/terminos`, `/eliminacion-de-datos` (solo versión publicada; si no hay, "Documento en preparación"), formulario de solicitud de eliminación (registra, no borra), vista de administración › Documentos públicos con borrador/previsualización/publicación versionada y auditada, lista y estados de solicitudes. Markdown sin HTML ejecutable. | Redactar y aprobar el contenido legal; registrar las URL en la app de Meta tras publicar. |

Decisiones tomadas al ejecutar:
- **Sin respuesta aprobada el bot no deriva automáticamente**: declara incertidumbre y ofrece asesor (deriva si el cliente lo pide). Evita colas por preguntas triviales y cumple "no inventar".
- **SSE/tiempo real** sigue por polling incremental (ver plan del panel); no era requisito de este plan.
- **Sin dependencias nuevas** en backend ni panel.

## Promociones por historial del cliente (requisito añadido 2026-10-07)

Observación directa, solo lectura, del editor Umbler `Brasper - Canal Principal`: existen opciones de primer envío en español y portugués, mensajes que anuncian una promoción de 25% y una imagen adjunta al mensaje español. El texto no establece sobre qué se aplica ese porcentaje. No se modificó ni guardó el flujo. No se confirmó en esta revisión una validación automática del historial de operaciones; seleccionar «primer envío» no acredita elegibilidad.

Requisitos pendientes de implementación:
- Distinguir contacto nuevo en el chat, cliente registrado y cliente con envíos completados. Consultar el historial autorizado de operaciones en la API de Brasper, vinculándolo a una identidad verificada. Un número nuevo o una conversación nueva no reinicia el beneficio.
- Primer envío: ofrecer y aplicar la promoción únicamente cuando el sistema confirme la elegibilidad. Con historial desconocido o API indisponible, pedir verificación del asesor sin prometer el beneficio. Definir comercialmente qué operaciones cuentan, el tratamiento de cancelaciones y el momento en que se consume el beneficio.
- Clientes recurrentes: permitir varias campañas configurables desde una vista Promociones del panel, con borrador, activación/desactivación, vigencia y zona horaria, segmento, dirección/monedas, mínimos/máximos, beneficio y base de cálculo, tope, usos por cliente, prioridad y compatibilidad entre campañas. La IA no crea ni modifica estos valores.
- Vincular a cada campaña textos aprobados ES/PT e imágenes por idioma. Enviar la imagen junto con las condiciones relevantes solo después de resolver elegibilidad; no reenviarla en cada mensaje. Si falla el envío de imagen, conservar explicación en texto y registrar el fallo.
- El backend calcula la promoción y devuelve su identificador, versión, elegibilidad, condiciones y cotización final. La IA comunica esa respuesta. Reservar/aplicar/consumir el beneficio de manera idempotente para evitar usos duplicados entre números, canales y conversaciones; registrar la decisión y gestionar vencimiento de cotizaciones.
- La verificación del pago permanece humana. Recibir un comprobante no confirma el pago ni completa una operación. El comprobante final solo se comunica cuando el equipo o la API confirme su disponibilidad y el resultado real.
- Validación fuera de producción: primer envío elegible, cliente recurrente, identidad sin verificar, historial inaccesible, beneficio ya usado, campañas vencidas o superpuestas, cambio de monto, dos chats simultáneos, imagen fallida y regresión Telegram. No activar campañas ni desplegar por esta incorporación al plan.

Dependencias: contrato de consulta de cliente e historial de operaciones, reglas comerciales aprobadas (incluido el significado del 25% observado), catálogo de imágenes y endpoints de cálculo/aplicación del beneficio. Estado: planificado; no implementado por esta revisión.

## Revisión de Umbler y atención conversacional (2026-10-07)

Alcance: lectura de los siete editores listados, del único agente IA listado y sus pestañas Identidad/Comportamiento/Conocimiento/Habilidades/Flujo, y de configuraciones de atención (canales, atendentes, sectores, reparto, chats, espera, inactividad, horarios, etiquetas, grupos, campos, biblioteca, plantillas, respuestas rápidas, formularios, programación, variables, transferencia, privacidad, webhooks y atajos). No se guardaron cambios ni se ejecutó el agente. Los archivos fuente de conocimiento no se descargaron ni se leyó su contenido; algunas capacidades están bloqueadas por el plan Umbler. No se auditaron secretos API, facturación ni todas las opciones avanzadas anidadas. Leer el editor confirma configuración, no ejecución efectiva de todas las ramas.

Hallazgos:
- Siete flujos: Brasper, Brasper - Canal Principal, Brasper - original NO BORRAR, Fluxos de Braspito, Fluxo, Fluxos de Brasper, Brasper Redirecionamentos. Los primeros tres comparten menús ES/PT, operaciones, monto, primer envío y derivación. No se deben migrar las copias como siete comportamientos independientes.
- Los auxiliares contienen encuesta de cinco respuestas, comentario adicional, despedida y recuperación por humano; redirecciones por petición de asesor, conocimiento insuficiente y límite de respuestas.
- Un agente listado: Brasper, tipo Vendas/Expert, estado Ativo, idioma Português do Brasil, firma activada. Su base conectada Brasper Português tiene un DOCX, cero URLs y cero FAQ. Su única etapa explícita exige un saludo portugués fijo. Tiene automatizaciones por contenido inválido, límite, cierre, humano y respuesta no encontrada. No se verificó integración de operaciones en estas pestañas. La interfaz muestra cero créditos; no se probó el agente para determinar si puede responder actualmente.
- Tres cuentas humanas listadas y un sector Braspito; la reasignación libera la conversación para otro atendente. Algunas ramas seleccionan al atendente Brasper específicamente. No inferir equidad de reparto por esta configuración.
- Dos canales WhatsApp Starter online; un WhatsApp Business API con registro pendiente. No equiparar Starter con Cloud API o Coex. Formularios indica que no existe canal Business API activo. Las listas de respuestas rápidas y templates están vacías.
- Una etiqueta Cliente novo y dos archivos en la biblioteca visible. Horarios, espera, inactividad, grupos organizativos, campos personalizados, variables, privacidad, webhooks y atajos muestran bloqueo por plan. «Grupos» aquí es organización de recursos, no prueba de soporte de grupos WhatsApp por API.

Decisión de producto: atención libre por IA, sin exigir menús numerados ni un constructor visual de flujos. Conservar estado interno, herramientas autorizadas y confirmaciones de operación; permitir corregir monto/destino, cambiar de intención y retomar sin repetir datos.

Trabajo adicional pendiente:
1. Perfiles de agente versionados: nombre de asistente, presentación transparente como IA, tono, longitud, emojis, idiomas, canal/número, conocimiento y herramientas permitidas. El panel ya tiene system_prompt; falta una vista estructurada para perfiles y selección consistente por conversación. Empezar con un perfil Brasper bilingüe y estilos para orientación inicial, atención recurrente y soporte; no cambiar personalidad abruptamente ni simular personas humanas. Estilo nunca altera promociones, tasas ni permisos.
2. Biblioteca de medios aprobados vinculada a campañas, idioma y propósito (promoción, instrucciones, cuentas oficiales). Vista previa, activación, versión y registro de envío; separar material comercial del comprobante específico de una operación. La capacidad técnica de enviar imágenes ya existe; falta la selección autónoma autorizada.
3. Encuesta breve opcional al finalizar atención, ES/PT, sin envío repetido; registrar satisfacción y comentario, detectar reclamos, ofrecer continuación humana con resumen. No finalizar una operación pendiente por cerrar un chat.
4. Seguimiento de espera/inactividad con horario y zona horaria del equipo, aviso honesto, SLA/escalamiento, recordatorios limitados y reanudación del contexto. Respetar consentimiento y reglas del canal; verificar ventana/template vigente mediante contrato Meta antes de activar mensajes proactivos. La vista de plantillas existe en nuestro repo, pero listar nombres no acredita aprobación Meta ni entrega real.
5. Completar conocimiento ES/PT desde fuentes aprobadas, separando FAQ estables de datos financieros en vivo. No copiar el saludo fijo portugués a clientes que escriben español; no derivar automáticamente preguntas triviales por una FAQ faltante.
6. Revisar roles, permisos por canal/sector, disponibilidad y cola, y asegurar pausa inmediata de IA al intervenir el humano. La base de presencia/handoff ya está en el repo; validar comportamiento con la versión desplegada antes de sustituir Umbler.
7. Pruebas conversacionales fuera de producción para promociones, imágenes, perfiles, cambios de intención, reclamos, recuperación de espera y Telegram; comparar con conversaciones reales anonimizadas. Migrar por piloto reversible, no dar por cubierta toda la plataforma por esta inspección.

Estado: estos requisitos adicionales son planificación, no implementación ni despliegue. La verificación de pago permanece humana.

### Aclaración comercial confirmada por el usuario

Las promociones se comportan como los cupones de Brasper: descuento configurable entre 0% y 100% sobre la comisión. El primer envío observado usa 25%; los beneficios de recurrentes dependen de la campaña configurada y activada, sin asumir otro porcentaje. Reutilizar las reglas y validaciones de la API oficial de Brasper. El porcentaje no se aplica al capital enviado ni al tipo de cambio. Vigencia, límites y elegibilidad deben ser explícitos en cada campaña.

Confirmación del usuario (2026-10-08, Lima): para primer envío cuentan las operaciones completadas. Una operación pendiente reserva el beneficio; si falla o se cancela, se libera. Implementar esta regla en la autoridad financiera, con concurrencia entre canales y números. Consultar el historial para decidir elegibilidad no equivale a reservar o consumir el beneficio.
