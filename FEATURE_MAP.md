# FEATURE_MAP — Brasper Bot / Cauce

> Contrato: intención → path código → fuente de datos. Actualizar al añadir una ruta al grafo.

## Un solo stack (desde Fase 0)

| Stack | Entry | Orquestación | Cotización real |
|-------|-------|--------------|-----------------|
| **Prod Docker** | `backend/main.py` | `backend/core/agent_graph.py` | ✅ `core/quotes.py` → `core/brasper_api.py` → apibras.finzeler.com |

El legacy `app/` fue eliminado; no hay segundo motor.

## Intenciones Brasper (ruta en `agent_graph.route_after_preprocess`)

| Orden | Intención | Detector | Nodo | Fuente de datos | LLM |
|-------|-----------|----------|------|-----------------|-----|
| 0 | Conversación en handoff | `conv_status == handoff` | `bot_paused` | — | No (bot en silencio) |
| 0b | Token de vinculación (`/start <token>`, `vincular <token>`) | `identity_link.extract_token` (en `engine`, antes de guardar) | `handle_identity_link` | API `/brasper/ai/identity-links/redeem` | No |
| 1 | Onboarding (saludo de lead nuevo / identidad para pagar) | `lead_onboarding.needs_onboarding` | `handle_onboarding` | API Brasper `/brasper/ai/clients/*` | No |
| 2 | Handoff | `handoff.keywords` | `do_handoff` | asesor con menos carga (`auth.derive_to_advisor`) | No |
| 3 | Cita (solo verticales con calendario; Brasper no) | `calendar_adapter` | `handle_calendar` | DB `appointments` | No |
| 4 | Cotización | `quotes.has_intent` | `handle_quote` | TC/comisiones/cupones en vivo (`brasper_api`) o config si API apagada | No |
| 4b | Estado de envío | `_status_hit` (una referencia `PxB-77` no se toma como monto) | `handle_status` | `status.lookup` (teléfono WA verificado) o `status.linked` (grant) | No |
| 5 | Checkout ("continuar", "¿cómo pago?") | `_checkout_hit` | `handle_deposit_accounts` | API Brasper `/brasper/ai/deposit-accounts` | No |
| 6 | Tool externa | `tool_router.select_tool` | `handle_tool` → LLM redacta | `externalApis` del tenant | Sí (redacción) |
| 7 | Chat libre | resto | `build_messages` → `call_llm` | DeepSeek | Sí |

Fallo del LLM → `llm_failed`: respuesta cortés + handoff (el bot nunca queda mudo).

## Reglas de negocio implementadas

| Regla | Dónde | Caso `run_checks` |
|-------|-------|-------------------|
| Tasa solo de la API; sin fallback local si falla | `quotes.rate_for` / `compute` | 34 |
| Cupón = % sobre la comisión (no sobre el monto) | `quotes._quote_from_gross_send` | 21 |
| Modo "recibir" (búsqueda inversa) | `quotes._quote_inverse` | 21 |
| Seguimiento conserva corredor y modo | `quotes.extract_request(prev=…)` | 22, 23, 45 |
| Aclaración determinista si falta un dato | `quotes.clarify_reply` | 23 |
| Vigencia del TC 20 min (`quote.tc_validity_minutes`) | `quotes.reply` | 37 |
| Monto alto → asesor (`quote.high_amount_threshold`) | `agent_graph.handle_quote` | 37 |
| Cotizar antes de identificarse; documento solo al continuar | `lead_onboarding` | 39 |
| Cliente recurrente por teléfono (WhatsApp) | `lead_onboarding.recognize_by_phone` | 40 |
| Cuentas oficiales sin crear transacción | `lead_onboarding.deposit_accounts_reply` | 38, 41 |
| Nunca derivar a WhatsApp externo / redes | `agent_graph.sanitize_no_external_channels` | 31 |
| Comprobante (media) → asesor | `telegram._handle_incoming_media` | 28 |
| Voz → transcripción → bot responde | `telegram._handle_incoming_audio` + `audio_adapter` | 32 |
| Vinculación Telegram/webchat: token de un uso, grant cifrado, dueño, timeout sin repetir | `identity_link`, `operation_status` | 70 |
| Contacto interno y alias por conexión; BSUID sin teléfono; conflictos sin fusión | `contacts` | 71 |
| Creación concurrente de conversación única; lock en DB si Redis cae | `db._creation_lock`, `db_lock` | 71 |
| Salidas enviado/cancelado/incierto/fallido; estados que solo avanzan; ecos diferidos | `outbound`, `channel_events`, `coex` | 72 |
| Alcance por canal/número/sector; comprobantes con `media:private` | `access` | 73 |
| Usuarios: contraseñas individuales, temporales con cambio obligatorio, sesiones revocables, último owner protegido | `users`, `auth` | 76 |
| Promociones en IA: oferta de bienvenida ES/PT, idioma incierto, sin repetir | `campaign_offers` | 77 |
| Promociones en IA: versiones, rutas, cupos, primer envío único por identidad, concurrencia, importación | `campaigns` | 78 |
| Expediente IA, descuento no prometido sin procedimiento verificado, vencimiento conciliado | `cases`, `campaigns` | 79 |
| Job de seguimiento reclamado y caído → incierto (nunca se reenvía) | `engagement.dispatch_one` | 67 |

