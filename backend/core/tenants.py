"""Carga y resolucion de tenants.

En local usa `config/tenants.json`. En produccion usa la tabla `tenants`
cuando existe `DATABASE_URL`, con el JSON como bootstrap inicial.
"""
from __future__ import annotations

import copy
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import db

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent                                  # raíz del repo
CONFIG_PATH = BASE_DIR / "config" / "tenants.json"
_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_REF_PATHS = {
    "llm.api_key_env",
    "whatsapp.token_env",
    "whatsapp.phone_number_id_env",
    "telegram.bot_token_env",
    "telegram.secret_token_env",
}

# Secretos: primero backend/.env si existe, luego el .env del repo (bot actual)
load_dotenv(BASE_DIR / ".env")
load_dotenv(REPO_DIR / ".env")


@lru_cache(maxsize=1)
def _config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def reload_config() -> None:
    _config.cache_clear()


from .util import now_iso as _now  # noqa: E402  (timestamp UTC único, ver core/util.py)


def _file_tenants() -> dict:
    return _config().get("tenants", {})


def database_tenants_enabled() -> bool:
    source = (os.getenv("TENANTS_SOURCE") or "").strip().lower()
    if source in {"file", "json"}:
        return False
    if source in {"database", "db", "postgres"}:
        return True
    return db.is_postgres()


def _decode_config(value: Any) -> dict:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


from .util import as_bool as _as_bool  # noqa: E402  (parseo bool único, ver core/util.py)


def _row_to_tenant(row: Any) -> dict:
    cfg = _decode_config(row["config_json"])
    cfg["name"] = row["name"]
    cfg["vertical"] = row["vertical"] or cfg.get("vertical", "")
    cfg["active"] = _as_bool(row["active"])
    return cfg


def _validate_tenant_id(tenant_id: str) -> str:
    tenant_id = (tenant_id or "").strip().lower()
    if not _TENANT_ID_RE.match(tenant_id):
        raise ValueError("tenant_id debe usar letras minusculas, numeros, guion o underscore")
    return tenant_id


def _normalize_config(tenant_id: str, config: dict) -> dict:
    cfg = copy.deepcopy(config or {})
    cfg.pop("id", None)
    cfg["name"] = str(cfg.get("name") or tenant_id).strip()[:120] or tenant_id
    cfg["vertical"] = str(cfg.get("vertical") or "").strip()[:120]
    cfg["active"] = _as_bool(cfg.get("active", True))
    cfg["fee_usd"] = float(cfg.get("fee_usd") or 0)
    return cfg


def validate_tenant_config(config: dict) -> list[str]:
    errors: list[str] = []
    if not str(config.get("name") or "").strip():
        errors.append("name es obligatorio")
    if not config.get("active", True):
        return errors

    llm_cfg = config.get("llm")
    if not isinstance(llm_cfg, dict):
        errors.append("llm es obligatorio para tenants activos")
    else:
        if not str(llm_cfg.get("model") or "").strip():
            errors.append("llm.model es obligatorio")
        if not (str(llm_cfg.get("api_key_env") or "").strip() or str(llm_cfg.get("api_key") or "").strip()):
            errors.append("llm.api_key_env es obligatorio")

    if not str(config.get("system_prompt") or "").strip():
        errors.append("system_prompt es obligatorio para tenants activos")

    whatsapp = config.get("whatsapp")
    if isinstance(whatsapp, dict) and whatsapp:
        if not str(whatsapp.get("phone_number_id_env") or whatsapp.get("phone_number_id") or "").strip():
            errors.append("whatsapp.phone_number_id_env es obligatorio si WhatsApp esta configurado")
        if not str(whatsapp.get("token_env") or whatsapp.get("token") or "").strip():
            errors.append("whatsapp.token_env es obligatorio si WhatsApp esta configurado")

    telegram = config.get("telegram")
    if isinstance(telegram, dict) and telegram:
        if not str(telegram.get("bot_token_env") or telegram.get("bot_token") or "").strip():
            errors.append("telegram.bot_token_env es obligatorio si Telegram esta configurado")
        if not str(telegram.get("secret_token_env") or telegram.get("secret_token") or "").strip():
            errors.append("telegram.secret_token_env es obligatorio si Telegram esta configurado")

    handoff = config.get("handoff")
    if isinstance(handoff, dict) and handoff and not str(handoff.get("number") or "").strip():
        errors.append("handoff.number es obligatorio si handoff esta configurado")

    errors.extend(_vertical_errors(config))
    return errors


