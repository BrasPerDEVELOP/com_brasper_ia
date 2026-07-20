# Políticas y contratos — Plataforma de bots WhatsApp/Telegram

**PLANTILLA — requiere revisión legal antes de usar; no constituye asesoría legal.**

> Contexto operativo: La agencia (en adelante, "la Agencia" o "el Proveedor") opera bots conversacionales sobre **WhatsApp Cloud API (Meta)**, **Telegram** y **webchat** por cuenta de sus clientes. En la mayoría de los casos, **el Cliente es el responsable/titular del tratamiento** de los datos personales de los usuarios finales, y **la Agencia actúa como encargada del tratamiento** (procesa datos por instrucción del Cliente). Ajustar esta calificación en cada contrato según el caso concreto.
>
> Marco de referencia sugerido (verificar con abogado local): **Perú** — Ley N.º 29733 de Protección de Datos Personales y su Reglamento (D.S. 003-2013-JUS), y disposiciones de la Autoridad Nacional de Protección de Datos Personales (ANPDP). **LatAm** — normas equivalentes por país (ej. LGPD Brasil, Ley 25.326 Argentina, Ley 1581 Colombia, LFPDPPP México). Si se tratan datos de residentes UE, considerar RGPD.

---

## Índice

- [A. Política de retención y borrado de datos](#a-politica-de-retencion-y-borrado-de-datos)
- [B. Política de privacidad y tratamiento de datos](#b-politica-de-privacidad-y-tratamiento-de-datos)
- [C. Contrato base de servicio](#c-contrato-base-de-servicio)
- [Anexo técnico: qué se guarda realmente en la plataforma](#anexo-tecnico-que-se-guarda-realmente-en-la-plataforma)

---

# A. Política de retención y borrado de datos

**PLANTILLA — requiere revisión legal antes de usar; no constituye asesoría legal.**

## A.1 Objeto y alcance

Esta política describe qué datos genera y almacena la plataforma de bots de la Agencia, durante cuánto tiempo, y cómo se eliminan o purgan. Aplica a todos los clientes ("tenants") atendidos y a los canales WhatsApp, Telegram y webchat.

La plataforma es **multi-tenant**: cada dato se asocia a un `tenant_id` y las consultas están segmentadas por cliente. Un usuario de panel con `tenant_scope` solo accede a los datos de su cliente.

## A.2 Categorías de datos que se guardan

Con base en el esquema real de la plataforma (Postgres en producción; SQLite solo en desarrollo/pruebas):

| Categoría | Almacenamiento | Contenido | Datos personales |
|---|---|---|---|
| **Conversaciones** | Tabla `conversations` | `id`, `tenant_id`, canal (`whatsapp`/`telegram`/`webchat`), `user_ref`, estado, fechas de inicio/actualización | El `user_ref` puede derivar del identificador del canal (p. ej. número de WhatsApp `wa:<msisdn>` o `tg:<chat_id>`) |
| **Mensajes** | Tabla `messages` | Rol (`user`/`assistant`/otros), contenido textual del mensaje, fecha | Contenido libre del usuario final; puede incluir datos personales según lo que escriba |
| **Consumo / uso (usage)** | Tabla `usage_events` | `tenant_id`, `conversation_id`, proveedor y modelo LLM, tokens de entrada/salida, costo estimado, fecha | Vinculable a una conversación; no contiene el texto del mensaje |
| **Auditoría** | Tabla `audit_events` | Actor (email del operador del panel), acción, recurso, metadatos, fecha | Datos del personal de la Agencia/Cliente que administra el sistema |
| **Citas / agendamientos** | Tabla `appointments` | Nombre del paciente/cliente, documento de identidad, especialidad, fecha programada, estado, metadatos | Datos personales directos (nombre, documento) en verticales que usan agendamiento |
| **Rotación de secretos** | Tabla `secret_rotations` | Actor, ruta del secreto, nombre de variable de entorno, nota, fecha | No contiene el valor del secreto; solo la referencia |
| **Configuración de tenant** | Tabla `tenants` (o `config/tenants.json` en local) | Nombre, vertical, prompt del sistema, referencias a secretos (`*_env`), conectores | Configuración; los secretos no se guardan en claro (ver A.6) |

> **Nota sobre audio (WhatsApp):** los mensajes de voz entrantes se transcriben a texto (servicio de transcripción compatible OpenAI/Whisper). El audio original **no se persiste** en las tablas de la plataforma; se procesa para obtener el texto, que sí queda como `message`. Confirmar retención del audio en el proveedor de transcripción y en Meta.

> **Datos en tránsito por terceros:** parte del contenido se envía a subencargados para poder funcionar (proveedor LLM, Meta/WhatsApp, Telegram, transcripción de voz, conectores externos configurados por tenant). Ver lista en el Anexo y en B.6.

## A.3 Plazos de retención sugeridos

**PLANTILLA — plazos referenciales; ajustar por contrato y por exigencia legal/sectorial del Cliente.**

| Dato | Plazo sugerido | Criterio |
|---|---|---|
| Mensajes y conversaciones | 12 meses desde el último mensaje | Soporte, continuidad conversacional y calidad; reducir si el Cliente lo exige |
| Registros de uso (`usage_events`) | 24 meses | Facturación, conciliación de costos y márgenes |
| Auditoría (`audit_events`) | 24 meses (o el mayor plazo legal aplicable) | Trazabilidad de seguridad y cumplimiento |
| Citas (`appointments`) | Según finalidad del Cliente; sugerido 24 meses | En salud u otros sectores regulados puede exigirse un plazo específico |
| Rotación de secretos (`secret_rotations`) | Vida del contrato + 12 meses | Evidencia de higiene de credenciales |
| Backups | Rotación de 30 días (o la definida en el contrato) | Recuperación ante desastres; ver A.5 |

Cumplido el plazo, los datos se anonimizan o eliminan salvo obligación legal de conservación o litigio en curso.

## A.4 Cómo se borra / purga

La plataforma no incluye hoy un endpoint de "borrado por usuario final" automatizado; el borrado se ejecuta de forma operada por la Agencia. Procedimientos disponibles:

- **Suspender un cliente (pausa lógica):** deja de operar el bot sin borrar datos.
  - `POST /api/admin/tenants/{tenant_id}/pause` (reanudar con `/resume`).
- **Purga selectiva por SQL** contra la base (segmentando siempre por `tenant_id`, y por `conversation_id`/`user_ref` cuando aplica a un titular concreto), sobre las tablas `messages`, `conversations`, `usage_events`, `appointments`. Registrar la operación como evento de auditoría.
- **Eliminación de configuración/secretos:** rotar o retirar las referencias de secretos del tenant (`POST /api/admin/tenants/{tenant_id}/secrets`) y, en su caso, retirar el tenant de la fuente de configuración (tabla `tenants` o `config/tenants.json`).
- **Backups:** los backups se generan y restauran con `backend/backup.py` (`create` / `list` / `restore --yes`); en Postgres usa `pg_dump`/`pg_restore`. La purga de un titular debe contemplar que los datos pueden persistir en backups hasta que estos expiren por rotación (ver A.5).

> **Recomendación:** definir e implementar una rutina periódica de purga (job programado) que aplique los plazos de A.3 automáticamente, y documentar cada borrado atendiendo a solicitudes de titulares.

## A.5 Backups y su ciclo de vida

- Backups cifrados y almacenados con acceso restringido.
- Rotación sugerida: conservar 30 días y eliminar los más antiguos.
- Ante una solicitud de borrado de un titular: se elimina de la base productiva de inmediato y se hace constar que la eliminación en backups se completa al expirar el backup correspondiente (documentar el plazo máximo).

## A.6 Seguridad de secretos y credenciales

- En producción **está prohibido guardar secretos en claro** en la configuración del tenant: la plataforma rechaza (HTTP 422) valores directos como `api_key`, `token`, `bot_token`, `secret_token` y exige **referencias por variable de entorno** (`*_env`), p. ej. `whatsapp.token_env`, `whatsapp.phone_number_id_env`, `telegram.bot_token_env`, `telegram.secret_token_env`, `llm.api_key_env`.
- Toda rotación de referencia de secreto queda registrada (`secret_rotations`) y consultable en `GET /api/admin/tenants/{tenant_id}/secrets/rotations`.
- Autenticación de webhooks: WhatsApp valida la firma `X-Hub-Signature-256` (con `META_APP_SECRET`) y el `WHATSAPP_VERIFY_TOKEN`; Telegram valida un secret token por tenant (`X-Telegram-Bot-Api-Secret-Token`).

## A.7 Derechos del titular de los datos

El titular (usuario final) puede ejercer, ante el **responsable del tratamiento** (habitualmente el Cliente), los derechos de: **acceso, rectificación, cancelación/supresión, oposición** y, según la norma aplicable, **portabilidad** y **limitación**.

- Las solicitudes se canalizan al Cliente como responsable; la Agencia, como encargada, colabora ejecutando el acceso/rectificación/borrado técnico dentro de los plazos legales.
- Plazo de atención sugerido: dentro del plazo legal aplicable (verificar el vigente en la jurisdicción del Cliente).
- Canal de contacto y procedimiento: definir en el contrato (C) y en la política de privacidad (B).

---

# B. Política de privacidad y tratamiento de datos

**PLANTILLA — requiere revisión legal antes de usar; no constituye asesoría legal.**

> Esta plantilla es la que el **Cliente (responsable del tratamiento)** publica/entrega a sus usuarios finales. La Agencia figura como **encargada del tratamiento**. Completar los campos entre corchetes.

## B.1 Identificación del responsable

- **Responsable del tratamiento:** [Razón social del Cliente], [RUC/identificación fiscal], [domicilio], [correo de contacto de privacidad].
- **Encargado del tratamiento:** [Razón social de la Agencia], que opera la plataforma de bots por cuenta e instrucción del Responsable.
- **Delegado/contacto de protección de datos (si aplica):** [nombre y contacto].

## B.2 Datos que se recogen

- **Identificadores de canal:** número de WhatsApp, `chat_id` de Telegram o identificador de sesión web.
- **Contenido de las conversaciones:** mensajes de texto que el usuario envía y las respuestas del asistente; los mensajes de voz de WhatsApp se transcriben a texto.
- **Datos que el usuario proporcione voluntariamente** en la conversación (p. ej. nombre, documento de identidad, datos de una cita/operación).
- **Metadatos de uso técnico:** marcas de tiempo, modelo/proveedor de IA usado y consumo asociado (para facturación y calidad).

No se recaban categorías especiales de datos salvo que la finalidad del Cliente lo requiera y exista base legal; en ese caso se informará específicamente.

## B.3 Finalidades del tratamiento

- Atender consultas y prestar el servicio de atención automatizada por chat.
- Gestionar agendamientos, cotizaciones u operaciones propias de la vertical del Cliente.
- Derivar la conversación a un asesor humano cuando el usuario lo solicite (handoff).
- Facturación, medición de consumo, seguridad, auditoría y mejora del servicio.

## B.4 Base legal / consentimiento

El tratamiento se ampara en [el consentimiento del titular / la ejecución de una relación contractual o precontractual / el interés legítimo / obligación legal], según corresponda a cada finalidad y a la norma aplicable. Al iniciar una conversación con el bot, se informará al usuario del tratamiento y, cuando la norma lo exija, se recabará su consentimiento.

## B.5 Decisiones automatizadas e IA

El servicio usa modelos de lenguaje (IA) para generar respuestas. Estas respuestas son orientativas y pueden contener imprecisiones; no sustituyen asesoría profesional. Cuando existan efectos jurídicos o significativos, se ofrecerá intervención humana (handoff a un asesor).

## B.6 Encargados y subencargados (terceros)

Para prestar el servicio, los datos pueden ser tratados por los siguientes tipos de proveedores (subencargados), cada uno con su propia política y ubicación:

- **Meta Platforms (WhatsApp Cloud API)** — envío y recepción de mensajes de WhatsApp.
- **Telegram** — envío y recepción de mensajes de Telegram.
- **Proveedor(es) de modelos de lenguaje (LLM)** — generación de respuestas (p. ej. el proveedor configurado por tenant; por defecto compatible con API tipo OpenAI/DeepSeek).
- **Proveedor de transcripción de voz** — conversión de audios de WhatsApp a texto (servicio compatible OpenAI/Whisper).
- **Proveedor de infraestructura/hosting** — [detallar: base de datos Postgres, Redis, servidor].
- **Conectores/API externas** configurados por el Cliente para su caso de uso (ERP, calendario, etc.).

Completar la lista con nombres, roles y país de tratamiento de cada proveedor. Algunos implican **transferencia internacional de datos**; informar y adoptar garantías conforme a la norma aplicable.

## B.7 Conservación

Los plazos de conservación se detallan en la Política de retención y borrado (sección A). En resumen: conversaciones/mensajes [12 meses], uso [24 meses], auditoría [24 meses], citas [según finalidad].

## B.8 Derechos del titular

El titular puede ejercer acceso, rectificación, cancelación/supresión, oposición y, según la norma, portabilidad y limitación, escribiendo a [correo de privacidad del Responsable]. Se responderá dentro del plazo legal. Tiene además derecho a presentar reclamo ante la autoridad de protección de datos competente (en Perú, la ANPDP).

## B.9 Seguridad

Se aplican medidas técnicas y organizativas razonables: segmentación multi-tenant por `tenant_id`, control de acceso por roles y tokens, secretos gestionados por referencia (no en claro), validación de firma en webhooks, límites de tasa, auditoría de acciones y backups.

## B.10 Cambios y contacto

Esta política puede actualizarse; la versión vigente estará disponible en [URL]. Consultas: [correo de contacto]. Última actualización: [fecha].

---

# C. Contrato base de servicio

**PLANTILLA — requiere revisión legal antes de usar; no constituye asesoría legal.**

**CONTRATO DE PRESTACIÓN DE SERVICIOS DE ASISTENTES CONVERSACIONALES (BOTS)**

Conste por el presente documento el contrato que celebran:

- **EL PROVEEDOR:** [Razón social de la Agencia], con [RUC], domicilio en [dirección], representada por [nombre], en adelante "la Agencia".
- **EL CLIENTE:** [Razón social], con [RUC], domicilio en [dirección], representada por [nombre], en adelante "el Cliente".

## C.1 Objeto

La Agencia presta al Cliente un servicio de operación de asistentes conversacionales (bots) sobre los canales WhatsApp, Telegram y/o webchat, incluyendo configuración del tenant, integración de canales, uso de modelos de IA, panel de gestión y soporte, según el alcance del Anexo de servicio.

## C.2 Alcance del servicio

- Alta y configuración del cliente ("tenant") en la plataforma multi-tenant.
- Integración de canales: WhatsApp Cloud API (Meta), Telegram y/o webchat.
- Configuración del comportamiento del bot (prompt del sistema, idiomas, conectores a APIs del Cliente, plantillas de WhatsApp).
- Derivación a asesor humano (handoff) según reglas acordadas.
- Panel de gestión con consumo, conversaciones y auditoría; suspensión/reactivación del servicio a solicitud.
- Backups y continuidad operativa.

## C.3 Roles en protección de datos

El **Cliente es el responsable del tratamiento** de los datos personales de los usuarios finales; la **Agencia es la encargada del tratamiento** y solo trata los datos por instrucción documentada del Cliente y para las finalidades del servicio. Las partes suscriben el **Acuerdo de Encargo de Tratamiento (Anexo de Datos)** que forma parte integrante de este contrato y regula: finalidades, categorías de datos, subencargados, medidas de seguridad, asistencia en derechos de titulares, notificación de brechas y devolución/borrado al término.

## C.4 Obligaciones de la Agencia

- Prestar el servicio con diligencia y disponibilidad razonable.
- Tratar los datos solo según instrucciones del Cliente y la normativa aplicable.
- Guardar confidencialidad y aplicar medidas de seguridad (ver sección A.6 y B.9).
- No guardar secretos en claro; gestionarlos por referencia y registrar rotaciones.
- Colaborar en la atención de derechos de titulares y en la notificación de incidentes de seguridad **sin dilación indebida** tras conocerlos.
- Informar de subencargados y no incorporar nuevos sin comunicación previa al Cliente.

## C.5 Obligaciones del Cliente

- Aportar información veraz y contar con base legal/consentimiento para el tratamiento.
- Publicar su política de privacidad e informar a los usuarios finales.
- Custodiar sus credenciales de acceso al panel y las de sus integraciones.
- Usar el servicio conforme a las políticas de WhatsApp/Meta y Telegram y a la ley (no spam, no usos prohibidos).
- Pagar la retribución pactada.

## C.6 Retribución y facturación

- Tarifa mensual por tenant (`fee`) de USD [monto], más [consumo variable de IA / cargos por canal] según el consumo medido por la plataforma (`usage_events`).
- Periodicidad de facturación: [mensual]. Forma de pago: [detallar]. Moneda: [USD/PEN].
- Los costos de terceros (Meta/WhatsApp, proveedor de IA, transcripción, etc.) se [incluyen / trasladan] según [detallar].

## C.7 Nivel de servicio y soporte

- Disponibilidad objetivo: [ej. 99% mensual], excluyendo mantenimientos programados y fallas de terceros (Meta, Telegram, proveedor de IA).
- Soporte: [canal y horario], tiempo de respuesta objetivo [detallar].
- Limitaciones de la IA: las respuestas son generadas automáticamente y pueden contener errores; el Cliente asume la supervisión de contenidos sensibles y la configuración del handoff.

## C.8 Confidencialidad

Cada parte mantendrá en reserva la información confidencial de la otra durante la vigencia y por [X años] posteriores a su término.

## C.9 Propiedad intelectual

La plataforma, su código y configuraciones de la Agencia son de su titularidad. Los datos y contenidos del Cliente y de sus usuarios finales son del Cliente. El Cliente otorga a la Agencia una licencia limitada para tratarlos con el fin de prestar el servicio.

## C.10 Retención, devolución y borrado

Al término del contrato, la Agencia, a elección del Cliente, devolverá o eliminará los datos personales tratados, salvo obligación legal de conservación, conforme a la Política de retención (sección A), incluyendo la expiración en backups. Se emitirá constancia de borrado si el Cliente lo solicita.

## C.11 Responsabilidad

La responsabilidad de la Agencia se limita a [ej. el importe facturado en los últimos N meses]. La Agencia no responde por fallas, cambios de política o suspensiones de terceros (Meta/WhatsApp, Telegram, proveedores de IA), ni por usos indebidos del Cliente o de sus usuarios.

## C.12 Vigencia y terminación

- Plazo: [inicial de N meses, renovable]. Preaviso de terminación: [30 días].
- Terminación por incumplimiento con subsanación previa de [15 días].

## C.13 Ley aplicable y solución de controversias

Este contrato se rige por las leyes de [país]. Las controversias se someterán a [arbitraje/juzgados de la ciudad de ___]. En materia de datos personales aplica la normativa vigente ([Ley 29733 y su reglamento en Perú], o equivalente).

## C.14 Anexos

- **Anexo A:** Alcance de servicio y precios.
- **Anexo B:** Acuerdo de Encargo de Tratamiento de Datos (roles, subencargados, medidas de seguridad).
- **Anexo C:** Datos de contacto técnico y de privacidad.

Firmado en [ciudad], a [fecha].

_____________________  _____________________
Por la Agencia         Por el Cliente

---

# Anexo técnico: qué se guarda realmente en la plataforma

Resumen fiel a la implementación, útil para completar A, B y C:

- **Base de datos:** Postgres en producción (SQLite solo en desarrollo/pruebas). Redis para colas y runtime.
- **Tablas:** `conversations`, `messages`, `usage_events`, `audit_events`, `tenants`, `channel_configs`, `connector_configs`, `appointments`, `secret_rotations` (más `panel_users` para acceso al panel).
- **Identificadores de usuario final:** `user_ref` con prefijo por canal (`wa:` WhatsApp, `tg:` Telegram, `webchat-visitor` u otro por webchat).
- **Canales y su seguridad:**
  - WhatsApp Cloud API: verificación de webhook con `WHATSAPP_VERIFY_TOKEN` y validación de firma `X-Hub-Signature-256` usando `META_APP_SECRET` (`WHATSAPP_REQUIRE_SIGNATURE=true`). Resolución de tenant por `phone_number_id`.
  - Telegram: webhook por URL `/telegram/webhook/{tenant_id}` con secret token por tenant (`X-Telegram-Bot-Api-Secret-Token`).
- **Secretos:** siempre por referencia `*_env` en producción (la API rechaza secretos en claro con HTTP 422). Rotaciones auditadas en `secret_rotations`.
- **Audio (WhatsApp):** transcrito a texto vía servicio compatible OpenAI/Whisper; el texto se guarda como mensaje, el audio original no se persiste en la plataforma.
- **Endpoints administrativos relevantes:** `POST/PATCH /api/admin/tenants`, `/pause`, `/resume`, `/secrets`, `GET /api/admin/tenants/{id}/usage`, `GET /api/admin/tenants/{id}/secrets/rotations`; operación en `/api/ops/metrics`, `/api/ops/alerts`, `/api/ops/dead-letter`.
- **CLI y respaldo:** `backend/manage.py` (`init`, `migrate`, `create-admin`, `list-users`, `list-tenants`); `backend/backup.py` (`create`, `list`, `restore --yes`; Postgres vía `pg_dump`/`pg_restore`). Migraciones con Alembic (`manage.py migrate`).
