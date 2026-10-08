# Atención autónoma · Etapa 0 — Diagnóstico y línea base

Fecha: 7 de octubre de 2026 · Fuente: código del repositorio en la rama `chore/gate-single-tenant-ci`. Lo que no puede verificarse desde el repo se marca **[externo]** y queda como condición de la etapa, no como hecho.

## 0.1 Inventario de canales, herramientas y permisos

### Canales

| Canal | Entrada | Salida | Media | Estado |
|---|---|---|---|---|
| WhatsApp Cloud API | `POST /webhook` (firma `X-Hub-Signature-256`, dedup por `messages[].id`) | `whatsapp.send_text/send_image/send_image_upload` por **conexión de origen** | imagen/PDF → comprobante (asesor); audio → transcripción + revisión; video/sticker → cortesía | Operativo; varios números vía `whatsapp.connections` (estándar o `coex`) |
| Telegram | `POST /telegram/webhook[/brasper]` (secret, dedup por `update_id`) | `telegram.send_message/send_photo/send_file_upload` | foto/documento → comprobante; voz → transcripción + revisión | Operativo |
| Webchat | `POST /api/chat`, `POST /consulta-webchat` | respuesta síncrona (sin push) | — | Operativo; respuestas del asesor solo visibles al refrescar |

### Herramientas (contratos en `core/tool_contracts.py`, visibles en `GET /api/tools`)

| Herramienta | Entradas | Escribe | Timeout | Disponibilidad |
|---|---|---|---|---|
| `quote.compute` | origin, destination, amount_send / desired_receive | no | 15 s | ✅ TC, comisión y cupón en vivo de la API Brasper; sin API → rechaza (nunca tasa local) |
| `knowledge.search` | query, lang | no | 2 s | ✅ FAQ aprobada con fuente |
| `client.find` | phone + code_phone / full_name | no | 20 s | ✅ `/brasper/ai/clients/lookup` |
| `client.upsert` | lead | **sí** (idempotente) | 20 s | ✅ `/brasper/ai/clients/upsert`; tras timeout consulta antes de repetir |
| `deposit.accounts` | currency | no | 20 s | ✅ `/brasper/ai/deposit-accounts` |
| `status.lookup` | operation_id / phone | no | — | ❌ **Sin API** en la integración IA privada → el bot deriva con resumen |
| `message.send` | channel, to, text, connection_id | sí | 30 s | ✅ |

### Permisos del panel (`core/auth.py`)

| Rol | Permisos efectivos | Qué puede hacer |
|---|---|---|
| owner | `*` | Todo: configurar, asignar, eliminar conversaciones, publicar documentos |
| agent | `conversations:read/write`, `chat:test`… | Atender lo suyo + libres; notas, etiquetas, presencia; no configura |
| billing | `usage:read`… | Consumo y monitoreo |

Guards: `_assert_conversation_access` (un asesor no opera conversaciones de otro), claim atómico al tomar (409 si ya la tiene otro), la Admin API rechaza secretos crudos en producción.

## 0.2 Matriz de tareas ↔ endpoints

| Tarea del cliente | Flujo | Clasificación | Evidencia |
|---|---|---|---|
| Cotizar (ES/PT, directo/inverso, seguimiento "¿y para 2000?") | `handle_quote` (determinista) | **Operativa** | `run_checks` 21–23, 34; evals `cotizar-*`, `cambiar-monto-*` |
| Resolver dudas frecuentes con fuente | `handle_info` + `knowledge.py` | **Operativa** (13 entradas aprobadas ES/PT) | `run_checks` 47; evals `documentos-*`, `faq-*` |
| Dudas sin respuesta aprobada (horarios, tiempos, límites) | `handle_info` → incertidumbre explícita | **Incompleta** (requiere aprobación comercial de 3 borradores) | `faq.json` entradas `draft` |
| Identificarse (nombre, documento, teléfono, correo) y alta en Brasper | `handle_onboarding` + `client.upsert` idempotente | **Operativa** | `run_checks` 39, 40, 55 |
| Proceder al pago: cuentas oficiales | `handle_deposit_accounts` + `deposit.accounts` | **Operativa** (handoff seguro si la API no devuelve cuentas) | `run_checks` 38, 41 |
| Enviar comprobante | media → asesor valida; nunca se confirma el pago por recibirlo | **Operativa** (validación humana) | `run_checks` 28, 53 |
| Consultar estado del envío | `handle_status` → asesor con resumen | **Sin API** (`status.lookup` no existe en la integración IA) | `run_checks` 48; evals `estado-*` |
| Hablar con una persona | `handoff` (keyword) + asignación por carga/presencia | **Operativa** | `run_checks` 24, 51 |
| Audio (ES/PT) | transcripción → revisión → grafo; ambiguo → confirmación; ilegible → asesor con evidencia | **Operativa** | `run_checks` 32, 53; evals `audio-*` |
| Conversación libre | LLM (DeepSeek/OpenAI-compatible) con anti-bucle y guard de canales externos | **Operativa** | `run_checks` 11, 31, 49 |
| Edición de mensajes enviados / grupos de WhatsApp | — | **En investigación** (documentación del proveedor) | plan, sección "Reglas de ejecución" |

## 0.3 Causas de derivación y fallos (instrumentadas)

Eventos estructurados disponibles para la línea base (`observability.event`): `conversation.handoff` con `reason` ∈ {keyword, checkout, llm_error, media, deposit_accounts_unavailable, status_lookup_unavailable, repetition, audio_unreadable, sync_error, no_advisor_available, coex_human, manual}; `knowledge.answered/miss`; `bot.repetition`; `audio.ambiguous/transcribed/transcription_failed`; `webhook.duplicate`; `tool.timeout/validation_error/unavailable/idempotent_replay`; `handoff.queued`. Métricas por flujo (conteo, errores, p50/p95) en `GET /api/ops/metrics → flows`.

**Recibir un audio ya no deriva automáticamente**: deriva solo si no puede transcribirse tras los reintentos (y conserva el audio como evidencia).

## 0.4 Pendiente externo (condiciones de la etapa 0)

- **[externo]** Comparar la versión desplegada (Dokploy) con esta rama: `git rev-parse HEAD` del contenedor vs `main`; `e2e_smoke.py` contra el dominio real.
- **[externo]** Revisar 30 conversaciones anonimizadas de producción para calibrar la FAQ (hoy los borradores de horarios/tiempos/límites esperan respuesta del equipo comercial) y añadir escenarios reales a `tests/evals/scenarios.json`.
- **[externo]** Meta / WhatsApp: confirmar versión de Graph soportada (el código usa v21.0), contrato real de `contacts[]` con BSUID/username (el código conserva campos extra en `lead_data.wa_identity` sin asumir semántica), elegibilidad y procedimiento Coex del número +51 926 032 463 hoy operado por Kommo, permisos de la app y facturación. Nada de esto se ha cambiado.
- **[externo]** Aprobación de contenido legal (privacidad, términos, eliminación) por el responsable de Brasper antes de publicar desde el panel.
- **[externo]** Horario de atención y SLA humano para calibrar `presence_required` y la cola.

## 0.5 Línea base técnica (medida en local, 2026-10-07)

| Indicador | Valor |
|---|---|
| `run_checks.py` | 56/56 en verde |
| Evals de escenarios | 54/54 en verde (13 categorías) |
| Entradas FAQ aprobadas / borrador | 13 / 3 |
| Herramientas con API / sin API | 6 / 1 (`status.lookup`) |
| Panel | `tsc` + `next build` en verde; Lighthouse en CI |
