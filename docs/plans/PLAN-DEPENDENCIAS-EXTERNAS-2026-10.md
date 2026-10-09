# Plan separado de configuración Facebook/Meta y dependencias externas

Actualizado: 9 de octubre de 2026 (Lima). Estado: pendiente de confirmación/ejecución. Este plan no bloquea completar el [trabajo local de código](PLAN-CODIGO-PENDIENTE-2026-10.md). Sí condiciona la activación real de capacidades dependientes de proveedores. La evidencia de cuentas citada corresponde a la revisión del 8 de octubre; esta actualización del plan no realizó cambios en Facebook.

No contiene autorización para cambiar producción, publicar la app, migrar un número, contratar servicios ni enviar mensajes. Primero recopilar evidencia de solo lectura. Cualquier cambio posterior debe tener alcance autorizado y recuperación preparada.

Revisión actual: [evidencia de Meta, Kommo y contratos Coex](EVIDENCIA-META-COEX-2026-10-08.md). Empresa verificada, app existente sin números de prueba disponibles y Kommo con control total sobre una WABA observados en Chrome. Coex del número y permisos de nuestra app todavía no acreditados. Embedded Signup v4 y contrato BSUID consultados; v2/v3 se retiran el 15-10-2026 según Meta. E1/E2 parciales; E3–E5 pendientes.

## Secuencia práctica de configuración, separada del desarrollo

| Paso | Qué revisar o configurar | Resultado para avanzar |
|---|---|---|
| F1 — Inventario | Confirmar portfolio Brasper, app existente, WABA, número, administradores, propietario y vínculo de Kommo. Obtener permisos efectivos y quién gestiona webhooks hoy. | Inventario documentado. No crear otra app ni retirar a Kommo sin necesidad demostrada. |
| F2 — Modalidades | Determinar si conectaremos solo recursos propios o también empresas clientes; elegir API estándar para números nuevos y Coex para números elegibles en WhatsApp Business. Confirmar vía directa o proveedor y requisitos que realmente aplican a esa vía. | Ruta por modalidad, elegibilidad comprobada y responsables. Verificación de empresa no equivale a Coex habilitado. |
| F3 — Documentación y páginas | Aprobar privacidad, términos y mecanismo de eliminación; publicar las vistas públicas preparadas en Brasper IA cuando esté autorizado, con HTTPS y sin login. | URLs públicas exactas para la app. La pantalla privada `/conversaciones` no sirve como política de privacidad. |
| F4 — App y acceso | Revisar configuración de la app existente, productos/caso de uso, Facebook Login for Business y Embedded Signup vigente, permisos necesarios, revisiones/acceso avanzado y Tech Provider si aplica. Configurar credenciales con mínimo privilegio y referencias en gestor de secretos. | Configuración revisada, permisos efectivos y revisión de Meta resuelta cuando corresponda. Nunca guardar tokens en los planes. |
| F5 — Recursos y webhook de prueba | Obtener WABA/número y usuarios autorizados de prueba. Configurar callback HTTPS y verificación, suscripciones y conexión con el sistema de pruebas; comprobar convivencia con Kommo antes de cambiar cualquier recurso compartido. | Recepción y envío controlados en la conexión correcta. El endpoint, firma, routing y deduplicación son tareas de código. |
| F6 — Coex | Ejecutar onboarding autorizado de un número elegible, comprobar coexistencia desde API y celular, consentimiento/sincronización disponible y eventos reales. No borrar el número ni desconectarlo para probar a ciegas. | Evidencia de Coex del número específico; historial y ecos comprobados. Un permiso de Kommo sobre la WABA no certifica nuestra integración. |
| F7 — Mensajería | Aprobar plantillas necesarias, consentimiento, idiomas y reglas de salida; revisar límites y facturación aplicables. | Plantillas/condiciones autorizadas para los casos que las necesitan. Una salida fuera de capacidad o ventana se bloquea. |
| F8 — Pruebas y piloto | Probar API estándar, Coex, varios números y regresión Telegram; después preparar despliegue gradual y recuperación con autorización. | Informe de integración real, métricas del piloto y criterio de activación. No publicar ni desplegar solo porque el plan está escrito. |

Si una cuenta o payload real descubre una incompatibilidad, registrar el cambio de código en C5/C6 y volver a probarlo antes de activar. Este plan contiene pasos pendientes, no promete disponibilidad de funciones Meta sin comprobar elegibilidad y contrato.

## E1. Meta, portfolio, app y relación con Kommo

- Revisar titularidad y permisos efectivos del portfolio, app, WABA y números; verificación de empresa, administradores y cuentas de sistema. Los estados observados anteriormente son históricos, no prueba de disponibilidad actual.
- Determinar qué papel tiene Kommo, quién controla el webhook y qué integración opera hoy; documentar si se puede compartir, reemplazar o migrar sin interrumpir servicio. No retirar al socio ni cambiar suscripciones durante la investigación.
- Confirmar requisitos vigentes de acceso/revisión, permisos, publicación, facturación y, si corresponde, Tech Provider. Una empresa verificada no demuestra que nuestra app pueda usar Coex.

Entrega: inventario de recursos y permisos, dependencias y camino de conexión propuesto con evidencia; sin tokens en documentos.

## E2. Contratos oficiales de WhatsApp y elegibilidad Coex

