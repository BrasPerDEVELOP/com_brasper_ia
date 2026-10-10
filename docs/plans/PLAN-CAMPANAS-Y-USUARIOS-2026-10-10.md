# Plan de campañas y gestión de usuarios de Brasper IA

Estado: implementado en IA el 10 de octubre (ver «Estado de implementación» al final); pendiente de validación en infraestructura real y de la confirmación del procedimiento de registro en Brasper. Este documento no activa campañas ni cambia producción.

Este es el plan prioritario para campañas y usuarios. Sustituye cualquier instrucción contradictoria sobre esas capacidades en planes anteriores y en el prompt de desarrollo. Hay commits y cambios locales en la API principal que siguen el diseño anterior: deben inventariarse y separarse de identidad/correcciones financieras, sin revertirlos automáticamente. La actualización del documento no implica que el código ya haya migrado al nuevo diseño.

## Restricción obligatoria y criterio de finalización

La implementación de capacidades se ejecuta exclusivamente en `com_brasper_ia`. No agregar capacidades de campañas a `com_brasper_api`, al portal ni al backoffice financiero. Se añade abajo un trabajo separado de retirada selectiva del diseño anterior de campañas en la API principal; no es autorización para reescribir funciones ajenas ni desplegar ese proyecto. El humano verifica el depósito y genera la transacción financiera. La IA prepara cotización, consentimiento, datos y comprobante para ese humano; no confirmar pago ni generar automáticamente la transacción como parte de este alcance.

## Revisión actual del código: pendientes para terminar

La revisión local del 10 de octubre encontró campañas persistidas en IA, usuarios con contraseñas/sesiones y expedientes en el commit `5e33bed`. Se ejecutó la suite aislada `backend/tests/run_checks.py`: **79/79 pasaron**. Esto no demuestra cumplimiento completo: se identificaron los pendientes siguientes. No desplegar como terminado antes de resolverlos y verificar el panel.

### P1. Migración de tabla de ofertas anterior — fallo reproducido

- `0013_ia_campaigns.py` y `campaign_offers.ensure_schema()` solo hacen `CREATE TABLE IF NOT EXISTS`. Si existe la tabla de ofertas de ocho columnas del diseño previo, no agregan `delivery_key`, `state`, `updated_at`.
- Reproducción en SQLite aislada con esquema anterior: después de aplicar los DDL de la migración faltan esas tres columnas; el INSERT del código nuevo falla por ausencia de `delivery_key`.
- Añadir migración aditiva real que inspeccione y agregue columnas faltantes, sin borrar ofertas ni modificar versiones ya aplicadas. Verificar si 0013 ya fue aplicada en algún entorno antes de elegir reparación/0014.
- Definir backfill de estado/clave para ofertas antiguas sin reenviarlas. Ensayar datos anteriores en SQLite y Postgres y luego operación real del repositorio de ofertas. No basta crear una base vacía.

### P2. Reserva ligada a cotización y expediente

- `campaigns.reserve()` recibe campaña, conversación y referencia; valida segmento/cupo/vigencia, pero no valida ruta, monto, topes ni snapshot aceptado. Además usa la versión publicada actual, no necesariamente la aceptada por el cliente.
- Requerir expediente/cotización identificados y versión inmutable, comprobar ruta/monto/elegibilidad y conservar desglose de comisión/descuento. Impedir reservar una campaña distinta o una versión no aceptada.
- Registrar evidencia de verificación humana cuando sustituya datos insuficientes; no permitir que un booleano sin detalle sea la única evidencia de comprobación.
- Añadir pruebas de ruta incompatible, monto fuera de límites, versión republicada, cotización vencida y campaña que no coincide con el expediente; todas deben rechazarse o exigir nueva aceptación explícita.
- Comprobar consumo/cancelación ligados al estado correcto de operación con acción humana auditada; no equiparar confirmación de depósito a envío completado.

### P3. Snapshot y promoción obsoleta

- `cases.quote_snapshot()` guarda ruta, importes, tasa y cupón, pero no el desglose completo de comisión. Añadir comisión original/final y descuento de campaña, y pruebas de conservación hasta revisión humana.
- En `agent_graph.py`, verificar que una nueva cotización sin campaña borre un `campaign_estimate` previo. Actualmente se escribe cuando hay campaña; impedir que un expediente nuevo herede una oferta anterior incompatible.
- Comprobar que dos aceptaciones simultáneas y dos adjuntos concurrentes no creen expedientes duplicados ni pierdan comprobantes; probar con Postgres, no solo secuencia SQLite.
- `for_quote()` usa orden de prioridad/porcentaje; definir selección final por ahorro efectivo después de topes si se mantiene la propuesta del plan, o documentar regla de prioridad comercial y probarla.

