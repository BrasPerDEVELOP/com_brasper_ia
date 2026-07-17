# Onboarding de leads Brasper sin crear transacciones

## Objetivo

El bot identifica y registra clientes en la API oficial de Brasper, consulta las
cuentas oficiales donde pueden depositar y entrega el comprobante a un agente
comercial. El bot nunca crea una transacción ni genera un código de operación.

## Flujo validado

1. El bot obtiene el teléfono desde WhatsApp; en Telegram y webchat lo solicita.
2. Recopila nombres, apellidos, tipo de documento, número de documento y correo
   opcional.
3. Confirma los datos y hace un upsert idempotente en `com_brasper_api`, usando el
   documento como identidad principal y el teléfono como dato de contacto.
4. Guarda `brasper_user_id` y el estado de sincronización en `lead_data`.
5. La cotización sigue usando tasa, comisión y cupón de la API Brasper.
6. Cuando el cliente quiere continuar, consulta las cuentas oficiales de Brasper
   para la moneda de origen de la última cotización y las presenta sin alterarlas.
7. Al recibir un comprobante, guarda el adjunto en la conversación, cambia la
   etapa a `proof_received`, pausa el bot y asigna un agente comercial.
8. El agente verifica el depósito y crea manualmente la transacción desde el
   backoffice.

## Límites de seguridad

- No se llama a `POST /transactions/` desde la IA.
- No se registran cuentas bancarias del cliente.
- No se inventan cuentas, tasas, comisiones, cupones ni códigos de operación.
- Los endpoints de integración requieren un secreto compartido enviado en
  `X-Brasper-IA-Secret`; el secreto solo vive en variables de entorno.
- Los datos personales no se escriben en logs de observabilidad.

## Estados comerciales en la conversación

- `collecting_identity`: faltan datos obligatorios.
- `client_synced`: cliente creado o enlazado con Brasper.
- `quoted`: existe una cotización reciente.
- `awaiting_deposit`: se mostraron cuentas oficiales.
- `proof_received`: llegó un comprobante y debe intervenir un agente.
- `sync_error`: la API no pudo crear o actualizar al cliente.

El estado técnico de conversación (`active`, `handoff`, `closed`) permanece
separado de la etapa comercial.

## Contratos de API

`POST /brasper/ai/clients/upsert` recibe los datos identificatorios y devuelve
`id`, `created` y los campos públicos del cliente. Busca primero por documento y
actualiza solo los campos entregados.

`GET /brasper/ai/deposit-accounts?currency=PEN` devuelve únicamente cuentas del
catálogo oficial `transaction.banks`, filtradas por moneda.

## Pruebas mínimas

- WhatsApp extrae teléfono del `user_ref`; Telegram/webchat lo solicitan.
- Un documento existente se actualiza sin duplicarse.
- Un documento nuevo crea un usuario con rol `client`.
- Correo vacío es válido.
- Las cuentas se filtran por moneda de origen.
- El flujo de IA no contiene ni invoca creación de transacciones.
- Si falla la sincronización, conserva el lead local y deriva a un agente.
