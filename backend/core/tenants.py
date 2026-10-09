"""Carga y resolucion de config (single-tenant).

Lee `config/tenants.json` y extrae la llave 'brasper'.
"""
import copy
import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent                                  # raíz del repo
CONFIG_PATH = BASE_DIR / "config" / "tenants.json"

# Secretos: primero backend/.env si existe, luego el .env del repo
load_dotenv(BASE_DIR / ".env")
load_dotenv(REPO_DIR / ".env")

@lru_cache(maxsize=1)
def get_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Extraemos la configuración de 'brasper'
    tenant_cfg = data.get("tenants", {}).get("brasper", {})
    tenant_cfg["id"] = "brasper"
    return tenant_cfg

def reload_config() -> None:
    get_config.cache_clear()


def database_tenants_enabled() -> bool:
    """La configuración de producto es single-tenant y vive en JSON.

    Se conserva este helper para scripts operativos que muestran la fuente.
    """
    return False


def _require_brasper(tenant_id: str) -> str:
    normalized = (tenant_id or "").strip().lower()
    if normalized != "brasper":
        raise KeyError(normalized or tenant_id)
    return normalized


def _deep_merge(target: dict, patch: dict) -> dict:
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def _save_brasper(config: dict) -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("tenants", {})["brasper"] = {
        key: value for key, value in copy.deepcopy(config).items() if key != "id"
    }
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, CONFIG_PATH)
    reload_config()
    return get_config()


def upsert_tenant_config(tenant_id: str, config: dict) -> dict:
    _require_brasper(tenant_id)
    return _save_brasper(_deep_merge(get_config(), config))


def set_tenant_active(tenant_id: str, active: bool) -> dict:
    _require_brasper(tenant_id)
    return _save_brasper(_deep_merge(get_config(), {"active": bool(active)}))


_SECRET_REF_PATHS = {
    "llm.api_key_env",
    "whatsapp.token_env",
    "whatsapp.phone_number_id_env",
    "telegram.bot_token_env",
    "telegram.secret_token_env",
}


def set_secret_refs(tenant_id: str, refs: dict[str, str]) -> dict:
    _require_brasper(tenant_id)
    cfg = copy.deepcopy(get_config())
    for path, env_name in (refs or {}).items():
        if path not in _SECRET_REF_PATHS:
            raise ValueError(f"Ruta de secreto no permitida: {path}")
        if not env_name or not env_name.replace("_", "").isalnum():
            raise ValueError(f"Nombre de variable inválido para {path}")
        node = cfg
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = env_name
    return _save_brasper(cfg)


def whatsapp_connections(cfg: dict | None = None) -> list[dict]:
    """Conexiones WhatsApp de Brasper (varios números). Cada una resuelve sus secretos
    por referencia `*_env`. Modalidades: `standard` (Cloud API) o `coex` (número que
    sigue activo en la app WhatsApp Business). Si `whatsapp.connections` no existe se
    expone la configuración única histórica como conexión `default`."""
    if cfg is None:
        cfg = get_config()
    wa = cfg.get("whatsapp", {}) or {}
    out: list[dict] = []
    for i, c in enumerate(wa.get("connections") or []):
        if not isinstance(c, dict):
            continue
        out.append({
            "id": str(c.get("id") or f"wa{i + 1}"),
            "label": c.get("label") or c.get("id") or f"WhatsApp {i + 1}",
            "mode": "coex" if str(c.get("mode", "standard")).lower() == "coex" else "standard",
            "phone_number_id": resolve_secret(c, "phone_number_id", "phone_number_id_env"),
            "token": resolve_secret(c, "token", "token_env"),
            "waba_id": c.get("waba_id"),
            "display_phone": c.get("display_phone"),
        })
    if not out:
        pnid = whatsapp_phone_number_id(cfg)
        if pnid or whatsapp_token(cfg):
            out.append({"id": "default", "label": wa.get("label") or "WhatsApp principal",
                        "mode": "coex" if str(wa.get("mode", "standard")).lower() == "coex" else "standard",
                        "phone_number_id": pnid, "token": whatsapp_token(cfg),
                        "waba_id": wa.get("waba_id"), "display_phone": wa.get("display_phone")})
    return out


def resolve_whatsapp_connection(phone_number_id: str | None, cfg: dict | None = None) -> dict | None:
    if not phone_number_id:
        return None
    for c in whatsapp_connections(cfg):
        if c.get("phone_number_id") and str(c["phone_number_id"]) == str(phone_number_id):
            return c
    return None


def whatsapp_connection_by_id(connection_id: str | None, cfg: dict | None = None) -> dict | None:
    conns = whatsapp_connections(cfg)
    if connection_id:
        for c in conns:
            if c["id"] == connection_id:
                return c
        # An explicit missing connection must never send from another number.
        return {"id": connection_id, "unavailable": True}
    return conns[0] if len(conns) == 1 else None


def resolve_by_phone_number_id(phone_number_id: str) -> dict | None:
    cfg = get_config()
    return cfg if resolve_whatsapp_connection(phone_number_id, cfg) else None

def resolve_secret(cfg: dict, key: str, env_key: str) -> str | None:
    if cfg.get(key):
        return cfg[key]
    env_name = cfg.get(env_key)
    return os.getenv(env_name) if env_name else None

def llm_api_key(cfg: dict = None) -> str | None:
    if cfg is None: cfg = get_config()
    return resolve_secret(cfg.get("llm", {}), "api_key", "api_key_env")

def whatsapp_token(cfg: dict = None) -> str | None:
    if cfg is None: cfg = get_config()
    return resolve_secret(cfg.get("whatsapp", {}), "token", "token_env")

def whatsapp_phone_number_id(cfg: dict = None) -> str | None:
    if cfg is None: cfg = get_config()
    return resolve_secret(cfg.get("whatsapp", {}), "phone_number_id", "phone_number_id_env")

def telegram_token(cfg: dict = None) -> str | None:
    if cfg is None: cfg = get_config()
    return resolve_secret(cfg.get("telegram", {}), "bot_token", "bot_token_env")

def telegram_secret(cfg: dict = None) -> str | None:
    if cfg is None: cfg = get_config()
    return resolve_secret(cfg.get("telegram", {}), "secret_token", "secret_token_env")

def model_price(model: str) -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    p = data.get("pricing_usd_per_million", {})
    return p.get(model) or p.get("default", {"in": 0.5, "out": 1.5})