### P4. Integración y publicación pendientes

- Probar UI completa de usuarios/campañas/expediente, typecheck/build y migración con históricos.
- Confirmar contratos existentes de clientes/historial y procedimiento manual que permite aplicar descuento; no resolver faltantes agregando funciones financieras.
- Verificar reserva concurrente y cupos con Postgres/Redis reales, además de la suite local.
- Ensayar cambio de credenciales owner y reversión; no publicar sin acceso verificado.

## Retirada selectiva del diseño anterior en la API principal

Este es un pendiente de limpieza solicitado por el usuario para que campañas quede exclusivamente en IA. No se ejecutó durante esta revisión. No borrar commits completos: hay cambios mezclados de identidad, autenticación e integridad financiera.

1. Inventariar el diff de campañas introducido por `c750b6a` y cambios locales posteriores. Comparar contra el estado anterior; guardar un parche de trabajo y preservar cambios ajenos. El commit de precisión `2f182ab` contiene correcciones que no deben perderse indiscriminadamente.
2. Candidatos de retirada exclusiva: rutas nuevas de administración/publicación/reserva de campañas en `app/modules/brasper/adapters/router/campaign_routes.py`, servicio `application/campaign_service.py`, esquemas `transactions/application/schemas/campaign_schema.py`, registro del router, pruebas específicas de esas rutas y documentación/secretos exclusivamente dedicados a ellas. Buscar consumidores antes de quitar archivos completos.
3. `ai_routes.py`, `ai_service.py`, `campaign_quote.py`, modelos/casos de uso de cupones y transacciones son mixtos: retirar solo conexiones y reglas añadidas para campañas IA; preservar el comportamiento de cupones previo y correcciones de importes. Elaborar diff revisable por función.
4. Preservar vinculación/consulta de identidad, autenticación y correcciones independientes salvo que el usuario cambie expresamente su alcance. No eliminar endpoints ya usados para consultar clientes.
5. No borrar migración 083 ni hacer downgrade/drop de tablas/columnas sin comprobar si se aplicó o contiene datos. En esta tarea no se modifica la base de producción. Si no se aplicó y no es requerida por capacidades conservadas, documentar retirada local de la migración y ajustar cadena solo tras comprobar dependencias. Si se aplicó, conservar historial y preparar estrategia aparte; no borrar datos financieros.
6. Pruebas financieras existentes deben seguir pasando, incluida coherencia de redondeo/cupones tradicionales. Pruebas exclusivas de campañas retiradas se eliminan o trasladan a IA según corresponda; no borrar tests para ocultar regresiones.
7. Entregar lista de funciones retiradas, conservadas y dependencias restantes. No hacer push, deploy, reset de Git ni eliminación de datos como efecto automático de esta limpieza. No añadir ninguna capacidad nueva a la API principal.

Esta sección sustituye la prohibición absoluta de edición para permitir únicamente la retirada selectiva descrita. El resto de la API principal sigue fuera del alcance; las menciones anteriores a solo lectura significan no desarrollar campañas allí, con esta excepción de limpieza local.

Finalizado significa código, migración y pruebas completas en IA, no solo actualización del documento. Una imposibilidad de obtener identidad/historial con las APIs existentes debe quedar visible como limitación, nunca solucionarse silenciosamente editando Brasper.

## Orden de ejecución y archivos concretos

### A. Inventario antes de editar

1. Registrar estado Git, cambios sin commit y contratos consumidos; preservar trabajo simultáneo. En esta revisión ya hay modificaciones locales de usuarios y campañas: inspeccionarlas antes de rehacer funciones.
2. Leer `backend/api/campaigns.py`, `backend/core/campaign_offers.py`, `backend/core/brasper_api.py`, `backend/core/quotes.py`, `backend/core/agent_graph.py`, `backend/core/media_library.py`, `backend/core/auth.py`, `backend/api/access.py`, `backend/core/engagement.py`, `backend/core/db.py` y las migraciones existentes.
3. Revisar `web/app/promociones/page.tsx`, `web/app/accesos/page.tsx`, componentes de sesión y bandeja. Leer instrucciones de `web/AGENTS.md` antes de editar web.
4. Inventariar endpoints de clientes, tasas, comisiones, cuentas e historial ya disponibles en la API desplegada. No tomar un endpoint nuevo del código local de Brasper como evidencia de que existe en producción. No usar búsquedas ambiguas por nombre para autorizar beneficios ni exponer historial por un teléfono no verificado.

