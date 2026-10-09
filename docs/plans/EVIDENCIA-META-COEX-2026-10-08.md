# Revisión de Meta y Coex — 8 de octubre de 2026

Consulta de solo lectura en Chrome. No se publicaron apps, generaron tokens, cambiaron permisos, iniciaron altas ni enviaron mensajes.

## Recursos observados

| Recurso | Evidencia visible | Lo que todavía no demuestra |
|---|---|---|
| Portfolio Brasper `4369572786603273` | Empresa verificada en el resumen de la cuenta consultada | Aprobación de nuestra app, Tech Provider o elegibilidad Coex |
| App Brasper `1440455638184375` | Existe; la pantalla de prueba indica que no tiene números disponibles | Conexión de esta app al número operativo |
| WABA `430159343521708`, BrasperTransferencias | Propiedad de Brasper; cuenta aprobada; teléfono conectado, calidad alta | Que esté suscrita a nuestra app o sea Coex |
| Socio Kommo `1939643829692418` | Control total sobre esa WABA | Quién recibe los webhooks hoy, derechos contractuales de migración o convivencia entre integraciones |
| Otras cuentas | BrasPertransferencias `1066572906126595`, otra entrada Braspertransferencias App Business y Braspertransferencias01 | No confundirlas con la cuenta que tiene Kommo |

La pantalla consultada no mostraba un método de pago. Eso no demuestra ausencia de facturación mediante otro recurso o socio. El botón de registro como proveedor de tecnología abría información de registro; no se continuó ni se acreditó aprobación.

## Contratos oficiales consultados

Se leyeron las páginas completas correspondientes en Meta Developers. Algunas se muestran traducidas automáticamente; los nombres de propiedades provienen de los ejemplos de código, no de la traducción del texto.

### Identidad sin teléfono

Fuente: [Business-scoped user IDs](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids/), actualización visible 15-09-2026.

El username es opcional y no sirve como clave estable. El BSUID tiene alcance de portfolio; deben conservarse todos sus caracteres. El contrato muestra `contacts[].user_id`, `messages[].from_user_id`, `statuses[].recipient_user_id` y `profile.username`. El teléfono puede faltar. Para enviar a BSUID se usa `recipient`; para teléfono se usa `to`. Si se proporcionan ambos, el teléfono tiene prioridad. Los BSUID principales añaden `ENT` y requieren inscripción específica; no se debe asumir esa capacidad.

Adaptación local realizada: parser conserva BSUID/teléfono por separado, destinatario usa el campo correspondiente, no se extraen dígitos del BSUID para verificar identidad. Pruebas sintéticas de contrato; falta recibir payloads reales autorizados y completar reconciliación de identidades/cambios de número. Compartir una tarjeta de contacto manual no prueba identidad financiera.

### Coexistencia

Fuente: [Onboarding WhatsApp Business app users](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/), actualización visible 26-06-2026.

Requiere un proveedor de soluciones o tecnología y Embedded Signup preparado para la app Business. Conserva uso del celular. Se suscriben eventos adicionales de cuenta, historial, sincronización y ecos; los ecos humanos pausan el bot. La disponibilidad de historial depende del consentimiento y del proceso de sincronización, que tiene una ventana de inicio de 24 horas. Un pedido aceptado no acredita sincronización completa.

La comprobación concreta del número usa los campos `is_on_biz_app` y `platform_type`; `true` y `CLOUD_API` permiten confirmar su condición en ese recurso. Esa consulta autenticada no se ejecutó. Tampoco se realizó un alta ni se registró nuevamente el número.

Los mensajes enviados desde la app del celular no amplían la ventana de atención de Cloud API. El código de seguimiento limita la ventana configurable a un máximo de 24 horas desde el último mensaje del usuario; bloquea proactividad sin consentimiento, conexión y configuración verificadas. No sustituye envíos fuera de ventana por plantillas no aprobadas.

### Registro actual

Fuente: [Embedded Signup v4](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/version-4/), actualización visible 03-09-2026.

Meta anuncia la retirada de v2 y v3 el **15-10-2026**. v4 se selecciona mediante una nueva configuración de Facebook Login for Business con los productos correspondientes. Cloud API exige acceso avanzado a `whatsapp_business_management` y `whatsapp_business_messaging`. Coex continúa admitido. No se debe confundir la versión del flujo con `sessionInfoVersion` de los eventos, ni copiar un ejemplo antiguo sin revisar su contrato.

Pendiente: elegir y validar la versión Graph del despliegue; el adaptador conserva su versión histórica por defecto y permite `WHATSAPP_GRAPH_VERSION`. Leer ejemplos de v26 no certifica que la app tenga esas capacidades ni autoriza actualizar producción.

## Siguiente paso externo, concreto

1. Revisar en la cuenta de Kommo quién controla la integración y su suscripción actual; no quitar al socio.
2. Obtener un recurso de prueba autorizado, confirmar `is_on_biz_app`/`platform_type`, permisos efectivos y suscripciones. La app consultada aún no muestra un número disponible para probar.
3. Configurar Embedded Signup v4 y completar requisitos de proveedor/revisión cuando se autorice esa modificación. No publicar la app para resolver por suposición un problema de permisos.
4. Ejecutar matriz estándar/Coex/varios números con usuarios de prueba y regresión de Telegram. Hasta entonces solo hay contratos leídos y simulaciones locales.

Estado: E1 y E2 avanzados con evidencia; E3–E5 no ejecutados. La consulta externa no cierra por sí sola el plan de código.

## Revisión adicional — 9 de octubre de 2026 (Lima)

Consulta en Chrome de la app y WABA existentes, sin guardar cambios ni revelar secretos.

- App 1440455638184375: estado visible «Sin publicar». En Próximos pasos: número «Registrado», verificación del negocio «Completado», método de pago «No agregado» y plantilla aprobada «No creada». Estos resúmenes no prueban conexión de nuestra app con el número operativo ni ausencia de facturación/plantillas mediante Kommo.
- Configuración básica: nombre Brasper, dominio brasper.com, categoría Negocios y páginas. URLs de privacidad, términos e instrucciones de eliminación vacías. No se rellenaron con páginas no aprobadas.
- WABA 430159343521708: teléfono operativo conectado, calidad Alta; identificada como App de WhatsApp Business. Pestaña Socios confirma Kommo con control total. No se modificaron socios ni suscripciones.
- Coex específico de nuestra app continúa sin acreditar: falta comprobar los campos autenticados del número y una prueba autorizada API/celular. La etiqueta App de WhatsApp Business por sí sola no basta.

Bloqueos para cerrar ejecución externa: textos/URLs legales aprobados y publicados; recursos de prueba y secretos de mínimo privilegio; permisos/configuración efectivos de onboarding; identificar la integración/webhook operativos; onboarding Coex y pruebas reales; aprobaciones comerciales y piloto. No se certifica E1–E5 completo.

Facebook Login for Business → Configuraciones: la lista consultada no muestra configuraciones existentes; ofrece «Crear configuración» y «Crear desde una plantilla». Falta preparar y aprobar la configuración concreta de activos/permisos para onboarding. No se creó porque ampliar acceso requiere revisar primero el alcance; no se atribuye a la app una configuración que no existe.
