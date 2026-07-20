# ONBOARDING / OFFBOARDING de clientes (tenants)

Guía operativa para el equipo de la agencia. Todos los endpoints van autenticados con
el header `X-Auth-Token` (token de un usuario con rol `owner`, `admin` o `builder` para
escribir; ver RBAC en `backend/core/auth.py`). Los ejemplos usan el proxy local
`http://localhost:8080` (en Docker); el contenedor `api` escucha directo en `:8002`.

> **Requisito para crear/editar tenants:** la escritura exige `TENANTS_SOURCE=database`
> (o Postgres activo vía `DATABASE_URL`). Con `config/tenants.json` como única fuente,
> los `POST/PATCH /api/admin/tenants` responden **409**. El JSON solo actúa como bootstrap
> inicial cuando la tabla `tenants` está vacía.

Variables base para los ejemplos:

```bash
export BASE=http://localhost:8080
export TOKEN=<token_owner_o_admin>   # header X-Auth-Token
export TID=cliente_nuevo             # tenant_id: [a-z0-9][a-z0-9_-]{1,62}
```

---

## ONBOARDING de un cliente nuevo

### 0. Prerrequisito: cargar secretos como variables de entorno

En producción (`APP_ENV=production`) **está prohibido** guardar secretos en claro dentro
del config del tenant: `POST/PATCH /api/admin/tenants` rechaza con **422** cualquier
`api_key`, `token`, `bot_token` o `secret_token` literal. Todo secreto se referencia por
el nombre de su variable de entorno con el sufijo `*_env`.

Añade los valores reales a `backend/.env` (nunca a git) y reinicia el stack para que el
proceso los lea:

```bash
# backend/.env  (ejemplo para un tenant "cliente_nuevo")
DEEPSEEK_API_KEY=sk-...                       # o la key del proveedor IA elegido
WA_PHONE_NUMBER_ID_CLIENTE=123456789012345    # phone_number_id de Meta
WA_TOKEN_CLIENTE=EAAG...                       # token de WhatsApp Cloud del cliente
TELEGRAM_TOKEN_CLIENTE=8123:AAH...            # token de BotFather
TELEGRAM_SECRET_CLIENTE=$(openssl rand -hex 32)  # secret del webhook Telegram
```

```bash
docker compose up -d   # recarga backend/.env
```

- [ ] Secretos del cliente añadidos a `backend/.env` con nombres `*_env` claros.
- [ ] Stack reiniciado para que el `api` y el `worker` vean las nuevas variables.

### 1. Crear el tenant (`POST /api/admin/tenants`)

El `config` se valida (ver `validate_tenant_config` en `core/tenants.py`): un tenant
activo **exige** `name`, `llm.model`, `llm.api_key_env` (o `api_key`, no en prod) y
`system_prompt`. Si defines bloques `whatsapp`/`telegram`/`handoff`, sus campos pasan a
ser obligatorios (ver validación abajo).

```bash
curl -sS -X POST "$BASE/api/admin/tenants" \
  -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "id": "'"$TID"'",
    "config": {
      "name": "Cliente Nuevo",
      "vertical": "Retail",
      "active": true,
      "fee_usd": 500,
      "languages": ["es"],
      "llm": {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "temperature": 0.5,
        "max_tokens": 500
      },
      "system_prompt": "Eres el asistente de Cliente Nuevo. Responde en español, breve y cordial.",
      "handoff": {
        "number": "51987654321",
        "keywords": ["asesor", "humano", "hablar con alguien"],
        "message": "Con gusto te conecto con un asesor 🤝 https://wa.me/{number}"
      },
      "whatsapp": {
        "phone_number_id_env": "WA_PHONE_NUMBER_ID_CLIENTE",
        "token_env": "WA_TOKEN_CLIENTE"
      },
      "telegram": {
        "bot_token_env": "TELEGRAM_TOKEN_CLIENTE",
        "secret_token_env": "TELEGRAM_SECRET_CLIENTE"
      }
    }
  }'
```

- [ ] Tenant creado sin error (respuesta `{"tenant": {...}}`, HTTP 200).
- [ ] **Proveedor IA** configurado (`llm.provider`, `llm.base_url`, `llm.model`,
      `llm.api_key_env`, y opcionalmente `temperature`/`max_tokens`).