### B. Lo que se elimina o sustituye SOLO en IA

| Elemento actual | Cambio requerido |
| --- | --- |
| `backend/api/campaigns.py`: función `upstream` y llamadas de administración a `/brasper/ai/admin/campaigns` | Sustituir por servicio/repositorio local IA; conservar URL pública del panel si facilita compatibilidad. |
| Ruta IA `/api/admin/campaigns/routes` delegada a ese proxy | Obtener rutas desde contratos existentes de tipos de cambio; no crear endpoint financiero nuevo. |
| `backend/core/brasper_api.py`: `active_campaigns` que consulta `/brasper/ai/campaigns/active` | Retirar esa dependencia; leer campañas publicadas en la base IA. |
| `backend/core/campaign_offers.py`: carga y caché de campañas oficiales financieras | Sustituir por catálogo local con invalidación al publicar/desactivar; actualizar docstrings que atribuyen reserva a Brasper. |
| Cotización personalizada dependiente de endpoints nuevos para reglas de campaña | Desacoplar campañas de esa llamada; usar tasa/comisión existentes y cálculo determinista IA. No retirar usos de identidad/estado ajenos sin analizar dependencias. |
| Formulario que exige código de cupón, pareja única o límite individual editable en primer envío | Reemplazar por nombre, ID interno generado, rutas múltiples/todas y límite individual fijo en uno. |
| Secretos de administración financiera usados únicamente por campañas | Eliminar esa necesidad de configuración; no borrar una variable que otro módulo todavía use. |
| Pruebas/documentación que exigen migraciones de campañas en Brasper | Reemplazar expectativas por persistencia y migración IA. Mantener pruebas de capacidades no relacionadas. |

No borrar `quotes.py`, `brasper_api.py`, biblioteca, contactos, auditoría o identidad completos. No ejecutar migraciones 083/084 de la API principal como requisito de este plan. Los commits mixtos ya existentes en Brasper no se revierten aquí; quedan fuera del despliegue. No hay autorización para eliminar datos o chats reales.

### C. Persistencia propia de campañas

Crear servicio/repositorio local (por ejemplo `backend/core/campaigns.py`) y una migración siguiente al último número real, sin modificar migraciones aplicadas. Usar Postgres en producción y compatibilidad SQLite para pruebas.

- Campaña: ID, nombre, estado, versión actual/publicada, autor y fechas.
- Versiones inmutables: porcentaje Decimal, segmento, vigencia con zona horaria, rutas, límites, importes mínimo/máximo/tope de descuento y mensajes/medios ES/PT.
- Oferta: identidad de contacto, versión, conversación, idioma y clave de entrega; reutilizar/migrar tabla `campaign_offers` sin perder registros existentes.
- Reserva: identificador estable de persona verificada, campaña/version, cotización/expediente, estado, importes y fechas. Estados explícitos reservado, consumido, liberado y vencido, con historial de transiciones.
- Restricción única y transacción/lock para impedir dos reservas simultáneas del primer envío de una misma persona, incluso en campañas diferentes. No vincular el derecho únicamente al ID del chat.
- Cupos calculados incluyendo reservas vigentes y consumos, nunca con lectura y escritura separadas sin bloqueo.
- Publicar copia una versión validada; editar crea borrador y no altera ofertas o cotizaciones aceptadas. Desactivar impide nuevas ofertas/reservas; definir tratamiento visible de reservas previas, sin borrar su historial.
- No importar automáticamente datos de la base financiera. Si existen campañas que deben conservarse, preparar importación explícita y de solo lectura con informe; no asumir que están vacías.

### D. Contrato y formulario del panel

- Tipar entradas y rechazar campos desconocidos. Nombre obligatorio; ID interno no editable. Porcentaje 1–100 y máximo dos decimales, aplicado a la comisión.
- Ruta: modo todas las habilitadas o selección múltiple de pares dirigidos; impedir combinación inválida. Definir que modo todas se evalúa contra rutas habilitadas en la cotización, mostrar esa semántica al operador.
- Primer envío: límite individual uno, bloqueado en UI y servidor. Cupo global independiente: añadir modo sin límite o límite positivo como propuesta de producto a validar, nunca transformar uno por persona en uno total.
- Otros segmentos: límites individuales configurables y valores explícitos. Mantener mínimo/máximo y tope de descuento, dejando claro si están expresados en moneda de origen por ruta. Para campañas multimoneda no interpretar una cifra igual en monedas distintas: configurar por moneda/ruta o exigir límites vacíos hasta elegir una sola moneda de origen.
- ES/PT: texto no vacío para publicar y selección de imagen aprobada del mismo idioma. Imagen opcional si el operador elige solo texto. Vista previa de ambas versiones y condiciones.
- Acciones guardar borrador, publicar/activar, desactivar e historial. Confirmación de versión esperada; cambios concurrentes devuelven conflicto y piden recarga sin sobrescribir.
- Errores de rutas/identidad se explican al operador; no mostrar caída de API financiera de campañas cuando la base local funciona.

