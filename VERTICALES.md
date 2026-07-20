# VERTICALES.md — Plantillas de configuración de tenant por vertical

Guía de configuración de tenants para la plataforma de bots (WhatsApp / Telegram / webchat).
Todos los bloques JSON son **compatibles con `backend/config/tenants.json`** (clave dentro de `tenants.<tenant_id>`)
y con el payload del endpoint `POST /api/admin/tenants` (`{ "id": "<tenant_id>", "config": { ... } }`).

Verificado contra el código real:
- Esquema y normalización: `backend/core/tenants.py` (`_normalize_config`, `validate_tenant_config`, `_SECRET_REF_PATHS`).
- Calendario/citas: `backend/core/calendar_adapter.py` (`calendar.enabled`, `calendar.timezone`, `calendar.specialties`).
- APIs externas: `backend/core/connectors.py` (`externalApis`, `auth.type`, `endpoints[].{tool,method,path,desc,output_var}`).
- LLM: `backend/core/llm.py` (`provider`, `base_url`, `model`, `api_key_env`, `temperature`, `max_tokens`).
- Handoff: `backend/core/agent_graph.py` (`handoff.keywords`, `handoff.number`, `handoff.message` con placeholder `{number}`).
- Rechazo de secretos en claro / refs de secretos: `backend/api/routes.py`.

---

## Reglas transversales (aplican a todas las verticales)

1. **`tenant_id`**: minúsculas, números, guion o guion bajo (regex `^[a-z0-9][a-z0-9_-]{1,62}$`).
2. **Secretos por referencia (`*_env`)**: en producción (`APP_ENV=production`) **está prohibido** guardar valores en claro.
   Las claves `api_key`, `token`, `bot_token`, `secret_token` se rechazan con **HTTP 422** en `POST/PATCH /api/admin/tenants`.
   Usa siempre las variantes `*_env` que apuntan al nombre de la variable de entorno.
3. **Rutas de secreto permitidas** (endpoint `POST /api/admin/tenants/{id}/secrets`, campo `refs`):
   `llm.api_key_env`, `whatsapp.token_env`, `whatsapp.phone_number_id_env`, `telegram.bot_token_env`, `telegram.secret_token_env`.
   Cualquier otra ruta se rechaza (`Ruta de secret no permitida`).
4. **Campos base normalizados**: `name` (obligatorio), `vertical`, `active` (bool, default `true`), `fee_usd` (float, default `0`).
5. **Canales opcionales**: los bloques `whatsapp` y `telegram` son opcionales, pero **si se incluyen** deben traer sus `*_env` (ver validación).
6. **Aplicar cambios**: tras crear/editar por API en producción se encola `tenant.changed`; con `config/tenants.json` recuerda que se cachea (`reload_config()` / reinicio).

---

## 1) Salud (vertical: `Salud`)

Requiere `calendar` con `specialties` para agendar citas (el `calendar_adapter` extrae nombre, DNI, especialidad y fecha/hora).

```json
{
  "name": "Clínica Vida",
  "vertical": "Salud",
  "active": true,
  "fee_usd": 400,
  "languages": ["es"],
  "llm": {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "temperature": 0.5,
    "max_tokens": 400
  },
  "system_prompt": "Eres el asistente de Clínica Vida. Informas sobre especialidades, horarios y ayudas a agendar citas. Para agendar pide: nombre completo, DNI, especialidad y fecha/hora. Si el usuario describe una urgencia, recomienda acudir a emergencias de inmediato. No des diagnósticos médicos. Responde en español, breve y empático.",
  "calendar": {
    "enabled": true,
    "timezone": "America/Lima",
    "specialties": ["medicina general", "pediatría", "ginecología", "odontología"]
  },
  "handoff": {
    "number": "51999555111",
    "keywords": ["asesor", "humano", "recepción", "hablar con alguien", "urgente"],
    "message": "Te comunico con recepción 🏥 Escríbenos directo: https://wa.me/{number}"
  },
  "whatsapp": {
    "phone_number_id_env": "WA_PHONE_NUMBER_ID_CLINICA",
    "token_env": "WA_TOKEN_CLINICA"
  },
  "telegram": {
    "bot_token_env": "TELEGRAM_TOKEN_CLINICA",
    "secret_token_env": "TELEGRAM_SECRET_CLINICA",
    "handoff_buttons": [
      { "text": "Escribir a recepción", "url": "https://wa.me/51999555111" }
    ]
  }
}
```