- Consultar documentación primaria vigente para la versión Graph elegida y guardar referencias/fecha: identidad, BSUID, username, teléfono opcional, scope, eventos de cambio y destinatarios de envío.
- Confirmar campos exactos de webhooks y respuestas con ejemplos oficiales y después con payloads anonimizados de prueba. No reutilizar contratos de otro BSP como si fueran Cloud API directa.
- Revisar elegibilidad real del número y app del celular para Coex, Embedded Signup, restricciones de región/cuenta, sincronización de historial/estado y ecos. Documentar datos disponibles y límites oficiales; no prometer acceso a todo el historial.
- Confirmar reglas actuales de ventanas, consentimiento, plantillas, medios y salidas proactivas. Investigar grupos o edición de mensajes únicamente como evaluación de capacidades, sin prometer implementación.

Entrega: matriz de contratos confirmados/no confirmados. Si contradicen la interfaz preparada localmente, abrir tareas concretas de adaptación y regresión en C5/C6; no activar hasta terminarlas.

## E3. Recursos de prueba e integración real

- Obtener recursos de prueba autorizados para API estándar, Coex y varios números/conexiones, y credenciales de mínimo privilegio en el gestor de secretos.
- Preparar usuarios de prueba y una matriz de texto, imagen, audio, plantilla, entrega, eco propio, intervención desde celular, pausa de IA, reanudación, historial y reconexión.
- Ejecutar corte y recuperación de una conexión sin afectar a otra ni al servicio actual. Verificar aislamiento y ausencia de duplicados, incluida regresión de Telegram en un bot de prueba.
- Probar la vinculación de identidad que requiera OTP o sesión externa. Un adaptador simulado no acredita entrega real de códigos ni identidad real.

Entrega: evidencia con modalidad, versión, recurso anonimizado, caso, resultado y reversión; nunca pruebas con clientes reales sin autorización.

## E4. Aprobaciones de Brasper y contenido

- Confirmar y aprobar FAQ ES/PT, horarios, SLA, límites, mensajes, imágenes, perfiles y campañas concretas. El motor queda configurable; el agente no inventa beneficios recurrentes ni activa promociones reales.
- Las reglas ya aprobadas no requieren volver a preguntarse: descuento 0–100% sobre comisión; completadas consumen primer envío, pendientes reservan y fallidas/canceladas liberan. Cualquier reversión especial de una operación completada sí requiere una regla explícita.
- Validar contenido de privacidad, términos, retención, responsables/contactos y solicitudes de eliminación con la empresa. El código de edición y publicación pertenece a C7; aprobar textos reales pertenece aquí.
- Cuando esté autorizado publicar, verificar las páginas de Brasper IA por HTTPS sin login y registrar las URLs exactas en Meta. `/conversaciones` sigue siendo privada; no se usa como URL legal. No trasladar esta tarea a brasper.com.

Entrega: contenidos y parámetros aprobados, responsables y versiones. No considerar texto de ejemplo como aprobación legal/comercial.

## E5. Línea base, modelo real, producción y piloto

- Conseguir una exportación autorizada y anonimizada de al menos 30 conversaciones y las fuentes de conocimiento necesarias de Umbler; no abrir chats que alteren leído ni exportar datos sin alcance autorizado.
- Comparar artefactos desplegados y versiones locales mediante inspección de solo lectura. Documentar diferencias antes de decidir sustitución o migración.
- Evaluar naturalidad y cumplimiento ES/PT con el modelo real, credenciales y presupuesto aprobados; enviar solo datos sintéticos o anonimizados autorizados. Separar resultados reales de pruebas deterministas.
- Tras cerrar el código y las integraciones, preparar despliegue gradual autorizado, backups del entorno, rollback, monitorización y piloto con responsables y métricas acordadas. La propuesta histórica de 80% requiere línea base y aceptación; no es garantía.

Entrega: informe de preparación y, después de autorización, evidencia del piloto. Sin aprobación de despliegue, el producto permanece preparado localmente.

## Regla de coordinación

No esperar por Meta para implementar lógica interna, migraciones, pantallas o pruebas locales. Tampoco dar por funcional una integración de tercero porque pasan mocks. Toda nueva información externa que necesite código se convierte en una tarea local verificable antes de activar la capacidad.

## Revisión adicional — 9 de octubre de 2026 (Lima)

Consulta en Chrome de la app y WABA existentes, sin guardar cambios ni revelar secretos.

- App 1440455638184375: estado visible «Sin publicar». En Próximos pasos: número «Registrado», verificación del negocio «Completado», método de pago «No agregado» y plantilla aprobada «No creada». Estos resúmenes no prueban conexión de nuestra app con el número operativo ni ausencia de facturación/plantillas mediante Kommo.
- Configuración básica: nombre Brasper, dominio brasper.com, categoría Negocios y páginas. URLs de privacidad, términos e instrucciones de eliminación vacías. No se rellenaron con páginas no aprobadas.
- WABA 430159343521708: teléfono operativo conectado, calidad Alta; identificada como App de WhatsApp Business. Pestaña Socios confirma Kommo con control total. No se modificaron socios ni suscripciones.
- Coex específico de nuestra app continúa sin acreditar: falta comprobar los campos autenticados del número y una prueba autorizada API/celular. La etiqueta App de WhatsApp Business por sí sola no basta.

Bloqueos para cerrar ejecución externa: textos/URLs legales aprobados y publicados; recursos de prueba y secretos de mínimo privilegio; permisos/configuración efectivos de onboarding; identificar la integración/webhook operativos; onboarding Coex y pruebas reales; aprobaciones comerciales y piloto. No se certifica E1–E5 completo.

Facebook Login for Business → Configuraciones: la lista consultada no muestra configuraciones existentes; ofrece «Crear configuración» y «Crear desde una plantilla». Falta preparar y aprobar la configuración concreta de activos/permisos para onboarding. No se creó porque ampliar acceso requiere revisar primero el alcance; no se atribuye a la app una configuración que no existe.