### E. Cotización y elegibilidad

- Tasas, comisiones y cuentas proceden de APIs existentes; nada inventado por el LLM ni tasas locales de respaldo.
- Cálculo de campaña en IA con Decimal y reglas explícitas de redondeo. Guardar comisión original, descuento, comisión final, tipo de cambio, monto enviado/recibido, ruta, versión y caducidad.
- Identidad no verificada o historial incompleto: solo promoción condicional, sin confirmar ni reservar descuento personal. La verificación debe usar medios ya existentes o revisión humana registrada; no exigir construir enlaces/grants nuevos en Brasper.
- Elegibilidad primer envío: cero completados verificados más ausencia de beneficio consumido/reservado local. Cliente existente no significa cliente recurrente; cliente no encontrado no significa elegible automáticamente.
- Historial puede variar fuera de IA: comprobar de nuevo antes de reservar/aceptar y explicar que no puede garantizarse exclusividad global si Brasper no expone el dato necesario.
- Definir prioridad determinista para campañas coincidentes: una por cotización, no sumar descuentos; propuesta mayor ahorro válido y desempate estable, documentada y probada.
- Aceptación explícita sobre snapshot vigente; no mantener reserva eterna. Si cambian importes o vence, volver a cotizar y aceptar.
- El descuento IA es una propuesta para la transacción que genera el humano: verificar que el procedimiento existente permite respetar el importe. Si no, impedir prometer un descuento aplicable y registrar el bloqueo; no editar Brasper para resolverlo.

### F. Envío de promoción y expediente humano

- Conservar selección de idioma y biblioteca existentes; elegir texto e imagen del mismo idioma. Preguntar solo cuando el idioma no sea conocido.
- Registrar oferta/delivery con estados preparado/enviado/incierto/fallido; no confundir registro previo al envío con entrega confirmada. Deduplicar por contacto/versión y revisar resultados inciertos.
- Publicar no manda mensajes masivos. Ofrecer en contexto de mensaje entrante; takeover humano impide mensajes del bot.
- Cotización aceptada crea expediente IA, no transacción financiera. Adjuntar los datos progresivamente sin pedir de nuevo los ya confirmados.
- Comprobante: validar formato/tamaño, almacenar con acceso restringido, enlazar al expediente y mostrar al asesor importe/ruta/cotización/promoción/cliente y pendientes. No extraer una confirmación de pago de la imagen.
- Asesor verifica dinero y genera transacción fuera de este cambio; registrar referencia oficial en IA cuando la tenga. Marcar reservado/consumido/liberado solo a partir de estados oficiales consultables o acción humana autorizada y auditada. Confirmar depósito no equivale a envío completado.
- No liberar una reserva pendiente por mera reapertura/cierre del chat. Vencimientos inciertos requieren conciliación para evitar consumo doble.

### G. Usuarios y seguimiento: completar lo existente

- Inspeccionar primero auth actual: ya aparecen funciones de hash de contraseña y sesiones en cambios locales; verificar rutas, UI, migración y pruebas antes de llamarlo pendiente o terminado.
- CRUD de usuarios con permiso owner, normalización de correo, roles válidos, alcance, desactivación y protección del último owner. Registrar actor; no devolver hashes/tokens.
- Contraseña individual, temporal con cambio obligatorio, sesiones revocables y rechazo de cuentas desactivadas. Migración owner ensayada sin exponer secretos ni bloquear acceso. Acotar y retirar compatibilidad con código compartido al completar transición.
- Seguimiento separado de campañas: validar consentimiento, estado, idioma, horarios, cancelación al responder/intervenir humano y deduplicación. La encuesta no consume el beneficio ni completa una transacción.

### H. Pruebas que permiten cerrar el trabajo