Notas:
- Si `calendar.specialties` se omite, el adaptador usa un default interno (`medicina general`, `pediatria`, `ginecologia`, `odontologia`), pero para producción **declárala explícitamente** por vertical/tenant.
- `handoff.message` sustituye `{number}` por `handoff.number` en tiempo de ejecución.

---

## 2) Reservas (vertical: `Reservas`)

Misma mecánica de calendario que salud, pero `specialties` representa el catálogo de servicios/recursos reservables (mesas, canchas, salas, tratamientos).

```json
{
  "name": "Bella Spa Reservas",
  "vertical": "Reservas",
  "active": true,
  "fee_usd": 350,
  "languages": ["es"],
  "llm": {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "temperature": 0.5,
    "max_tokens": 400
  },
  "system_prompt": "Eres el asistente de reservas de Bella Spa. Ayudas a reservar servicios y a consultar disponibilidad. Para reservar pide: nombre completo, documento, servicio y fecha/hora. Responde en español, breve y cordial.",
  "calendar": {
    "enabled": true,
    "timezone": "America/Lima",
    "specialties": ["masaje relajante", "facial", "manicure", "pedicure"]
  },
  "handoff": {
    "number": "51988777666",
    "keywords": ["asesor", "humano", "recepción", "hablar con alguien"],
    "message": "Te conecto con recepción 💆 Escríbenos directo: https://wa.me/{number}"
  },
  "whatsapp": {
    "phone_number_id_env": "WA_PHONE_NUMBER_ID_SPA",
    "token_env": "WA_TOKEN_SPA"
  }
}
```

Notas:
- En reservas puedes omitir el bloque `telegram` si el tenant solo opera por WhatsApp/webchat.
- El `calendar_adapter` reconoce intención con palabras como *cita, agendar, reservar, reserva, turno, book, schedule*.

---

## 3) Retail (vertical: `Retail`)

Usa `externalApis` para conectar con ERP/e-commerce (stock, pedidos, tracking). El `tool_router` mapea el mensaje del usuario al `tool` correcto y extrae variables `{{...}}` del `path`.

```json
{
  "name": "TiendaMax",
  "vertical": "Retail",
  "active": true,
  "fee_usd": 600,
  "languages": ["es", "en"],
  "llm": {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "temperature": 0.6,
    "max_tokens": 500
  },
  "system_prompt": "Eres el asistente de TiendaMax. Ayudas a consultar stock por SKU, estado de pedidos por tracking y a crear pedidos. Si falta un dato para ejecutar una consulta, pídelo con claridad. Responde en el idioma del usuario, breve y cordial.",
  "handoff": {
    "number": "51955111222",
    "keywords": ["asesor", "humano", "hablar con alguien", "advisor"],
    "message": "Te conecto con un asesor 🛍️ Escríbenos directo: https://wa.me/{number}"
  },
  "externalApis": {
    "erp": {
      "name": "ERP de stock y pedidos",
      "base_url": "https://erp.tiendamax.example",
      "auth": {
        "type": "bearer",
        "token_env": "ERP_TOKEN_TIENDAMAX"
      },
      "default_headers": { "Accept": "application/json" },
      "endpoints": [
        { "tool": "consultar_stock", "method": "GET", "path": "/v1/stock?sku={{sku}}", "desc": "Consulta el stock disponible por SKU", "output_var": "stock" },
        { "tool": "estado_pedido", "method": "GET", "path": "/v1/pedidos/{{tracking}}", "desc": "Consulta el estado de un pedido por código de tracking" },
        { "tool": "crear_pedido", "method": "POST", "path": "/v1/pedidos", "desc": "Crea un pedido; envía cliente e items en el body JSON" }
      ]
    }
  },
  "whatsapp": {
    "phone_number_id_env": "WA_PHONE_NUMBER_ID_TIENDAMAX",
    "token_env": "WA_TOKEN_TIENDAMAX"
  },
  "telegram": {
    "bot_token_env": "TELEGRAM_TOKEN_TIENDAMAX",
    "secret_token_env": "TELEGRAM_SECRET_TIENDAMAX"
  }
}
```

