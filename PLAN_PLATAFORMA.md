# Plan de Produccion: Plataforma IA Multi-Tenant

## 1. Objetivo

El proyecto entra en etapa de produccion. La plataforma debe servir para operar
bots de varios clientes desde un panel interno de agencia, con WhatsApp,
Telegram y webchat, midiendo costos, guardando conversaciones y permitiendo
activar, pausar y configurar tenants sin tocar codigo.

No se busca construir todavia un SaaS publico self-service. La prioridad es una
plataforma gestionada: tu equipo configura clientes, conecta canales, revisa
conversaciones, controla consumo y despliega con contenedores.

## 2. Alcance Actual

Lo que ya queda como base de produccion:

| Area | Decision |
|---|---|
| Backend | FastAPI en `backend/` |
| Panel | Next.js en `web/` |
| IA | LangGraph como orquestador principal |
| Canales | WhatsApp Cloud API, Telegram Bot API y webchat |
| Datos | Postgres en produccion; SQLite solo local/tests |
| Temporal | Redis para locks, debounce, jobs y estado corto |
| Deploy | Docker Compose con `api`, `worker`, `admin-web`, `reverse-proxy`, `postgres`, `redis` |
| Tenants | Configuracion administrable desde API/panel, con bootstrap desde JSON |
| Seguridad | RBAC, scopes por tenant, secrets por variables de entorno y webhooks firmados |

## 3. Arquitectura Decidida

```text
Cliente final
  -> WhatsApp / Telegram / Webchat
  -> reverse-proxy
  -> api FastAPI
  -> TenantResolver
  -> LangGraph Agent
  -> Tools / Adapters
  -> Postgres + Redis
  -> respuesta al canal
```

### Contenedores

| Contenedor | Tecnologia | Responsabilidad |
|---|---|---|
| `api` | Python + FastAPI + Uvicorn | Webhooks, API interna, auth, tenant resolver |
| `worker` | Python | Jobs, debounce, reintentos, backups, tareas asincronas |
| `admin-web` | Next.js | Panel interno de operacion |
| `postgres` | Postgres | Fuente de verdad de produccion |
| `redis` | Redis | Locks, colas, debounce y cache temporal |
| `reverse-proxy` | Caddy | TLS, rutas publicas, health y proxy al panel/API |

### Frameworks y librerias principales

| Capa | Stack |
|---|---|
| API | FastAPI, Pydantic, Uvicorn |
| Panel | Next.js, React, TypeScript |
| Agente IA | LangGraph, LangChain core/adapters |
| LLM providers | OpenAI, DeepSeek, Anthropic por tenant |
| HTTP/canales | `httpx` contra WhatsApp Cloud API y Telegram Bot API |
| DB | Postgres con `psycopg`; Alembic para migraciones |
| Jobs/estado | Redis |
| Reverse proxy | Caddy |

## 4. Datos

### Postgres

Postgres es la fuente de verdad de produccion. Guarda:

- Tenants y configuracion activa.
- Usuarios, roles, permisos y scopes.
- Conversaciones y mensajes.
- Usage events: tokens, costo, proveedor, modelo y tenant.
- Auditoria de cambios, login, rotacion de secrets y errores operativos.
- Estado de canales.
- Conectores externos.
- Citas y reservas.
- Historial de rotacion de secretos.

Regla obligatoria:

```text
tenant_id siempre forma parte de las consultas, indices y restricciones.
```

### Redis

Redis se usa para:

- Locks por tenant/conversacion.
- Debounce de rafagas de mensajes.
- Cola liviana de jobs.
- Dead-letter queue.
- Cache corta de herramientas o estados temporales.

Todas las claves deben llevar prefijo por tenant cuando aplique:

```text
{tenant_id}:...
```

### SQLite

SQLite queda solo como fallback local y para tests. No debe usarse en
produccion.

### MongoDB

MongoDB no entra por defecto. Solo debe agregarse si aparece un caso claro,
por ejemplo logs crudos de webhooks a gran volumen o documentos
semi-estructurados. Mientras tanto, Postgres + Redis reduce complejidad y es
suficiente.

## 5. Motor IA

El bot no debe ser solo un respondedor de dudas. Debe actuar como agente por
tenant, con reglas, herramientas y escalamiento.