1. CRUD/publicación local sin llamadas a endpoints de campañas de Brasper ni escrituras en su API; test de adaptador que falle si se intentan.
2. Borrador no visible al bot, versión publicada inmutable, desactivación y conflictos de edición.
3. ES/PT, idioma desconocido, imagen aprobada/retirada, error de entrega, duplicados y reapertura.
4. Rutas múltiples/todas y moneda no habilitada; descuentos 1/100, límites, topes, bordes de comisión y redondeo; coherencia del snapshot aceptado.
5. Nuevo contacto sin identificar, cliente existente sin envíos, cliente recurrente y datos insuficientes; identidad entre canales y reservas concurrentes por persona.
6. Fallo/cancelación/liberación, pendiente aún reservado, completado consume una vez; transiciones repetidas idempotentes y conciliación de estados inciertos.
7. Comprobante privado, takeover humano y expediente completo; ningún pago confirmado ni transacción generada automáticamente.
8. Roles, último owner, cambio obligatorio de contraseña, cierre/revocación de sesión y filtros de conversación/medios.
9. Migración en copia aislada de datos, Postgres/Redis reales para concurrencia, checks existentes y build/typecheck web. No probar contra clientes reales.
10. Reporte de resultados y limitaciones. No afirmar completitud de integración si faltan APIs de historial o mecanismo financiero para el importe propuesto.

### I. Entrega y despliegue

- Entregar lista de archivos IA modificados, endpoints/contratos locales, migraciones, resultados y procedimiento owner/asesor.
- Verificar que el diff del trabajo no modifica ninguno de los otros repositorios. Sus cambios preexistentes se registran como tales, no se borran.
- Desplegar solo IA tras respaldo y ensayo; conservar variables de canales, biblioteca, datos y cuentas existentes. Preparar reversión compatible con esquema/sesiones.
- Validar panel, login, campañas locales, conversaciones y recepción del comprobante; mantener campañas desactivadas hasta validación explícita de condiciones y operación.
- Actualizar plan de código y prompt para que ningún agente siga el diseño anterior. Esta lista sustituye instrucciones contradictorias; no crear objetivos nuevos fuera de ella.

## 1. Campañas: experiencia deseada

- Crear una promoción con nombre, imagen y mensaje, sin obligar al operador a inventar un código de cupón. Generar un identificador interno único compatible con Brasper.
- Mantener guardar borrador para preparar cambios y ofrecer una acción clara de publicar/activar con resumen y validación. No ofrecer un borrador a los clientes.
- Configurar descuento de 1 a 100 por ciento sobre la comisión, con vigencia y condiciones visibles.
- Elegir todas las rutas disponibles o varias rutas específicas, por ejemplo PEN→BRL y BRL→PEN. Cargar rutas habilitadas desde Brasper; no asumir que cualquier combinación existe.
- Preparar mensaje e imagen por idioma: español y portugués. Seleccionar la versión con el idioma de la conversación; si es incierto, preguntar. No mezclar imágenes y textos de idiomas distintos.
- Permitir seleccionar imagen aprobada de la biblioteca y mostrar una vista previa de imagen, texto y condiciones antes de publicar.

## 2. Primer envío y clientes recurrentes

- La promoción de primer envío admite un único beneficio por persona. Este límite individual no es el límite total de clientes de la campaña.
- Basar elegibilidad en envíos completados de Brasper, no en ausencia de contacto en el chat o en la base de clientes.
- Reservar el beneficio mientras haya una operación pendiente; consumirlo al completar el envío y liberarlo si falla o se cancela.
- Evitar que campañas nuevas, cuentas duplicadas, distintos canales o solicitudes simultáneas permitan repetir un beneficio definido como único primer envío.
- Si el contacto no está identificado, mostrar la promoción como beneficio sujeto a comprobación; no afirmar elegibilidad ni aplicar descuento hasta comprobar identidad e historial.
- Para clientes recurrentes, permitir otras campañas con porcentaje, vigencia y límites configurables.
- Mantener el cupo total como configuración separada. Pendiente definir si se permite campaña sin cupo total; no fijarlo en uno para primer envío.

## 3. Envío por el bot

- Definir y probar el disparador de la oferta durante la conversación de bienvenida/primer envío.
- Enviar imagen más mensaje aprobado en el idioma correspondiente por el canal de origen.
- Registrar qué versión se ofreció y evitar repetir automáticamente la misma promoción en cada mensaje o reapertura.
- Respetar intervención humana y restricciones de envío del canal; no activar difusión masiva como efecto de publicar una campaña.
- Si falla la imagen, conservar un mensaje de texto coherente sin afirmar que la imagen se entregó. Resolver resultados inciertos sin duplicar envíos.

## 4. Reparto de responsabilidades