Notas sobre `externalApis` (verificado en `core/connectors.py`):
- `auth.type` admite: `none`, `api_key_header` (usa `header`, default `X-Api-Key`), `bearer`. Con `api_key_header`/`bearer` es obligatorio `token` o `token_env` resoluble.
- Interpolación: cualquier `{{var}}` en `path` (incluida la query) se reemplaza urlencoded; en `POST/PUT/PATCH` las variables no usadas en el path se envían como JSON en el body.
- `output_var` es opcional (nombre lógico de la salida).

---

## 4) Servicios (vertical: `Servicios`)

Vertical genérica de servicios (soporte, agendamiento de visitas técnicas, consultas de estado). Puede combinar `externalApis` y, si aplica, `calendar`.

```json
{
  "name": "TecniHogar Servicios",
  "vertical": "Servicios",
  "active": true,
  "fee_usd": 500,
  "languages": ["es"],
  "llm": {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "temperature": 0.6,
    "max_tokens": 500
  },
  "system_prompt": "Eres el asistente de TecniHogar. Ayudas a consultar el estado de tickets de servicio y a registrar solicitudes de visita técnica. Pide los datos necesarios (número de ticket o dirección) según corresponda. Responde en español, breve y cordial.",
  "handoff": {
    "number": "51944333222",
    "keywords": ["asesor", "humano", "hablar con alguien", "técnico"],
    "message": "Te conecto con un asesor 🛠️ Escríbenos directo: https://wa.me/{number}"
  },
  "externalApis": {
    "crm": {
      "name": "CRM de tickets",
      "base_url": "https://crm.tecnihogar.example",
      "auth": {
        "type": "api_key_header",
        "header": "X-Api-Key",
        "token_env": "CRM_APIKEY_TECNIHOGAR"
      },
      "default_headers": { "Accept": "application/json" },
      "endpoints": [
        { "tool": "estado_ticket", "method": "GET", "path": "/api/tickets/{{ticket}}", "desc": "Consulta el estado de un ticket de servicio por su número", "output_var": "ticket" },
        { "tool": "crear_solicitud", "method": "POST", "path": "/api/solicitudes", "desc": "Registra una solicitud de visita técnica con los datos del cliente" }
      ]
    }
  },
  "whatsapp": {
    "phone_number_id_env": "WA_PHONE_NUMBER_ID_TECNIHOGAR",
    "token_env": "WA_TOKEN_TECNIHOGAR"
  }
}
```

---

## Reglas de validación por vertical

Esta sección la consume el código de validación. Se divide en:
- **(A) Reglas ya aplicadas hoy** por `validate_tenant_config()` en `backend/core/tenants.py` (comunes a toda vertical).
- **(B) Reglas específicas por vertical** (a aplicar/extender en el validador; hoy `calendar.specialties` y `externalApis` **no** son obligatorios en `validate_tenant_config` — se recomienda hacerlas obligatorias por vertical antes de activar).

### (A) Reglas comunes ya vigentes (todas las verticales)

`validate_tenant_config()` solo exige lo siguiente cuando `active` es `true` (si `active=false`, solo valida `name`):