- [ ] **system_prompt** definido (rol, idioma, tono, qué no debe inventar).
- [ ] **Handoff** definido si aplica: `handoff.number` (obligatorio si hay bloque handoff),
      `handoff.keywords`, `handoff.message` (usa `{number}`).

> Para editar después sin reescribir todo, usa el PATCH con merge profundo:
> ```bash
> curl -sS -X PATCH "$BASE/api/admin/tenants/$TID" \
>   -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" \
>   -d '{"config": {"system_prompt": "Nuevo prompt..."}}'
> ```

### 2. Registrar las refs de secretos (`POST /api/admin/tenants/{id}/secrets`)

Deja constancia auditable de qué variable de entorno respalda cada secreto (queda en la
tabla `secret_rotations`). Solo se aceptan estas 5 rutas; cualquier otra da **422**:
`llm.api_key_env`, `whatsapp.token_env`, `whatsapp.phone_number_id_env`,
`telegram.bot_token_env`, `telegram.secret_token_env`.

```bash
curl -sS -X POST "$BASE/api/admin/tenants/$TID/secrets" \
  -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "refs": {
      "llm.api_key_env": "DEEPSEEK_API_KEY",
      "whatsapp.token_env": "WA_TOKEN_CLIENTE",
      "whatsapp.phone_number_id_env": "WA_PHONE_NUMBER_ID_CLIENTE",
      "telegram.bot_token_env": "TELEGRAM_TOKEN_CLIENTE",
      "telegram.secret_token_env": "TELEGRAM_SECRET_CLIENTE"
    },
    "note": "alta cliente_nuevo"
  }'
```

- [ ] Refs de secretos registradas (verifica con
      `GET /api/admin/tenants/$TID/secrets/rotations`).

### 3. Conectar WhatsApp (Cloud API)

WhatsApp identifica al tenant por el `phone_number_id` en el webhook, así que el webhook
es **único y compartido**: `POST /webhook`.

1. En Meta, registra el webhook público `https://tu-dominio/webhook`.
2. Verificación de Meta (`GET /webhook`): usa el valor de `WHATSAPP_VERIFY_TOKEN`
   (o `WEBHOOK_VERIFY_TOKEN`/`VERIFY_TOKEN`; default `cauce-verify`).
3. Firma: en producción usa `WHATSAPP_REQUIRE_SIGNATURE=true` y define `META_APP_SECRET`
   (o `WHATSAPP_APP_SECRET`); los mensajes se validan con la cabecera
   `X-Hub-Signature-256`. Sin firma válida el webhook responde **403**.

- [ ] `WHATSAPP_VERIFY_TOKEN`, `META_APP_SECRET`, `WHATSAPP_REQUIRE_SIGNATURE=true` en `.env`.
- [ ] `whatsapp.phone_number_id_env` y `whatsapp.token_env` del tenant apuntan a variables cargadas.
- [ ] Webhook `https://tu-dominio/webhook` verificado en Meta.

### 4. Conectar Telegram

Telegram no trae la identidad del bot en el update, así que el tenant se resuelve por la
URL: `POST /telegram/webhook/{tenant_id}`. El `secret_token` por tenant se valida contra
la cabecera `X-Telegram-Bot-Api-Secret-Token` (en producción es **obligatorio**: sin él
el webhook responde **503**).

Con URL pública HTTPS, registra el webhook (esto envía el secret a Telegram automáticamente):

```bash
curl -sS -X POST "$BASE/api/$TID/telegram/set-webhook" \
  -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"base_url": "https://tu-dominio"}'

# Diagnóstico (getMe + getWebhookInfo):
curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/$TID/telegram/info"
```

- [ ] Bot creado en BotFather; `TELEGRAM_TOKEN_*` y `TELEGRAM_SECRET_*` en `.env`.
- [ ] `set-webhook` OK; `telegram/info` muestra el bot correcto y el webhook activo.
      El webhook público queda en `https://tu-dominio/telegram/webhook/$TID`.

### 5. Validar la configuración y activar