- Panel IA: creación, edición, vista previa, publicación y desactivación; nombre, textos, imágenes y selección de rutas.
- Backend y base de datos IA: almacenar campañas, versiones, reglas, elegibilidad, cupos, reservas, consumo y liberación; seleccionar idioma, enviar medios y controlar repetición y concurrencia.
- Corrección de alcance del usuario: toda la administración de campañas pertenece a la plataforma IA. No modificar la API financiera ni exigir gestionar campañas desde el otro panel.
- Consumir contratos existentes de Brasper para consultar clientes, historial, tasas, comisiones, rutas y estado de operaciones, según lo que realmente expongan. Ausencia de cliente no demuestra ausencia de envíos; ante información insuficiente no confirmar elegibilidad.
- Antes de implementar descuentos reales, verificar si los endpoints existentes admiten registrar la operación con el importe descontado de forma coherente. Si no lo admiten, documentar esa limitación: un cálculo local en IA no modifica por sí mismo el cobro financiero. No cambiar la otra API sin autorización.
- El beneficio de primer envío se controla entre los canales atendidos por IA. Comprobar si el historial existente permite detectar beneficios usados fuera de IA; no prometer exclusividad global si ese dato no está disponible.
- Sustituir la dependencia actual del proxy de campañas financieras por persistencia propia en IA, con migración explícita de datos y pruebas. Los campos texto/imagen ES/PT ya existen; conservar su capacidad.
- La integración actual en producción no funciona; este nuevo diseño aún debe implementarse y validarse. No marcar completo solo por tener formulario.

## 5. Gestión de usuarios pendiente

- Formulario para nombre, correo, rol y alcance por canal, conexión y sector.
- Crear, editar y desactivar cuentas; bloquear sesiones de cuentas desactivadas.
- Solo owner administra usuarios y roles. Proteger al último owner de desactivación o pérdida de privilegios.
- Sustituir el código compartido por credenciales individuales con almacenamiento seguro, cambio de contraseña y revocación de sesiones.
- Migrar la cuenta owner actual sin perder acceso; auditar cambios y comprobar restricciones en servidor.

## 6. Verificación y despliegue

- Probar oferta ES/PT con imagen, idioma incierto, ausencia de imagen, primer envío, cliente recurrente, contacto sin identificar y repetición de mensajes.
- Probar rutas múltiples/todas, vigencia, límites, reserva concurrente, cancelación, fallo y consumo único al completar.
- Confirmar que el importe cotizado y el registrado coinciden en la API financiera, incluyendo límites de tramos y redondeo.
- Probar roles, cuentas desactivadas, revocación y conservación del acceso owner.
- Validar primero en entorno aislado; respaldar datos y preparar reversión antes del despliegue autorizado.

## 7. Encuestas y seguimiento: comportamiento encontrado en código

- Configuración independiente de campañas: activación, encuestas, horario, días, zona horaria, canales, intervalos y máximo de recordatorios (0–3).
- Encuesta opcional tras cierre del chat: nota de 1 a 5 y comentario. Una por revisión de cierre; cerrar un chat no completa una operación financiera.
- Aviso de espera: conversación derivada a atención humana todavía sin asesor asignado.
- Recordatorio de inactividad: conversación activa para invitar a retomarla.
- Los envíos requieren consentimiento explícito registrado, horario y canal habilitados; también las encuestas pasan por esta comprobación en el código actual.
- Mensajes fijos ES/PT elegidos por el idioma guardado. Todavía no son un editor de campañas ni una personalización libre de mensajes.
- El worker procesa trabajos persistidos; suprime los que dejan de cumplir condiciones y no reintenta automáticamente entregas inciertas.
- Resultados del panel: cantidad de respuestas, nota promedio y estados de trabajos. El umbral de espera genera un evento de auditoría, no una notificación externa garantizada.
- Esta revisión describe código; no confirma que la configuración esté activada actualmente en producción ni certifica entrega real en todos los canales.

## Estado de implementación — 10 de octubre de 2026

Implementado solo en `com_brasper_ia`, sin commits ni despliegue. `com_brasper_api`, el portal y el backoffice no se modificaron; los cambios de la API ya existentes se inventariaron en [INVENTARIO-API-CAMPANAS-2026-10-10.md](INVENTARIO-API-CAMPANAS-2026-10-10.md). Nota: antes de leer la restricción de solo lectura se apartaron a la rama local `archivo/campanas-api-diseno-anterior` (sin push) cambios de campañas propios aún no commiteados en la API; `main` de la API no cambió.

