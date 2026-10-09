"""Feature flags del bot Brasper (despliegue gradual, etapa 5 del plan de atención autónoma).

Se leen de `tenants.json` → `tenants.brasper.features` (editable por la Admin API con
deep-merge). Si una flag no está definida se usa el valor por defecto de abajo. Las
flags NO son secretos: pueden vivir en el archivo versionado.
"""
from __future__ import annotations

from core import tenants as T

DEFAULTS: dict[str, bool] = {
    "knowledge": True,            # FAQ con fuente (etapa 1)
    "status_intent": True,        # "¿ya llegó mi envío?" -> derivación con resumen (sin API de estado)
    "anti_loop": True,            # límite de repeticiones del bot
    "audio_confirmation": True,   # confirmar cifras ambiguas en audios
    "webhook_dedup": True,        # deduplicación de webhooks por id de mensaje
    "presence_required": False,   # asignar solo a asesores disponibles con heartbeat vigente
    "coex": False,                # ecos de la app WhatsApp Business (coexistencia)
    "campaigns": False,           # requiere API Brasper con migración 083 y validación previa
    "operation_status": False,    # consulta privada con identidad verificada; habilitar tras validar API
    "identity_link": False,       # vinculación Telegram/webchat desde la cuenta Brasper; requiere BRASPER_IA_GRANT_KEY
}


def all_flags() -> dict[str, bool]:
    cfg = (T.get_config().get("features") or {}) if T.get_config() else {}
    out = dict(DEFAULTS)
    for k, v in cfg.items():
        out[k] = bool(v)
    return out


def enabled(name: str) -> bool:
    return all_flags().get(name, False)