```bash
# ¿El tenant aparece con IA y canales OK?  (fuente + flags de configuración)
curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/admin/tenants"        # lista completa (incluye inactivos)
curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/tenants"              # vista con consumo/margen

# CLI equivalente (marca llm✓/llm✗ y canales detectados):
cd backend && ../.venv/bin/python manage.py list-tenants
```

En `GET /api/tenants` confirma: `llm_key_configured: true`, `whatsapp_configured: true`
y/o `telegram_configured: true`, y `handoff_number` correcto.

Si lo creaste inactivo (o hubo una pausa), reanúdalo:

```bash
curl -sS -X POST "$BASE/api/admin/tenants/$TID/resume" -H "X-Auth-Token: $TOKEN"
```

- [ ] `llm_key_configured` = true y canales esperados en true.
- [ ] Tenant `active: true` (reanudado si hacía falta).

### 6. Prueba de humo

```bash
# Webchat / API por tenant (requiere permiso chat:test)
curl -sS -X POST "$BASE/api/$TID/chat" \
  -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"message": "Hola, ¿qué servicios ofrecen?", "user_ref": "smoke-test"}'
```

- [ ] La respuesta llega con `response` no vacío (HTTP 200; 502 indica error del LLM).
- [ ] WhatsApp: enviar un mensaje real al número y verificar respuesta del bot.
- [ ] Telegram: escribir al bot y verificar respuesta + botón de handoff si aplica.
- [ ] Conversación registrada:
      `curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/$TID/conversations"`.
- [ ] Consumo/costo empieza a acumularse:
      `curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/admin/tenants/$TID/usage"`.

---

## OFFBOARDING de un cliente

### 1. Pausar el tenant (corta la operación)

Pausar deja el tenant inactivo: deja de resolverse en `/webhook`, `/telegram/webhook/*`
y `/api/{tenant}/chat` (responden **404** "tenant no existe o está inactivo"). Es
reversible y queda auditado.

```bash
curl -sS -X POST "$BASE/api/admin/tenants/$TID/pause" -H "X-Auth-Token: $TOKEN"
```

- [ ] Tenant pausado; `GET /api/admin/tenants` lo muestra con `active: false`.

### 2. Exportar conversaciones (antes de borrar)

No hay endpoint de exportación masiva; se exporta leyendo los endpoints de lectura
(rol con `conversations:read`) y guardando el JSON.

```bash
# Índice de conversaciones del tenant
curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/$TID/conversations" \
  > export_${TID}_conversations.json

# Mensajes de cada conversación (itera con jq sobre los IDs)
for cid in $(jq -r '.conversations[].id' export_${TID}_conversations.json); do
  curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/$TID/conversations/$cid" \
    > "export_${TID}_conv_${cid}.json"
done

# Consumo/usage y citas (si aplica) para cierre de cuentas
curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/admin/tenants/$TID/usage" > export_${TID}_usage.json
curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/$TID/appointments"        > export_${TID}_appointments.json
```

Toma también un backup completo de la base antes de borrar nada:

```bash
docker compose exec api python backup.py create
docker compose exec api python backup.py list
```

- [ ] Conversaciones, usage y (si aplica) citas exportados y entregados/archivados.
- [ ] Backup de base de datos creado y verificado.

### 3. Revocar tokens y secrets del cliente

Los secretos viven en `backend/.env`, no en la base. Revocar = invalidar en el origen y
quitar del entorno.

- WhatsApp: revoca/rota el token en Meta (Business Manager) y borra/limpia `WA_TOKEN_*`
  y `WA_PHONE_NUMBER_ID_*` del `.env`.
- Telegram: revoca el bot con BotFather (`/revoke` o `/deletebot`) y borra el webhook:
  ```bash
  curl -sS -X POST "$BASE/api/$TID/telegram/delete-webhook" -H "X-Auth-Token: $TOKEN"
  ```
  Luego quita `TELEGRAM_TOKEN_*` y `TELEGRAM_SECRET_*` del `.env`.
- LLM: si la key era exclusiva del cliente, rótala/revócala con el proveedor y limpia su `*_env`.
- Aplica los cambios de `.env`: `docker compose up -d`.
- Revoca accesos de panel del cliente (si tenía usuario scoped): rota su token con
  `manage.py create-admin` (para owners) o desactiva su usuario en `panel_users`.