| Bloque | Estado | Dónde / evidencia |
|---|---|---|
| A. Inventario | Hecho | Inventario de la API; contrato desplegado verificado en código (`8059ece`): `clients/lookup` (con `is_first_transfer` = sin transacciones), `clients/upsert`, `deposit-accounts`, tasas/comisiones/cupones públicos. `history`/`operations` solo existen en commits posteriores: se usan si responden, sin darlos por desplegados. |
| B. Sustituciones en IA | Hecho | `api/campaigns.py` sin proxy (persistencia local, mismas URL); rutas desde `/coin/tax-rate`; `brasper_api.active_campaigns` retirado; `campaign_offers` lee la base IA; la cotización ya no usa `/brasper/ai/quotes`; el formulario sin código obligatorio. `BRASPER_IA_ADMIN_SECRET` solo se usa para la importación opcional. |
| C. Persistencia | Hecho | `core/campaigns.py` + migración `0013_ia_campaigns`: campañas, versiones inmutables, beneficios reservado/consumido/liberado/vencido con historial (`campaign_benefit_events`), `first_transfer_claims` (cliente Brasper, contacto y documento; únicos entre campañas), cupo global opcional con actualización condicional, límite por persona. Importación explícita `manage.py import-campaigns` (solo lectura, informe, como borrador). |
| D. Panel | Hecho | `/promociones`: nombre, ID interno, 1–100 % con dos decimales, todas/varias rutas habilitadas, primer envío = 1 por persona bloqueado, cupo global con opción «sin límite» (propuesta a validar), límites vacíos con varias monedas de origen, ES/PT con imagen del mismo idioma, vista previa, publicación con resumen/validación, conflicto de versión. Campos desconocidos rechazados (422). |
| E. Cotización y elegibilidad | Hecho con límite | Elegibilidad solo con identidad verificada por canal + dato Brasper (historial verificado o «sin transacciones»), más ausencia de reclamo local. Cálculo `Decimal` ROUND_HALF_UP, una campaña por cotización (prioridad, mayor ahorro, desempate estable) y solo si supera el cupón público. **Límite:** no se verificó que el procedimiento humano en Brasper respete un importe con descuento IA (el registro aplica solo cupones propios de Brasper), por eso `campaigns.discount_applicable` viene en `false`: el bot anuncia la promoción como pendiente de confirmar por el asesor, sin prometer el ahorro, y registra `campaign.discount_not_applicable`. |
| F. Oferta y expediente | Hecho | Oferta en la bienvenida: idioma con evidencia o pregunta única (la respuesta no se toma como dato del onboarding), texto+imagen del mismo idioma, «sujeto a comprobación», registro por contacto/versión con estado preparado→enviado/solo texto/fallido/incierto, sin reenvíos. Expediente (`core/cases.py`): aceptación al pasar al pago solo sobre cotización vigente, comprobantes enlazados (sin confirmar pago), referencia oficial registrada por el asesor, cierre del chat no cambia nada. Reserva/consumo/liberación/vencimiento solo por acción humana auditada desde la ficha. |
| G. Usuarios | Hecho | `core/users.py`, `api/users.py`, migración `0012`, `/usuarios`, `/cuenta`: contraseñas scrypt, temporales con cambio obligatorio, sesiones con hash/vencimiento/revocación, desactivación inmediata, solo owner, último owner protegido (concurrente), compatibilidad acotada con el código compartido (RUNBOOK §1.5). |
| H. Pruebas | Hecho salvo infraestructura real | `run_checks` 79/79 (64, 76–79 nuevos o adaptados), evals 57/57, doctests, migración SQLite 0006→0013, `tsc` y `next build`, revisión visual local de `/promociones` (guardar, publicar, desactivar) y `/usuarios`. **Pendiente:** concurrencia en PostgreSQL 16 multisesión, Redis real y migración sobre copia de datos reales. |
| I. Entrega | Preparado | Desplegar solo IA tras backup; flag `campaigns` apagado hasta validar condiciones y procedimiento; ver RUNBOOK §9.9. |

Pendientes que no se resuelven en IA: confirmación del responsable de Brasper sobre cómo el asesor registra el importe con descuento (para activar `discount_applicable`), exclusividad global del primer envío si se usó fuera de IA (solo se detecta si Brasper lo refleja en el historial), y la decisión de producto sobre campañas sin cupo global.

## Resolución de la revisión (P1–P4) y retirada en la API — 10 de octubre de 2026