### Responsabilidades de LangGraph

- Mantener estado de conversacion.
- Detectar intencion.
- Pedir datos faltantes.
- Responder en el idioma del usuario si escribe en otro idioma.
- Usar herramientas cuando haga falta.
- Agendar o reservar citas cuando el tenant tenga calendario.
- Consultar APIs externas configuradas por tenant.
- Escalar a humano cuando el usuario lo pida o falte contexto.
- Evitar gasto de LLM cuando una regla deterministica sea suficiente.
- Persistir mensajes y medir consumo.

### Flujo del grafo

```text
pre_process
  -> classify_intent
  -> collect_required_data
  -> route_tool_or_answer
  -> post_process
  -> persist_and_measure
```

### Providers

Cada tenant puede definir:

- `openai`
- `deepseek`
- `anthropic`
- modelo principal
- proveedor fallback
- limite de costo mensual
- limite de tokens por conversacion
- secret por variable de entorno

El agente nunca debe guardar secretos crudos. El tenant solo referencia nombres
de variables como `OPENAI_API_KEY_CLIENTE` o `DEEPSEEK_API_KEY_CLIENTE`.

## 6. Canales

### WhatsApp

Debe soportar:

- Webhook firmado con `META_APP_SECRET`.
- Resolucion de tenant por `phone_number_id`.
- Envio de texto.
- Plantillas HSM.
- Manejo de ventana de 24 horas.
- Estados de mensaje.
- Debounce de rafagas.
- Procesamiento asincrono de audios y transcripcion.

### Telegram

Debe soportar:

- Webhook por tenant: `/telegram/webhook/{tenant_id}`.
- Secret token obligatorio en produccion.
- `setWebhook` desde la API/panel.
- `deleteWebhook`.
- `getWebhookInfo`.
- Mensajes de texto.
- Botones de handoff.

### Webchat

Debe soportar:

- Token publico por tenant.
- Dominios permitidos.
- Rate limit.
- Widget embebible.
- Historial por visitante.

## 7. Seguridad

Antes de publicar fuera de localhost:

- `APP_ENV=production` obligatorio.
- Sin usuarios ni tokens demo activos.
- `DATABASE_URL` debe apuntar a Postgres.
- `REDIS_URL` debe estar definido y responder.
- `CORS_ALLOW_ORIGINS` debe usar dominios reales.
- WhatsApp debe validar firma.
- Telegram debe validar secret token por tenant.
- Todo endpoint interno debe exigir auth y scope.
- Los logs no deben imprimir tokens, API keys ni secrets.
- Los secretos se guardan como referencias `*_env`.
- Cada cambio de tenant debe quedar auditado.
- Debe existir backup y rollback documentado.

## 8. Fases de Produccion

### Fase 1: Hardening Operativo

Objetivo: dejar el stack seguro, desplegable y verificable.

Entregables:

- [x] Reverse proxy enruta API, panel, WhatsApp y Telegram.
- [x] Health check valida Postgres y Redis en produccion.
- [x] Tokens demo deshabilitados en produccion.
- [x] Rate limiting en login, chat y webhooks.
- [x] Webhook WhatsApp con firma.
- [x] Telegram con secret obligatorio por tenant.
- [x] `.env.example` completo.
- [x] Runbook de deploy inicial.
- [x] CORS cerrado con dominio real (en produccion se descartan origenes localhost; dominio real via `CORS_ALLOW_ORIGINS`).
- [ ] Probar `docker compose up --build` en una maquina con Docker instalado.

### Fase 2: Datos y Migraciones

Objetivo: operar con Postgres como fuente de verdad.

Entregables:

- [x] Soporte Postgres via `DATABASE_URL`.
- [x] Alembic configurado.
- [x] Migraciones versionadas.
- [x] Tablas de auth, conversaciones, mensajes, usage y auditoria.
- [x] Tabla de tenants.
- [x] Tabla de citas.
- [x] Tabla de rotacion de secrets.
- [x] Aislamiento por `tenant_id`.
- [x] SQLite limitado a local/tests.
- [ ] Separar repositorios por dominio para reducir `core/db.py`.

### Fase 3: Administracion de Tenants

Objetivo: operar clientes desde API/panel sin editar archivos.

Entregables:

- [x] Crear tenant.
- [x] Editar tenant.
- [x] Pausar tenant.
- [x] Reanudar tenant.
- [x] Configurar proveedor IA.
- [x] Configurar WhatsApp.
- [x] Configurar Telegram.
- [x] Configurar secret refs.
- [x] Ver usage por tenant.
- [x] Auditar cambios.
- [x] Rechazar secretos crudos en produccion.
- [x] Validaciones de negocio por vertical/canal (`tenants.validate_tenant_config`; ver `VERTICALES.md`).

### Fase 4: Agente y Herramientas

Objetivo: que el bot resuelva flujos reales, no solo preguntas simples.

Entregables:

- [x] LangGraph como motor principal.
- [x] TenantResolver.
- [x] ModelAdapter por tenant.
- [x] ToolRouter.
- [x] Handoff.
- [x] Deteccion de idioma por mensaje.
- [x] Conectores externos desde el grafo.
- [x] CalendarAdapter para citas.
- [x] Persistencia y medicion de uso.
- [x] Validaciones fuertes por vertical: salud/reservas exigen calendario; retail/servicios sin requisito duro (ver `VERTICALES.md`).
- [ ] Pruebas de conversaciones largas por canal.

### Fase 5: Worker y Automatizaciones

Objetivo: sacar del request web lo que no debe bloquear al usuario.

Entregables:

- [x] Worker en contenedor separado.
- [x] Cola Redis.
- [x] Debounce de WhatsApp/Telegram.
- [x] Reintentos de jobs.
- [x] Dead-letter queue.
- [x] Backups automaticos opcionales.
- [x] Transcripcion de audios WhatsApp (webhook -> job `whatsapp.audio` -> `audio_adapter` -> motor; fallback en linea sin Redis).
- [x] Jobs programados (scheduler del worker `run_scheduled`: alertas externas + retencion; `SCHED_INTERVAL_SECONDS`).
- [x] Agregacion avanzada de usage/costos (`db.usage_daily` + `GET /api/ops/usage-daily`).

### Fase 6: Observabilidad y Costos

Objetivo: detectar problemas antes de que el cliente reclame.

Entregables:

- [x] Logs JSON estructurados.
- [x] Redaccion de secretos en logs.
- [x] Endpoint protegido `/api/ops/metrics`.
- [x] Endpoint protegido `/api/ops/alerts`.
- [x] Usage por tenant.
- [x] Costos por proveedor/modelo.
- [x] Alertas externas: webhook Slack/Mattermost-compatible (`ALERT_WEBHOOK_URL`, con cooldown).
- [ ] Dashboard operacional completo.
- [ ] SLA y reporte mensual por cliente.

### Fase 7: Operacion Comercial

Objetivo: poder vender y operar clientes sin improvisar.

Entregables:

- [x] Checklist de onboarding (`ONBOARDING.md`).
- [x] Checklist de offboarding (`ONBOARDING.md`).
- [x] Plantilla de configuracion por vertical (`VERTICALES.md`).
- [x] Exportacion de conversaciones (`GET /api/{tenant_id}/export`).
- [x] Politica de retencion y borrado (`POLITICAS.md` + purga automatica `RETENTION_DAYS`).
- [x] Contrato base de servicio (plantilla en `POLITICAS.md` — requiere revision legal).
- [x] Politica de privacidad y tratamiento de datos (plantilla en `POLITICAS.md` — requiere revision legal).
- [ ] SLA por plan/cliente.

## 9. Prioridad Inmediata

Orden recomendado para seguir:

1. Cerrar CORS con el dominio real del panel.
2. Probar el stack completo con Docker en una maquina con Docker instalado.
3. Implementar transcripcion de audios WhatsApp en el worker.
4. Agregar validaciones por vertical/canal antes de activar tenants.
5. Separar `core/db.py` en repositorios por dominio.
6. Crear checklist comercial de onboarding/offboarding.
7. Preparar runbook de incidentes y monitoreo externo.

## 10. Criterio de Listo Para Produccion

La plataforma esta lista para operar clientes reales cuando:

- `docker compose up --build` levanta el stack completo.
- `/health` responde `ok: true` en produccion.
- Postgres y Redis estan activos.
- No existen tokens demo activos.
- Todo webhook publico valida firma o secret.
- Todo endpoint interno exige auth y scope por tenant.
- CORS solo permite dominios reales.
- Los tenants se pueden crear, pausar y editar desde panel/API.
- Los secrets se guardan solo como referencias.
- Hay backups y restore probado.
- Hay logs por tenant.
- Hay alertas de costo/error.
- Hay pruebas automaticas de aislamiento multi-tenant.
- Hay runbook de deploy, rollback e incidentes.

## 11. No Construir Todavia

Para no inflar el proyecto antes de tener clientes reales:

- Marketplace grande.
- Billing automatico self-service.
- Builder visual tipo React Flow.
- Registro publico de empresas.
- Planes self-service.
- RAG/documentos por defecto.
- Multi-idioma de plataforma completa.
- MongoDB sin caso de uso real.

Estas piezas solo entran si un cliente pagado las exige o si reducen trabajo
operativo real del equipo.

## 12. Estado de Avance

Implementado:

- Stack base con `api`, `worker`, `admin-web`, `reverse-proxy`, `postgres` y `redis`.
- Backend FastAPI multi-tenant.
- Panel Next.js.
- Auth interna con RBAC y scope por tenant.
- Modo produccion sin tokens demo.
- Health check que exige Postgres y Redis en produccion.
- Webhook Telegram por tenant con secret obligatorio.
- Webhook WhatsApp con verificacion de firma.
- Rate limiting basico.
- Persistencia compatible con Postgres.
- Fallback SQLite local/tests.
- Migraciones Alembic.
- Store de tenants en Postgres con bootstrap desde JSON.
- Admin API para crear, editar, pausar y reanudar tenants.
- Panel de clientes conectado a Admin API.
- Secret refs por variable de entorno.
- LangGraph como motor principal.
- ToolRouter para conectores externos.
- CalendarAdapter con citas persistidas.
- Locks Redis por conversacion.
- Debounce Redis para WhatsApp/Telegram.
- Cola Redis y contenedor worker.
- Reintentos y dead-letter queue.
- Backups automaticos opcionales.
- Logs JSON con redaccion de secretos.
- Metricas y alertas internas protegidas.
- Script de backup/restore.
- Historial de rotacion de secrets.
- Tests de aislamiento multi-tenant y canales.
- Transcripcion de audios WhatsApp conectada al worker (con fallback en linea).
- Validaciones de negocio por vertical.
- CORS restringido a dominios reales en produccion.
- Alertas externas por webhook + scheduler de retencion en el worker.
- Export de conversaciones y agregacion diaria de usage.
- Documentacion operativa/comercial: `backend/RUNBOOK.md`, `ONBOARDING.md`, `VERTICALES.md`, `POLITICAS.md`.
- Cotizador de remesas por tenant (`core/quotes.py`): matematica portada 1:1 del bot Brasper real
  (rangos de comision, cupon sobre comision, modo enviar/recibir), determinista y sin costo LLM;
  tasas/pares/cupon editables desde el panel. Migracion `0004` + nodo `handle_quote` en LangGraph.
- Derivacion a asesores: el handoff asigna la conversacion al asesor con menos carga
  (`auth.pick_advisor`, columna `conversations.assigned_to`), visible en el panel y con
  endpoints `GET /api/{t}/advisors` y `POST /api/{t}/conversations/{id}/assign`.
- Bot 100% configurable desde el panel (`web/app/bot`): system prompt, modelo/temperatura/max_tokens,
  handoff (numero/keywords/mensaje) y cotizador (tasas, cupon, rangos) via PATCH Admin API,
  verificado e2e (cambiar la tasa en la UI cambia la cotizacion del bot al instante).
- Pruebas: Gate hermetico 28/28 (`tests/run_checks.py`, unit+integracion+HTTP sin red) y smoke
  E2E real 14/14 contra el servidor vivo con Postgres y LLM reales (`tests/e2e_smoke.py`).

Pendiente:

- Prueba real de `docker compose up --build` en una maquina con Docker (no verificable en este entorno).
- Repositorios de datos separados por dominio (refactor opcional de `core/db.py`; no bloquea produccion).
- Dashboard operacional en el panel (los datos ya estan en `/api/ops/*`).
- SLA por plan/cliente y reporte mensual automatico.
- Pruebas de conversaciones largas por canal.