- `name`: obligatorio (no vacío) — **siempre**, activo o no.
- `llm`: obligatorio y debe ser objeto.
  - `llm.model`: obligatorio.
  - `llm.api_key_env` (o `llm.api_key` en dev): obligatorio.
- `system_prompt`: obligatorio.
- Si existe bloque `whatsapp` no vacío:
  - `whatsapp.phone_number_id_env` (o `phone_number_id`): obligatorio.
  - `whatsapp.token_env` (o `token`): obligatorio.
- Si existe bloque `telegram` no vacío:
  - `telegram.bot_token_env` (o `bot_token`): obligatorio.
  - `telegram.secret_token_env` (o `secret_token`): obligatorio.
- Si existe bloque `handoff` no vacío:
  - `handoff.number`: obligatorio.
- En producción: ninguna clave `api_key`, `token`, `bot_token`, `secret_token` en claro (rechazo 422).

### (B) Obligatorios por vertical antes de activar

#### Salud
- `vertical` = `"Salud"`.
- `calendar`: OBLIGATORIO.
  - `calendar.enabled`: `true` (obligatorio para que el bot agende).
  - `calendar.timezone`: obligatorio (IANA, p. ej. `America/Lima`).
  - `calendar.specialties`: obligatorio, lista no vacía de strings.
- `system_prompt`: debe pedir explícitamente nombre completo, DNI/documento, especialidad y fecha/hora (campos que extrae `calendar_adapter`).
- Al menos un canal activo (`whatsapp` o `telegram`) o uso vía webchat/API.

#### Reservas
- `vertical` = `"Reservas"`.
- `calendar`: OBLIGATORIO.
  - `calendar.enabled`: `true`.
  - `calendar.timezone`: obligatorio (IANA).
  - `calendar.specialties`: obligatorio, lista no vacía (catálogo de servicios/recursos reservables).
- `system_prompt`: debe pedir nombre completo, documento, servicio y fecha/hora.

#### Retail
- `vertical` = `"Retail"`.
- `externalApis`: OBLIGATORIO, al menos un conector con `endpoints` no vacío.
- Por cada conector:
  - `base_url`: obligatorio (no vacío).
  - `auth.type` ∈ {`none`, `api_key_header`, `bearer`}. Si es `api_key_header` o `bearer`: `token_env` (o `token`) obligatorio y resoluble.
  - `auth.header`: obligatorio solo si `auth.type` = `api_key_header` (default `X-Api-Key` si se omite).
- Por cada endpoint: `tool` y `path` obligatorios; `method` recomendado (default `GET`).
- `system_prompt`: debe describir las operaciones disponibles (stock, pedidos, tracking) y pedir los datos que faltan.

#### Servicios
- `vertical` = `"Servicios"`.
- `externalApis`: OBLIGATORIO, al menos un conector con `endpoints` no vacío (mismas reglas de conector/endpoint que Retail).
- `calendar`: OPCIONAL; si se incluye con `enabled=true`, entonces `calendar.timezone` y `calendar.specialties` pasan a ser obligatorios (igual que Reservas).
- `system_prompt`: debe describir las operaciones disponibles y pedir los datos que faltan.

### Reglas de conector/endpoint (reutilizables por Retail y Servicios)

- `externalApis.<key>.base_url`: obligatorio, no vacío.
- `externalApis.<key>.auth.type` ∈ {`none`, `api_key_header`, `bearer`}; cualquier otro valor = inválido.
- Si `auth.type` ∈ {`api_key_header`, `bearer`}: `token_env` (preferido) o `token` obligatorio y resoluble a un valor no vacío.
- `externalApis.<key>.endpoints`: lista no vacía.
- Cada `endpoint`: `tool` obligatorio (único dentro del conector), `path` obligatorio; `method` por defecto `GET`.
- Toda variable `{{var}}` usada en un `path` debe poder resolverse en tiempo de ejecución (se extrae del mensaje del usuario o del body).
