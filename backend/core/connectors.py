"""Ejecutor declarativo de APIs externas por tenant.

Version real del 'conector de API generico' de la maqueta. Cada tenant puede
declarar en su config una seccion ``externalApis`` con conectores y endpoints;
este modulo los lista (sin exponer secretos) y los ejecuta de forma segura.

Forma esperada de la config (por tenant)::

    "externalApis": {
      "<connector_key>": {
        "name": "ERP de stock",
        "base_url": "https://httpbin.org",
        "auth": {
          "type": "none" | "api_key_header" | "bearer",
          "token": "valor-directo",          # opcional
          "token_env": "NOMBRE_VAR_ENTORNO",  # opcional (preferido)
          "header": "X-Api-Key"               # solo para api_key_header
        },
        "default_headers": { "Accept": "application/json" },
        "endpoints": [
          {
            "tool": "consultar_stock",
            "method": "GET",
            "path": "/get?sku={{sku}}",
            "desc": "Consulta stock por SKU",
            "output_var": "stock"            # opcional
          }
        ]
      }
    }

Interpolacion: cualquier ``{{var}}`` en ``path`` (incluida la query) se
reemplaza con ``variables[var]`` aplicando urlencode. Para POST/PUT/PATCH, las
variables no consumidas por el path se envian como JSON en el body.
"""
import re
from urllib.parse import quote

import httpx

from . import tenants as T

TIMEOUT_SECONDS = 20.0
_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _external_apis(tenant: dict) -> dict:
    """Seccion externalApis del tenant (dict vacio si no existe)."""
    apis = tenant.get("externalApis") or {}
    return apis if isinstance(apis, dict) else {}


def _public_endpoint(ep: dict) -> dict:
    """Vista publica de un endpoint (sin exponer nada sensible)."""
    return {
        "tool": ep.get("tool"),
        "method": (ep.get("method") or "GET").upper(),
        "path": ep.get("path", ""),
        "desc": ep.get("desc", ""),
    }


def list_connectors(tenant: dict) -> list[dict]:
    """Lista de conectores del tenant. NUNCA expone tokens ni token_env."""
    out = []
    for key, cfg in _external_apis(tenant).items():
        if not isinstance(cfg, dict):
            continue
        endpoints = cfg.get("endpoints") or []
        out.append({
            "key": key,
            "name": cfg.get("name", key),
            "base_url": cfg.get("base_url", ""),
            "endpoints": [_public_endpoint(ep) for ep in endpoints
                          if isinstance(ep, dict)],
        })
    return out


def _find_endpoint(cfg: dict, tool_name: str) -> dict | None:
    for ep in cfg.get("endpoints") or []:
        if isinstance(ep, dict) and ep.get("tool") == tool_name:
            return ep
    return None


def _interpolate(path: str, variables: dict) -> tuple[str, set[str]]:
    """Reemplaza {{var}} en el path (urlencoded). Devuelve (path, usados)."""
    used: set[str] = set()

    def repl(m: re.Match) -> str:
        name = m.group(1)
        used.add(name)
        val = variables.get(name, "")
        return quote(str(val), safe="")

    return _VAR_RE.sub(repl, path), used


def _build_auth(auth: dict) -> tuple[dict, str | None]:
    """Devuelve (headers_de_auth, error). El error es un mensaje si falta token."""
    headers: dict = {}
    if not isinstance(auth, dict):
        return headers, None
    atype = (auth.get("type") or "none").lower()
    if atype == "none":
        return headers, None
    token = T.resolve_secret(auth, "token", "token_env")
    if atype == "bearer":
        if not token:
            return headers, "auth 'bearer' sin token/token_env resoluble"
        headers["Authorization"] = f"Bearer {token}"
        return headers, None
    if atype == "api_key_header":
        if not token:
            return headers, "auth 'api_key_header' sin token/token_env resoluble"
        header_name = auth.get("header") or "X-Api-Key"
        headers[header_name] = token
        return headers, None
    return headers, f"tipo de auth no soportado: {atype}"


async def call_endpoint(tenant: dict, connector_key: str, tool_name: str,
                        variables: dict | None = None) -> dict:
    """Ejecuta un endpoint declarado. Devuelve {ok, status, data|error}."""
    variables = variables or {}
    apis = _external_apis(tenant)
    cfg = apis.get(connector_key)
    if not isinstance(cfg, dict):
        return {"ok": False, "status": 0,
                "error": f"conector '{connector_key}' no existe en el tenant"}

    ep = _find_endpoint(cfg, tool_name)
    if not ep:
        return {"ok": False, "status": 0,
                "error": f"tool '{tool_name}' no existe en el conector '{connector_key}'"}

    base_url = (cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        return {"ok": False, "status": 0,
                "error": f"conector '{connector_key}' sin base_url"}

    method = (ep.get("method") or "GET").upper()
    raw_path = ep.get("path", "")
    path, used = _interpolate(raw_path, variables)
    if not path.startswith("/"):
        path = "/" + path
    url = base_url + path

    headers: dict = {}
    default_headers = cfg.get("default_headers")
    if isinstance(default_headers, dict):
        headers.update(default_headers)
    auth_headers, auth_err = _build_auth(cfg.get("auth", {}))
    if auth_err:
        return {"ok": False, "status": 0, "error": auth_err}
    headers.update(auth_headers)

    # Variables no consumidas por el path -> body JSON en métodos con cuerpo.
    json_body = None
    if method in ("POST", "PUT", "PATCH"):
        json_body = {k: v for k, v in variables.items() if k not in used}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            r = await client.request(method, url, headers=headers, json=json_body)
    except httpx.TimeoutException:
        return {"ok": False, "status": 0,
                "error": f"timeout tras {TIMEOUT_SECONDS:g}s llamando a {url}"}
    except httpx.HTTPError as e:
        return {"ok": False, "status": 0, "error": f"error de red: {e}"}

    try:
        data = r.json()
    except ValueError:
        data = r.text

    result = {"ok": r.is_success, "status": r.status_code, "data": data}
    output_var = ep.get("output_var")
    if output_var:
        result["output_var"] = output_var
    return result