# Reglas de negocio por vertical (se exigen al activar el tenant). Ver VERTICALES.md.
def _vertical_key(config: dict) -> str:
    from .util import normalize_text
    return normalize_text(config.get("vertical") or "", split_underscores=True)


def _vertical_errors(config: dict) -> list[str]:
    """Validaciones fuertes según el rubro del cliente (Fase 3/4 del plan)."""
    v = _vertical_key(config)
    errors: list[str] = []
    cal = config.get("calendar") or {}
    has_calendar = isinstance(cal, dict) and cal.get("enabled")

    # Salud y reservas se DEFINEN por agendar citas: exigimos calendario.
    if any(k in v for k in ("salud", "health", "clinica", "medic")):
        if not has_calendar:
            errors.append("vertical salud: requiere 'calendar.enabled=true' para agendar citas")
        elif not (cal.get("specialties") or []):
            errors.append("vertical salud: 'calendar.specialties' no puede estar vacío")
    elif any(k in v for k in ("reserva", "booking", "turno", "agenda")):
        if not has_calendar:
            errors.append("vertical reservas: requiere 'calendar.enabled=true'")
    # Otras verticales (retail, servicios, fintech…) no imponen requisitos duros:
    # un bot que solo responde FAQs es válido.
    return errors


def _db_rows(include_inactive: bool = False) -> list:
    where = "" if include_inactive else " WHERE active=true" if db.is_postgres() else " WHERE active=1"
    with db.connect() as con:
        return con.execute(
            "SELECT id, name, vertical, active, config_json FROM tenants"
            f"{where} ORDER BY name"
        ).fetchall()


def _db_count() -> int:
    with db.connect() as con:
        row = con.execute("SELECT COUNT(*) AS c FROM tenants").fetchone()
    return int(row["c"] if row else 0)


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _set_path(config: dict, path: str, value: str) -> None:
    parts = path.split(".")
    node = config
    for part in parts[:-1]:
        current = node.get(part)
        if not isinstance(current, dict):
            current = {}
            node[part] = current
        node = current
    node[parts[-1]] = value


def ensure_store(overwrite: bool | None = None) -> None:
    """Inicializa tenants en DB usando el JSON como bootstrap.

    Por defecto solo siembra cuando la tabla esta vacia. Para forzar sincronizar
    el JSON otra vez: TENANTS_BOOTSTRAP_OVERWRITE=true o `overwrite=True`.
    """
    if not database_tenants_enabled():
        return
    if overwrite is None:
        overwrite = os.getenv("TENANTS_BOOTSTRAP_OVERWRITE", "").strip().lower() in {"1", "true", "yes", "on"}
    if _db_count() and not overwrite:
        return
    for tenant_id, config in _file_tenants().items():
        upsert_tenant_config(tenant_id, config)


def pricing() -> dict:
    return _config().get("pricing_usd_per_million", {})


def all_tenants(include_inactive: bool = False) -> dict:
    if database_tenants_enabled():
        return {row["id"]: _row_to_tenant(row) for row in _db_rows(include_inactive)}
    tenants = _file_tenants()
    if include_inactive:
        return tenants
    return {tid: cfg for tid, cfg in tenants.items() if cfg.get("active", True)}


def get_tenant(tenant_id: str, include_inactive: bool = False) -> dict | None:
    t = all_tenants(include_inactive=include_inactive).get(tenant_id)
    if not t:
        return None
    if not include_inactive and not t.get("active", True):
        return None
    return {**t, "id": tenant_id}