- [ ] Token de WhatsApp revocado en Meta y variable limpia.
- [ ] Bot de Telegram revocado, webhook borrado y variables limpias.
- [ ] Key de LLM del cliente rotada/revocada si era dedicada.
- [ ] Usuarios de panel del cliente sin acceso; stack recargado.

### 4. Borrar datos según retención

No existe endpoint de purga; el borrado se hace con SQL en ventana de mantenimiento
(tras confirmar el backup del paso 2). Las tablas con datos del tenant son
`messages`, `conversations`, `usage_events`, `appointments`, `audit_events` y
`secret_rotations` (todas indexadas por `tenant_id`).

```bash
# Ventana de mantenimiento
docker compose exec postgres psql -U cauce -d cauce <<SQL
BEGIN;
DELETE FROM messages        WHERE tenant_id = '$TID';
DELETE FROM conversations   WHERE tenant_id = '$TID';
DELETE FROM appointments    WHERE tenant_id = '$TID';
DELETE FROM usage_events    WHERE tenant_id = '$TID';   -- conservar si se necesita para facturación histórica
DELETE FROM secret_rotations WHERE tenant_id = '$TID';
-- audit_events: conservar por trazabilidad salvo que la política de retención exija borrarlos
DELETE FROM tenants         WHERE id = '$TID';          -- baja definitiva (opcional; ver paso 5)
COMMIT;
SQL
```

- [ ] Datos borrados según la política de retención acordada (o conservados los que exija facturación/auditoría).
- [ ] Backup previo disponible por si hay que revertir.

### 5. Confirmar la baja

```bash
# Ya no debe aparecer (o aparecer inactivo) en la lista
curl -sS -H "X-Auth-Token: $TOKEN" "$BASE/api/admin/tenants"

# Los canales ya no resuelven (404 esperado)
curl -sS -X POST "$BASE/api/$TID/chat" -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" -d '{"message":"test"}'   # -> 404

cd backend && ../.venv/bin/python manage.py list-tenants
```

- [ ] Tenant ausente/inactivo en `list-tenants` y en `GET /api/admin/tenants`.
- [ ] `/api/{tenant}/chat`, `/webhook` y `/telegram/webhook/{tenant}` ya no responden por él.
- [ ] Secrets revocados, datos tratados según retención y baja comunicada al cliente.

---

## Datos que pide cada canal

| Canal | Bloque en config del tenant | Refs de secreto (`*_env`, ir a `.env`) | Otros datos / obligatorios | Webhook / entrada |
|---|---|---|---|---|
| **Webchat / API** | `llm`, `system_prompt` | `llm.api_key_env` | `llm.model`, `llm.base_url`, `llm.provider`; opc. `temperature`, `max_tokens` | `POST /api/{tenant}/chat` (header `X-Auth-Token`, permiso `chat:test`) |
| **WhatsApp Cloud API** | `whatsapp` | `whatsapp.token_env`, `whatsapp.phone_number_id_env` | `phone_number_id` de Meta; a nivel plataforma: `WHATSAPP_VERIFY_TOKEN`, `META_APP_SECRET`, `WHATSAPP_REQUIRE_SIGNATURE=true` | `POST /webhook` (compartido; resuelve tenant por `phone_number_id`); verificación `GET /webhook`; firma `X-Hub-Signature-256` |
| **Telegram Bot API** | `telegram` | `telegram.bot_token_env`, `telegram.secret_token_env` | token de BotFather; secret del webhook por tenant; opc. `handoff_buttons` | `POST /telegram/webhook/{tenant_id}` (resuelve por URL); cabecera `X-Telegram-Bot-Api-Secret-Token`; alta con `POST /api/{tenant}/telegram/set-webhook` |
| **Handoff (transversal)** | `handoff` | — | `handoff.number` (obligatorio si hay bloque); `handoff.keywords`, `handoff.message` (`{number}`) | Se dispara dentro del motor; en Telegram usa botones inline |

> Nota: en desarrollo (`APP_ENV` distinto de `production`) se admiten valores directos
> (`api_key`, `token`, `bot_token`, `secret_token`) y usuarios demo con tokens legibles
> (`demo-owner`, etc.). En producción esos atajos están bloqueados/purgados.
