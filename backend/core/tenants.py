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
