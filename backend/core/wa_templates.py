"""Plantillas de WhatsApp (HSM) por tenant sobre la Cloud API de Meta.

Las plantillas (mensajes HSM / Highly Structured Messages) son el único
formato permitido para iniciar conversación fuera de la ventana de 24h.
Deben estar pre-aprobadas por Meta; aquí solo listamos su metadata y
construimos/enviamos el payload de envío `type=template`.

Contratos usados (NO reescribir):
  core/tenants.py -> whatsapp_token / whatsapp_phone_number_id
"""
import re

import httpx

from . import tenants as T

GRAPH = "https://graph.facebook.com/v21.0"

# Idioma por defecto de las plantillas si el tenant/llamada no especifica.
DEFAULT_LANGUAGE = "es"


# --- Defaults por vertical (fallback cuando el tenant no define 'templates') ---
_DEFAULTS_BY_VERTICAL = {
    "Salud": [
        {
            "name": "recordatorio_cita",
            "category": "UTILITY",
            "language": "es",
            "status": "APPROVED",
            "body": "Hola {{1}}, te recordamos tu cita de {{2}} el {{3}}. Responde CONFIRMAR o REAGENDAR.",
        },
    ],
    "Remesas / Fintech": [
        {
            "name": "confirmacion_operacion",
            "category": "UTILITY",
            "language": "es",
            "status": "APPROVED",
            "body": "Hola {{1}}, tu envío por {{2}} fue procesado. Código de seguimiento: {{3}}.",
        },
    ],
}

# Fallback genérico si el vertical no está mapeado.
_DEFAULT_GENERIC = [
    {
        "name": "hello_world",
        "category": "UTILITY",
        "language": "es",
        "status": "APPROVED",
        "body": "Hola {{1}}, gracias por contactarnos.",
    },
]


def _count_variables(body: str) -> int:
    """Número de placeholders {{n}} distintos en el cuerpo de la plantilla."""
    nums = {int(n) for n in re.findall(r"\{\{\s*(\d+)\s*\}\}", body or "")}
    return max(nums) if nums else 0


def _normalize(tpl: dict) -> dict:
    """Completa campos faltantes y calcula 'variables' desde el body."""
    body = tpl.get("body", "")
    return {
        "name": tpl.get("name", ""),
        "category": tpl.get("category", "UTILITY"),
        "language": tpl.get("language", DEFAULT_LANGUAGE),
        "status": tpl.get("status", "APPROVED"),
        "body": body,
        "variables": tpl.get("variables", _count_variables(body)),
    }


def list_templates(tenant: dict) -> list[dict]:
    """Plantillas del tenant: usa tenant['templates'] o un default por vertical.

    Devuelve [{name, category, language, status, body, variables}].
    """
    defined = tenant.get("templates")
    if defined:
        return [_normalize(t) for t in defined]
    vertical = tenant.get("vertical", "")
    defaults = _DEFAULTS_BY_VERTICAL.get(vertical, _DEFAULT_GENERIC)
    return [_normalize(t) for t in defaults]


def build_template_payload(template_name: str, language: str, params: list, to: str) -> dict:
    """Construye el objeto message type='template' de la Cloud API.

    Si hay params, añade el componente body con parameters type='text'.
    """
    params = params or []
    template: dict = {
        "name": template_name,
        "language": {"code": language or DEFAULT_LANGUAGE},
    }
    if params:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in params],
            }
        ]
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template,
    }


def _template_language(tenant: dict, template_name: str) -> str:
    """Idioma declarado para la plantilla en la config del tenant, si existe."""
    for t in list_templates(tenant):
        if t["name"] == template_name:
            return t["language"]
    return DEFAULT_LANGUAGE


async def send_template(tenant: dict, to: str, template_name: str,
                        params: list = None, language: str = None) -> dict:
    """Envía una plantilla vía POST /{phone_number_id}/messages.

    Devuelve {sent, status, detail}. Si falta token/pnid -> {sent:false, reason}.
    """
    token = T.whatsapp_token(tenant)
    pnid = T.whatsapp_phone_number_id(tenant)
    if not token or not pnid:
        return {"sent": False, "reason": f"Tenant {tenant['id']}: WhatsApp sin token/phone_number_id"}

    lang = language or _template_language(tenant, template_name)
    payload = build_template_payload(template_name, lang, params or [], to)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GRAPH}/{pnid}/messages", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
    ok = r.status_code == 200
    return {"sent": ok, "status": r.status_code, "detail": None if ok else r.text[:200]}