## Endpoints API

| Método | Path | Uso |
|--------|------|-----|
| POST | `/api/chat` | Webchat del panel (token) |
| POST | `/consulta-webchat` | Compat público del webchat anterior |
| GET/POST | `/webhook` | WhatsApp Cloud API (firma `X-Hub-Signature-256`) |
| POST | `/telegram/webhook` | Telegram (secret token) |
| GET | `/api/conversations`, `/api/conversations/{id}` | Panel: bandeja + lead estructurado |
| POST | `/api/conversations/{id}/reply` · `/status` · `/send-image` · `/upload` | Takeover del asesor |
| DELETE | `/api/conversations/{id}?expected_user_ref=` | Borrado con guard |
| GET/PATCH | `/api/admin/tenants` | Config Brasper (deep-merge) |
| POST | `/api/admin/tenants/pause` · `/resume` · `/secrets` | Operación |
| GET | `/api/admin/quote-rates` | TC en vivo para el panel |
| DELETE | `/api/admin/brasper/clients/{id}?expected_name=` | Borrar perfil Brasper creado por el bot |
| GET | `/health`, `/api/ops/metrics`, `/api/ops/alerts`, `/api/ops/usage-daily` | Ops |
| GET | `/api/conversations/{id}/deliveries` | Estado de las salidas automáticas |
| GET / PUT | `/api/admin/users` · `/api/admin/users/{email}/scope` | Alcance por canal/número/sector (`users:write`) |
| GET / POST | `/api/admin/contact-conflicts` · `/{id}/resolve` | Contactos por revisar (sin fusión automática) |

## Config Brasper (`backend/config/tenants.json` → `tenants.brasper`)

| Campo | Estado |
|-------|--------|
| `quote.api.enabled` + `base_url` | ✅ API real |
| `quote.pairs` | ✅ PEN↔BRL, USD↔BRL |
| `quote.rates` / `commission_ranges` / `coupon` | Solo se usan si `quote.api.enabled=false` (dev/tests) |
| `quote.tc_validity_minutes` / `high_amount_threshold` | ✅ 20 min / 5000 |
| `system_prompt` | ✅ prohíbe inventar tasas y derivar a WhatsApp |
| `handoff.keywords` | ✅ es/pt/en |
| Secretos | ✅ solo `*_env` |

## Tests

| Suite | Path | Cubre |
|-------|------|-------|
| Gate local/CI | `backend/tests/run_checks.py` | 73 casos: grafo, cotizador, onboarding, handoff, canales, identidad, contactos, salidas, permisos, panel, ops (sin LLM, sin red) |
| Evals | `backend/tests/evals/run.py` | 57 escenarios ES/PT deterministas |
| Migraciones SQLite | `backend/tests/sqlite_migration_checks.py` | 0006 → 0010 con datos, repetición y backup/restore |
| Doctests | `backend/core/policies.py` | Primitivas puras (idioma, monedas, montos) |
| Smoke post-deploy | `backend/tests/e2e_smoke.py` | Servidor vivo: health, login, cotización, handoff |

## Plan

[docs/plans/00-ROADMAP.md](docs/plans/00-ROADMAP.md)
