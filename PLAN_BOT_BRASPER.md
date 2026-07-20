# Plan de mejora — Bot Cauce conectado a la API de Brasper

Objetivo: que el bot de Brasper haga solo lo que hoy los asesores hacen a mano
(cotizar con el TC del día, asignar, captar datos), quede **conectado a la API de
Brasper** (`apibras.finzeler.com`) y **se ayude mutuamente** con el sistema de
Brasper (rates/comisión/cupón del lado Brasper; leads/operaciones/vouchers del
lado bot).

Contexto observado en Kommo (real): los asesores escriben la cotización **a mano**
con el TC del día (1.505, 1.496, 5.488 según fecha), la asignación de leads es
**inconsistente** ("Usuario resp." vacío), y el Agente de IA de Kommo **no está
activo**. Todo eso es justo lo que Cauce puede automatizar.

---

## Fase 1 — Cotización con TC en vivo ✅ HECHO
- Conector `core/brasper_api.py` a `apibras.finzeler.com`:
  `/coin/tax-rate`, `/coin/commission`, `/transactions/coupons/`.
- Caché en memoria (TTL 180s ≈ reserva de TC) + **fallback al config** si la API cae.
- Integrado en `core/quotes.py` (tasa, comisión y cupón en vivo).
- Config por tenant: `quote.api.enabled`. Activado para brasper (JSON + Postgres).
- **Verificado en vivo**: "Cotizar 500 PEN a BRL" → tasa **1.4880** (real) vs 1.46 (config).
- Tests: Gate caso 39 (usa la API con datos simulados + prueba el fallback).

---

## Fase 2 — Lead nuevo + banner de primer envío
**Qué:** cuando un usuario escribe por primera vez (sin conversación previa), el
bot lo marca como *lead nuevo* y envía un **banner de "primer envío"** (imagen +
texto de bienvenida/promo) antes del flujo normal.

**Cómo:**
- Detección: en `agent_graph.start_conversation`, si la conversación es nueva
  (0 mensajes previos) y el user_ref no tenía conversaciones cerradas → `is_new_lead`.
- Banner: `telegram.send_photo` / `whatsapp.send_image` (infra **ya existe**) con la
  imagen de campaña + copy de primer envío. Configurable por tenant
  (`onboarding.first_send_banner: {image_url|file, text}`).
- Evitar repetir: marca en la conversación/lead que el banner ya se envió.

**Esfuerzo:** bajo. La infra de envío de imágenes ya está.

---

## Fase 3 — Datos del lead estructurados (como Kommo)
**Qué:** el bot **captura y guarda** los datos clave del lead y los muestra en el
panel, replicando los campos de Kommo: Idioma, Canal de origen, Ruta, Estado TC,
Tipo de cliente, Monto a Enviar/Recibir, ¿Aplica Promo?, y datos KYC
(nombre, documento, banco/PIX del beneficiario).

**Cómo:**
- Tabla `leads` (o columnas JSON en `conversations`): `idioma, canal, ruta,
  estado_tc, tipo_cliente, monto_enviar, monto_recibir, aplica_promo,
  nombre, documento, banco_pix, beneficiario, evidencias`.
- El bot rellena los campos al detectarlos (la cotización ya conoce ruta/idioma/monto;
  el resto se pide en el flujo de checkout).
- Panel: pestaña "Operación" del hilo mostrando estos campos (hoy solo se ve el chat).
- Al asignar asesor (ya automático), el asesor recibe el lead **con los datos llenos**.

**Esfuerzo:** medio (migración + UI). Alto valor: elimina el llenado manual de Kommo.

---

## Fase 4 — Media completa (stickers / imágenes) — revisión
**Estado actual (ya implementado):**
- Entrantes: imágenes, documentos (comprobantes), **stickers**, video, voz/audio
  (con transcripción) → se guardan y se ven en el panel. ✅
- Salientes (bot/asesor): texto ✅, imágenes por URL y por subida (multipart) con
  burbuja para el asesor ✅.