| Pendiente | Resolución | Evidencia |
|---|---|---|
| P1 tabla de ofertas anterior | Migración nueva `0014_campaign_offers_columns` (no se editó `0013`, ya publicada) y `campaign_offers.ensure_schema()` agregan `delivery_key`, `state`, `updated_at` si faltan. Ofertas antiguas: clave calculada, `state='legacy_unverified'` (nunca se marcan enviadas ni se reenvían). | Check 80 (SQLite, reparación en caliente + INSERT nuevo + idempotencia); `sqlite_migration_checks.py` 0006→0014 con tabla antigua con datos; PGlite (PostgreSQL 18): 0013→ tabla antigua → 0014, repetición sin cambios, INSERT nuevo OK. |
| P2 reserva ligada a cotización | `campaigns.reserve(case_id, …)`: exige expediente abierto con promoción y **versión aceptadas**; rechaza campaña distinta, versión republicada (volver a cotizar y aceptar), ruta no incluida, monto/comisión fuera de condiciones, vigencia. Guarda `commission_gross`, `discount`, `commission_final`, `case_id`. Sin dato suficiente de Brasper exige **nota de verificación humana** (≥15 caracteres, guardada en `evidence`), no un booleano. Consumo solo con referencia oficial registrada en el expediente y nota («el depósito confirmado no basta»); liberar/vencer con nota. | Check 80 (ruta incompatible, monto fuera de límites, campaña distinta, versión republicada, expediente sin promoción, cotización vencida, desglose 30→12); check 78/79 adaptados (nota insuficiente rechazada, consumo sin referencia rechazado). |
| P3 snapshot y promoción obsoleta | Snapshot con `comision_bruta`, `comision_tasa`, `comision`; la promoción aceptada guarda versión, ruta, monto, comisión antes/después y ahorro. Cada cotización nueva borra `campaign_estimate` y lo recalcula. Expediente y comprobantes serializados por conversación (advisory lock en PostgreSQL, `BEGIN IMMEDIATE` en SQLite); un expediente con comprobante u operación no se reemplaza por una cotización nueva. Selección de campaña: **mayor ahorro efectivo tras mínimos/máximos/topes**, empate por prioridad y luego id. | Check 80 (6 aceptaciones simultáneas → 1 expediente; 6 comprobantes simultáneos → 6 conservados; recotizar sin campaña borra la anterior; 30% sin tope gana a 50% con tope 5 y al revés con comisión baja). |
| P4 integración | Panel: la reserva se hace desde el expediente (referencia + nota de verificación); consumir/liberar/vencer piden nota. Revisión visual local: expediente con desglose y pendientes, reserva desde la UI («Reservado · descuento 15, comisión 30 → 15»). `tsc` y `next build` OK. | Pendiente fuera de este equipo: PostgreSQL 16 multisesión y Redis reales (concurrencia probada con hilos en SQLite), migración sobre copia de datos reales, ensayo de cambio de credenciales owner en el servidor y confirmación del procedimiento de Brasper para el importe con descuento. |

Limpieza en IA: retirada la cotización personalizada del diseño anterior (`brasper_api.personalized_quote`, rama `identity` de `quotes.compute`) y el camino del secreto administrativo en `_integration_request`; `manage.py import-campaigns` exige `--file` porque la API ya no expone la administración; `BRASPER_IA_ADMIN_SECRET` fuera de `.env.example`.

### Retirada selectiva en la API principal

Hecha en el commit `74595ff` (detalle en [RETIRADA-CAMPANAS-API-2026-10-10.md](RETIRADA-CAMPANAS-API-2026-10-10.md)): se retiraron las rutas y el servicio de administración de campañas, `CampaignDraft`, `POST /brasper/ai/quotes` con `quote_for_client`, `BRASPER_IA_ADMIN_SECRET` y sus entradas de auditoría; se conservaron identidad, autenticación, auditoría, facturación, correcciones C1, migraciones 083/084 y la rama de campañas en el registro (latente, para no aplicar filas `CAMPAIGN` existentes sin sus límites). Suite API: 458 → 457.

**Incidente:** el trabajo debía quedar en la rama local `limpieza/retirada-campanas-api` para revisión. Una acción externa a las sesiones del agente (el reflog registra un `pull --ff --recurse-submodules --progress` propio de un cliente Git gráfico, seguido de `checkout main`) dejó el commit en `main` y luego se hizo push: `origin/main` = `74595ff`. No se reescribió historia. Opciones del responsable: conservarlo (tests verdes) o `git revert 74595ff` en `main` y llevarlo a la rama para revisión. Si `main` despliega automáticamente, esas rutas pueden ya no existir en el servidor.

