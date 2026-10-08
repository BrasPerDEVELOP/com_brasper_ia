"""Contratos tipados de herramientas (etapa 2 del plan de atención autónoma).

Cada herramienta declara entradas permitidas, permiso, timeout, si escribe y cómo se
valida su salida. `run()` valida la entrada, ejecuta con timeout y devuelve SIEMPRE
un dict estructurado con errores distinguibles:
  {ok: bool, data, error_code: validation|timeout|unavailable|upstream|internal, detail}
Las escrituras pueden declarar una clave de idempotencia: una repetición devuelve el
resultado guardado sin repetir la acción.
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Callable

from . import idempotency, observability

Validator = Callable[[Any], bool]


@dataclass(frozen=True)
class Contract:
    name: str
    description: str
    inputs: dict[str, type | tuple[type, ...]]
    required: frozenset[str]
    permission: str
    timeout: float
    write: bool = False
    available: bool = True          # False = la API no expone esta capacidad (sin API)
    output_check: Validator | None = None
    optional_inputs: frozenset[str] = field(default_factory=frozenset)


class ToolUnavailable(Exception):
    pass


def _is_dict(x: Any) -> bool:
    return isinstance(x, dict)


REGISTRY: dict[str, Contract] = {
    "quote.compute": Contract(
        name="quote.compute", description="Cotización determinista con TC/comisión/cupón en vivo (API Brasper)",
        inputs={"origin": str, "destination": str, "amount_send": (int, float), "desired_receive": (int, float)},
        required=frozenset({"origin", "destination"}), permission="bot", timeout=15.0,
        output_check=lambda o: isinstance(o, dict) and ("amount_receive" in o or "amount_send" in o)),
    "knowledge.search": Contract(
        name="knowledge.search", description="FAQ aprobada con fuente", inputs={"query": str, "lang": str},
        required=frozenset({"query"}), permission="bot", timeout=2.0,
        output_check=lambda o: o is None or (isinstance(o, dict) and "entry" in o)),
    "client.find": Contract(
        name="client.find", description="Buscar cliente Brasper por teléfono o nombre",
        inputs={"phone": str, "code_phone": str, "full_name": str}, required=frozenset(), permission="bot",
        timeout=20.0, output_check=_is_dict),
    "client.upsert": Contract(
        name="client.upsert", description="Alta/actualización idempotente del cliente en Brasper",
        inputs={"lead": dict}, required=frozenset({"lead"}), permission="bot", timeout=20.0, write=True,
        output_check=lambda o: isinstance(o, dict) and o.get("ok") is True),
    "deposit.accounts": Contract(
        name="deposit.accounts", description="Cuentas oficiales Brasper por moneda", inputs={"currency": str},
        required=frozenset({"currency"}), permission="bot", timeout=20.0, output_check=_is_dict),
    "status.lookup": Contract(
        name="status.lookup", description="Estado de una operación (NO disponible en la API IA privada: deriva a asesor)",
        inputs={"operation_id": str, "phone": str}, required=frozenset(), permission="bot", timeout=10.0,
        available=False),
    "message.send": Contract(
        name="message.send", description="Envío por canal (WhatsApp/Telegram) con conexión de origen",
        inputs={"channel": str, "to": str, "text": str, "connection_id": str},
        required=frozenset({"channel", "to", "text"}), permission="conversations:write", timeout=30.0, write=True),
}


def describe() -> list[dict]:
    out = []
    for c in REGISTRY.values():
        out.append({"name": c.name, "description": c.description, "permission": c.permission,
                    "timeout_s": c.timeout, "write": c.write, "available": c.available,
                    "inputs": {k: (v.__name__ if isinstance(v, type) else "|".join(t.__name__ for t in v))
                               for k, v in c.inputs.items()},
                    "required": sorted(c.required)})
    return out


def validate(name: str, inputs: dict) -> str | None:
    """None si la entrada es válida; si no, el detalle del error."""
    c = REGISTRY.get(name)
    if not c:
        return f"herramienta desconocida: {name}"
    if not isinstance(inputs, dict):
        return "inputs debe ser un objeto"
    unknown = set(inputs) - set(c.inputs)
    if unknown:
        return f"entradas no permitidas: {sorted(unknown)}"
    missing = [k for k in c.required if inputs.get(k) in (None, "")]
    if missing:
        return f"faltan entradas: {sorted(missing)}"
    for k, v in inputs.items():
        if v is None:
            continue
        expected = c.inputs[k]
        if isinstance(v, bool) and expected is not bool:
            return f"'{k}' tiene tipo inválido (bool)"
        if not isinstance(v, expected):
            return f"'{k}' debe ser {expected if isinstance(expected, type) else expected}"
    return None


def run(name: str, inputs: dict, fn: Callable[..., Any], *, idempotency_key: str | None = None) -> dict:
    c = REGISTRY.get(name)
    if not c:
        return {"ok": False, "error_code": "validation", "detail": f"herramienta desconocida: {name}"}
    if not c.available:
        observability.event("tool.unavailable", tool=name)
        return {"ok": False, "error_code": "unavailable", "detail": "capacidad no habilitada en la API Brasper"}
    err = validate(name, inputs)
    if err:
        observability.event("tool.validation_error", tool=name, detail=err)
        return {"ok": False, "error_code": "validation", "detail": err}
    if c.write and idempotency_key:
        prev = idempotency.recall(idempotency_key)
        if prev is not None:
            observability.event("tool.idempotent_replay", tool=name)
            return {**prev, "replayed": True}
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, **inputs)
        try:
            data = fut.result(timeout=c.timeout)
        except concurrent.futures.TimeoutError:
            observability.event("tool.timeout", tool=name, timeout_s=c.timeout)
            return {"ok": False, "error_code": "timeout", "detail": f"sin respuesta en {c.timeout:.0f}s"}
        except Exception as exc:  # noqa: BLE001 - error estructurado, nunca excepción al grafo
            observability.event("tool.error", tool=name, error=str(exc)[:160])
            return {"ok": False, "error_code": "internal", "detail": str(exc)[:160]}
    if c.output_check and not c.output_check(data):
        observability.event("tool.bad_output", tool=name)
        return {"ok": False, "error_code": "upstream", "detail": "salida inválida de la herramienta"}
    result = {"ok": True, "data": data}
    if c.write and idempotency_key:
        idempotency.remember(idempotency_key, result, scope=f"tool:{name}")
    return result
