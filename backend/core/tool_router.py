"""Router deterministico de herramientas externas por tenant."""
from __future__ import annotations

import json
import re

from core import tenants as T
from . import connectors, db
from .util import normalize_text

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_STOPWORDS = {
    "consultar", "consulta", "crear", "estado", "obtener", "enviar", "hacer",
    "por", "para", "the", "get", "create", "send",
}


def _norm(value: str) -> str:
    return normalize_text(value, split_underscores=True)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", _norm(value)))


def _path_vars(path: str) -> list[str]:
    return _VAR_RE.findall(path or "")


def _endpoint_score(text: str, endpoint: dict) -> int:
    normalized = _norm(text)
    tool = str(endpoint.get("tool") or "")
    label = _norm(tool)
    if tool and tool.lower() in text.lower():
        return 10
    if label and label in normalized:
        return 9
    tool_terms = {t for t in _tokens(tool) if t not in _STOPWORDS and len(t) > 2}
    desc_terms = {t for t in _tokens(endpoint.get("desc", "")) if t not in _STOPWORDS and len(t) > 4}
    text_terms = _tokens(text)
    score = len(tool_terms & text_terms) * 3 + len(desc_terms & text_terms)
    return score


def _extract_var(text: str, name: str, endpoint: dict) -> str | None:
    patterns = [
        rf"\b{name}\b\s*[:=#-]?\s*([A-Za-z0-9_-]+)",
        rf"\b{name}\s+([A-Za-z0-9_-]+)",
    ]
    if name.lower() == "sku":
        patterns.extend([r"\bstock\s+([A-Za-z0-9_-]+)", r"\bproducto\s+([A-Za-z0-9_-]+)"])
    if name.lower() == "tracking":
        patterns.extend([r"\btracking\s+([A-Za-z0-9_-]+)", r"\benvio\s+([A-Za-z0-9_-]+)"])
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    # Si solo hay una variable y el usuario dijo la herramienta + un codigo corto,
    # toma el ultimo token alfanumerico como valor.
    if len(_path_vars(endpoint.get("path", ""))) == 1:
        candidates = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9_-]{2,}\b", text)
        if candidates:
            return candidates[-1]
    return None


def select_tool(text: str) -> dict | None:
    tenant = T.get_config()
    tenant_id = tenant["id"]
    best: tuple[int, dict, dict] | None = None
    for connector in connectors.list_connectors():
        for endpoint in connector.get("endpoints", []):
            score = _endpoint_score(text, endpoint)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, connector, endpoint)
    if best is None:
        return None
    _, connector, endpoint = best
    vars_needed = _path_vars(endpoint.get("path", ""))
    variables = {name: _extract_var(text, name, endpoint) for name in vars_needed}
    missing = [name for name, value in variables.items() if not value]
    return {
        "connector_key": connector["key"],
        "connector_name": connector.get("name", connector["key"]),
        "tool": endpoint["tool"],
        "method": endpoint.get("method", "GET"),
        "path": endpoint.get("path", ""),
        "variables": {k: v for k, v in variables.items() if v},
        "missing": missing,
    }


def missing_reply(request: dict) -> str:
    return f"Para usar {request['tool']} me falta: " + ", ".join(request["missing"]) + "."


def result_reply(request: dict, result: dict) -> str:
    if not result.get("ok"):
        return f"No pude ejecutar {request['tool']}: {result.get('error') or result.get('status')}"
    data = result.get("data")
    summary = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    if len(summary) > 700:
        summary = summary[:700] + "..."
    return f"Ejecute {request['tool']} en {request['connector_name']}. Resultado: {summary}"


def persist_tool_result(conversation_id: str, request: dict, result: dict) -> None:
    tenant = T.get_config()
    tenant_id = tenant["id"]
    db.add_audit_event(
        actor="agent",
        action="tool.execute",
        resource=f"tool:{request['connector_key']}.{request['tool']}",
        metadata={"variables": request.get("variables"), "ok": result.get("ok"), "status": result.get("status")},
    )