- Bot puede enviar imagen + texto (usado para el banner de Fase 2). ✅ infra lista.

**Gaps a cerrar:**
- Bot enviar **stickers** salientes (hoy solo texto+imagen). Bajo valor, opcional.
- Enviar **plantillas/imagenes automáticas** en momentos clave (voucher recibido →
  "en revisión"; operación completada → comprobante). Se apoya en Fase 5.

**Esfuerzo:** bajo (la base de media ya existe; falta wiring puntual).

---

## Fase 5 — Integración profunda con Brasper ("se ayudan mutuamente")
**Brasper → bot (lectura):** tasas, comisión, cupones ✅ (Fase 1). Sumar: estado de
la operación / número de operación para confirmar al cliente.

**Bot → Brasper (escritura, requiere endpoints/credenciales de la API):**
- Registrar el lead / la solicitud de operación en el sistema de Brasper.
- Adjuntar el comprobante (voucher) captado por el bot.
- Consultar/actualizar estado (pago validado, enviado, comprobante emitido).

**Pendiente para esta fase:** confirmar con Brasper los **endpoints de escritura**
y **autenticación** (la API pública actual `/coin/*` y `/coupons/` es solo lectura).

**Esfuerzo:** medio-alto, depende de la doc de la API de Brasper.

---

## Reglas de negocio del proceso (del PPT/video) a incorporar
- **Reserva de TC 20 min**: la cotización marca vigencia; pasada la ventana, recotizar.
- **Handoff por monto alto / compliance**: el bot no cierra solo montos altos o
  señales de incidencia → deriva a asesor (ya hay auto-asignación round-robin).
- **Voucher recibido ≠ pago validado**: el comprobante crea tarea; valida un humano
  (ya se deriva a asesor al recibir comprobante).

## Auto-asignación (a afinar con el equipo real)
Hoy Cauce asigna al asesor con **menos carga** (round-robin) en handoff/checkout/
comprobante — mejor que la asignación inconsistente de Kommo. Falta: cargar los
**asesores reales** como usuarios `agent` para que el reparto sea sobre el equipo real.

## Nota de canal (WhatsApp)
Un número de WhatsApp entrega a **un solo** sistema. Si Brasper sigue en Kommo por
WhatsApp, Cauce va por Telegram (sin choque). Para que Cauce tome WhatsApp, ese
número **no puede** seguir en Kommo a la vez.

---

## Estado de implementación (2026-07-16)
| Fase | Estado | Notas |
|---|---|---|
| 1 · Cotización TC en vivo | ✅ HECHO | API Brasper + fallback; verificado (1.488 real) |
| 2 · Lead nuevo + banner | ✅ HECHO | detección primer contacto + banner (Telegram/WhatsApp/webchat) |
| 3 · Datos del lead | ✅ HECHO | `lead_data` (idioma/ruta/monto/TC…) + panel muestra chips |
| Reglas: TC 20 min | ✅ HECHO | vigencia en el texto de la cotización |
| Reglas: monto alto → asesor | ✅ HECHO | umbral configurable (5000) → handoff + asignación |
| 4 · Media (stickers/imágenes) | ✅ HECHO | entrante+saliente ya operativo; banner usa imagen |
| 5 · Escritura a Brasper | ⏳ SCAFFOLD | `register_operation` listo y gated OFF; falta endpoint+token reales |

Tests: Gate **43/43** (casos 39–43 cubren las fases nuevas). Todo verificado en vivo.

**Único pendiente real (Fase 5):** los endpoints de **escritura** de Brasper y el
**token** de autenticación. El código ya está listo (`brasper_api.register_operation`,
gated por `quote.api.write_enabled` + token); en cuanto lleguen las credenciales se
activa sin más cambios.

## Lo que aún depende de datos tuyos (no de código)
- **Imagen del banner** de primer envío (hoy va con texto; añade `onboarding.first_send_banner.image_url`).
- **Asesores reales** del equipo como usuarios `agent` (para que el round-robin reparta sobre ellos).
- **Credenciales de escritura** de la API de Brasper (Fase 5).
