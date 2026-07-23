# Onboarding de leads Brasper sin crear transacciones

## Objetivo

El bot identifica y registra clientes en la API oficial de Brasper, consulta las
cuentas oficiales donde pueden depositar y entrega el comprobante a un agente
comercial. El bot nunca crea una transacción ni genera un código de operación.

## Flujo validado

1. El bot obtiene el teléfono desde WhatsApp y busca primero al cliente existente.
2. Si no lo reconoce, pide solo el nombre completo. El cliente puede omitirlo y
   cotizar directamente sin quedar bloqueado en el registro.
3. El documento se solicita recién cuando el cliente confirma que desea continuar;
   no se pide correo durante este flujo.
4. Confirma los datos y hace un upsert idempotente en `com_brasper_api`, usando el
   documento como identidad principal y el teléfono como dato de contacto.
5. Guarda `brasper_user_id` y el estado de sincronización en `lead_data`.
6. La cotización sigue usando tasa, comisión y cupón de la API Brasper.
7. Cuando el cliente quiere continuar, consulta las cuentas oficiales de Brasper
   para la moneda de origen de la última cotización y las presenta sin alterarlas.
   Si la consulta falla, oculta el error técnico, activa `handoff`, asigna un asesor
   y comunica que se contactará en unos instantes.
8. Al recibir un comprobante, guarda el adjunto en la conversación, cambia la
   etapa a `proof_received`, pausa el bot y asigna un agente comercial.
9. El agente verifica el depósito y crea manualmente la transacción desde el
   backoffice.

## Límites de seguridad

- No se llama a `POST /transactions/` desde la IA.
- No se registran cuentas bancarias del cliente.
- No se inventan cuentas, tasas, comisiones, cupones ni códigos de operación.
- Los endpoints de integración requieren un secreto compartido enviado en
  `X-Brasper-IA-Secret`; el secreto solo vive en variables de entorno.
- Los datos personales no se escriben en logs de observabilidad.

## Estados comerciales en la conversación

- `awaiting_name`: se ofreció indicar el nombre o cotizar directamente.
- `identified`: se obtuvo el nombre sin solicitar aún documentos.
- `collecting_identity`: el cliente confirmó el envío y faltan datos obligatorios.
- `client_synced`: cliente creado o enlazado con Brasper.
- `quoted`: existe una cotización reciente.
- `awaiting_deposit`: se mostraron cuentas oficiales.
- `proof_received`: llegó un comprobante y debe intervenir un agente.
- `sync_error`: la API no pudo crear o actualizar al cliente.

El estado técnico de conversación (`active`, `handoff`, `closed`) permanece
separado de la etapa comercial.

## Contratos de API

`GET /brasper/ai/clients/lookup` busca puntualmente por teléfono o nombre y nunca
expone la lista completa. Devuelve `document_verified` e `is_first_transfer`, no
el número de documento.

`POST /brasper/ai/clients/upsert` recibe los datos identificatorios y devuelve
`id`, `created` e `is_first_transfer`. Busca primero por documento, luego por
teléfono y rechaza cuando ambos identificadores pertenecen a personas distintas.

`GET /brasper/ai/deposit-accounts?currency=PEN` devuelve únicamente cuentas del
catálogo oficial `transaction.banks`, filtradas por moneda.

## Pruebas mínimas

- WhatsApp extrae teléfono del `user_ref` y reconoce a un cliente recurrente.
- Un cliente nuevo puede cotizar antes de entregar documento o correo.
- El banner de primer envío aparece solo tras verificar que el cliente no existe.
- Un documento existente se actualiza sin duplicarse.
- Un documento nuevo crea un usuario con rol `client`.
- Correo vacío es válido.
- Las cuentas se filtran por moneda de origen.
- El flujo de IA no contiene ni invoca creación de transacciones.
- Si falla la sincronización, conserva el lead local y deriva a un agente.
- Si fallan las cuentas oficiales, no muestra detalles técnicos y realiza handoff.