def get_tenant_config(tenant_id: str) -> dict | None:
    return all_tenants(include_inactive=True).get(tenant_id)


def upsert_tenant_config(tenant_id: str, config: dict) -> dict:
    if not database_tenants_enabled():
        raise RuntimeError("La escritura de tenants requiere TENANTS_SOURCE=database o Postgres")
    tenant_id = _validate_tenant_id(tenant_id)
    cfg = _normalize_config(tenant_id, config)
    validation_errors = validate_tenant_config(cfg)
    if validation_errors:
        raise ValueError("Configuracion de tenant invalida: " + "; ".join(validation_errors))
    payload = json.dumps(cfg, ensure_ascii=False)
    now = _now()
    if db.is_postgres():
        sql = (
            "INSERT INTO tenants (id, name, vertical, active, config_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT (id) DO UPDATE SET "
            "name=EXCLUDED.name, vertical=EXCLUDED.vertical, active=EXCLUDED.active, "
            "config_json=EXCLUDED.config_json, updated_at=EXCLUDED.updated_at"
        )
    else:
        sql = (
            "INSERT INTO tenants (id, name, vertical, active, config_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, vertical=excluded.vertical, active=excluded.active, "
            "config_json=excluded.config_json, updated_at=excluded.updated_at"
        )
    with db.connect() as con:
        con.execute(sql, (tenant_id, cfg["name"], cfg.get("vertical", ""), cfg["active"], payload, now, now))
    return {**cfg, "id": tenant_id}


def patch_tenant_config(tenant_id: str, patch: dict) -> dict:
    current = get_tenant_config(tenant_id)
    if current is None:
        raise KeyError(tenant_id)
    merged = _deep_merge(current, patch or {})
    return upsert_tenant_config(tenant_id, merged)


def set_tenant_active(tenant_id: str, active: bool) -> dict:
    return patch_tenant_config(tenant_id, {"active": bool(active)})


def set_secret_refs(tenant_id: str, refs: dict[str, str]) -> dict:
    current = get_tenant_config(tenant_id)
    if current is None:
        raise KeyError(tenant_id)
    cfg = copy.deepcopy(current)
    for path, env_name in (refs or {}).items():
        if path not in _SECRET_REF_PATHS:
            raise ValueError(f"Ruta de secret no permitida: {path}")
        env_name = (env_name or "").strip()
        if not _ENV_NAME_RE.match(env_name):
            raise ValueError(f"Nombre de variable invalido para {path}")
        _set_path(cfg, path, env_name)
    return upsert_tenant_config(tenant_id, cfg)


def resolve_secret(cfg: dict, key: str, env_key: str) -> str | None:
    """Valor directo en config o, si no, variable de entorno referenciada."""
    if cfg.get(key):
        return cfg[key]
    env_name = cfg.get(env_key)
    return os.getenv(env_name) if env_name else None


def llm_api_key(tenant: dict) -> str | None:
    return resolve_secret(tenant.get("llm", {}), "api_key", "api_key_env")


def whatsapp_token(tenant: dict) -> str | None:
    return resolve_secret(tenant.get("whatsapp", {}), "token", "token_env")


def whatsapp_phone_number_id(tenant: dict) -> str | None:
    return resolve_secret(tenant.get("whatsapp", {}), "phone_number_id", "phone_number_id_env")


def telegram_token(tenant: dict) -> str | None:
    return resolve_secret(tenant.get("telegram", {}), "bot_token", "bot_token_env")


def telegram_secret(tenant: dict) -> str | None:
    return resolve_secret(tenant.get("telegram", {}), "secret_token", "secret_token_env")


def resolve_by_phone_number_id(pnid: str) -> dict | None:
    """Webhook de WhatsApp: identifica al tenant por el phone_number_id de Meta."""
    for tid in all_tenants():
        t = get_tenant(tid)
        if t and whatsapp_phone_number_id(t) == pnid:
            return t
    return None


def model_price(model: str) -> dict:
    p = pricing()
    return p.get(model) or p.get("default", {"in": 0.5, "out": 1.5})
