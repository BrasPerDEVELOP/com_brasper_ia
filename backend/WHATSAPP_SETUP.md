# Activar WhatsApp Cloud API (Brasper)

Instructivo para conectar el canal **WhatsApp Cloud API** siguiendo la
documentación oficial de Meta. El lanzamiento inicial es **solo Telegram**;
este canal queda 100% preparado en código y se activa llenando variables.

> El código ya cumple el estándar de Meta y **no requiere cambios**:
> - Graph API `v21.0` (`core/whatsapp.py`).
> - Verificación de webhook con `hub.mode` / `hub.verify_token` / `hub.challenge`
>   (`GET /webhook`).
> - Validación de firma `X-Hub-Signature-256` = `sha256=HMAC-SHA256(app_secret, body)`
>   (`POST /webhook`), obligatoria con `WHATSAPP_REQUIRE_SIGNATURE=true`.
> - Ruteo multi-tenant por `phone_number_id`.

---

## 0. Prerrequisitos

- Cuenta de **Meta Business** (business.facebook.com).
- Una **App** de tipo *Business* en developers.facebook.com con el producto
  **WhatsApp** agregado.
- Un **número de teléfono** dedicado (que no esté en la app de WhatsApp normal).
- El backend accesible por **HTTPS público** (Caddy ya lo resuelve con TLS
  automático; ver `backend/DEPLOY.md`).

---

## 1. Obtener los identificadores

En **App Dashboard → WhatsApp → API Setup** anota:

| Dato | Dónde | Variable en `backend/.env` |
|---|---|---|
| **Phone number ID** | API Setup (junto al número) | `WA_PHONE_NUMBER_ID_BRASPER` |
| **WhatsApp Business Account ID** (WABA ID) | API Setup | *(solo para gestión; no va al `.env`)* |

## 2. Token PERMANENTE (System User)

El token temporal de "API Setup" caduca en 24 h. Para producción se usa un
**System User** (Business Settings → **System users**):

1. Crea un System User (rol *Admin* o *Employee*).
2. **Assign assets**: asigna la **App** y la **WhatsApp Account** con control total.
3. **Generate token** seleccionando estos permisos (oficiales de Meta):
   - `business_management`
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
4. Copia el token y guárdalo en:

```
wp_key=EAAG...   # token permanente del System User (NO el temporal)
```

## 3. Número de producción

En **WhatsApp Manager** agrega y verifica el número de negocio, define el
**display name** y espera su aprobación. Hasta aprobarlo, solo se puede enviar a
números de prueba registrados.

## 4. Webhook

En **App Dashboard → WhatsApp → Configuration**:

1. **Callback URL:**

   ```
   https://<SITE_ADDRESS>/webhook
   ```

   (ej. `https://panel.tu-dominio.com/webhook`)

2. **Verify token:** el mismo valor que pongas en `WHATSAPP_VERIFY_TOKEN`.
   Genera uno con `openssl rand -hex 16`.

   Al pulsar *Verify and save*, Meta hace `GET /webhook` con `hub.mode=subscribe`,
   `hub.verify_token` y `hub.challenge`; el backend responde el `challenge` si el
   token coincide. ✅

3. **Webhook fields:** suscríbete al campo **`messages`** (entrantes + estados).

4. **App secret → firma:** copia el **App Secret** (Settings → Basic) en
   `META_APP_SECRET` y mantén `WHATSAPP_REQUIRE_SIGNATURE=true`. Cada `POST`
   entrante se valida con `X-Hub-Signature-256`; si la firma no cuadra, el
   backend responde `403`.

## 5. Variables (resumen)

```bash
# backend/.env
WHATSAPP_VERIFY_TOKEN=<cadena propia = la del panel de Meta>
META_APP_SECRET=<App Secret de Meta>
WHATSAPP_REQUIRE_SIGNATURE=true
WA_PHONE_NUMBER_ID_BRASPER=<Phone number ID>
wp_key=<token permanente del System User>
```

> Los nombres de variable por tenant los define `backend/config/tenants.json`
> (bloque `whatsapp`: `phone_number_id_env` y `token_env`). Para Brasper hoy son
> `WA_PHONE_NUMBER_ID_BRASPER` y `wp_key`.

## 6. Verificación

```bash
# 1) Handshake del webhook (debe imprimir "ping"):
curl "https://<SITE_ADDRESS>/webhook?hub.mode=subscribe&hub.verify_token=<WHATSAPP_VERIFY_TOKEN>&hub.challenge=ping"

# 2) El panel debe reportar el canal configurado:
curl -H "X-Auth-Token: $PANEL_ADMIN_TOKEN" https://<SITE_ADDRESS>/api/tenants
#   -> brasper: "whatsapp_configured": true
```

Luego, desde el número de prueba/producción, envía un mensaje al número de
Brasper: debe llegar como conversación en el panel y el bot responder en el
idioma del usuario.

## 7. Notas

- Un `POST /webhook` sin `META_APP_SECRET` configurado y con
  `WHATSAPP_REQUIRE_SIGNATURE=true` se **rechaza** (403): es el comportamiento
  correcto en producción.
- El envío de **plantillas** (mensajes iniciados por el negocio fuera de la
  ventana de 24 h) requiere plantillas aprobadas; ya hay ejemplos en
  `tenants.json` (`templates`).
- La atención sigue siendo **100% in-chat** (sin derivar a otro número), igual
  que en Telegram.

---

### Referencias oficiales de Meta

- Get Started (Cloud API): <https://developers.facebook.com/docs/whatsapp/cloud-api/get-started>
- Configurar webhooks: <https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks>
- Webhooks (verificación y firma): <https://developers.facebook.com/docs/graph-api/webhooks/getting-started>
- System Users / tokens permanentes: <https://developers.facebook.com/docs/whatsapp/business-management-api/get-started>
