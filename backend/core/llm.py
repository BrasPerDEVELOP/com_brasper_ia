"""Cliente LLM OpenAI-compatible por tenant (DeepSeek/OpenAI) con captura de uso."""
import httpx

from . import tenants as T


class LLMError(Exception):
    pass


def _cost_usd(model: str, tokens_in: int, tokens_out: int, cached_in: int) -> float:
    """Costo del turno. Los modelos DeepSeek v4 cobran la entrada en caché mucho
    más barata (p.ej. 0.0028 vs 0.14 por 1M), así que se factura por separado."""
    price = T.model_price(model)
    hit_price = price.get("in_cache_hit", price["in"])
    miss = max(0, tokens_in - cached_in)
    cost = (miss / 1e6 * price["in"]
            + cached_in / 1e6 * hit_price
            + tokens_out / 1e6 * price["out"])
    return round(cost, 8)


async def chat(tenant: dict, messages: list[dict]) -> dict:
    """Devuelve {content, tokens_in, tokens_out, model, provider, cost_usd}."""
    cfg = tenant.get("llm", {})
    api_key = T.llm_api_key(tenant)
    if not api_key:
        raise LLMError(f"Tenant {tenant['id']}: sin API key de LLM configurada")
    model = cfg.get("model", "deepseek-v4-flash")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": cfg.get("temperature", 0.7),
        "max_tokens": cfg.get("max_tokens", 900),
    }
    # Los modelos de razonamiento aceptan reasoning_effort (low|medium|high|max|xhigh).
    if cfg.get("reasoning_effort"):
        payload["reasoning_effort"] = cfg["reasoning_effort"]
    url = cfg.get("base_url", "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=payload,
                                  headers={"Authorization": f"Bearer {api_key}"})
    except httpx.RequestError as e:
        raise LLMError(f"LLM inalcanzable: {e}") from e
    if r.status_code != 200:
        raise LLMError(f"LLM {r.status_code}: {r.text[:200]}")
    try:
        data = r.json()
        choice = data["choices"][0]
    except (ValueError, KeyError, IndexError) as e:
        raise LLMError(f"LLM respondió un formato inesperado: {r.text[:200]}") from e
    usage = data.get("usage", {})
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)
    cached_in = (usage.get("prompt_cache_hit_tokens")
                 or (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    content = (choice.get("message", {}).get("content") or "").strip()
    if not content:
        # Un modelo de razonamiento puede gastar todo max_tokens pensando y devolver
        # content vacío. Es un fallo, no una respuesta: si lo dejáramos pasar el bot
        # se quedaría callado. Sube llm.max_tokens o baja llm.reasoning_effort.
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        raise LLMError(
            f"LLM devolvió respuesta vacía (modelo {model}, finish_reason="
            f"{choice.get('finish_reason')}, tokens_out={tokens_out}, "
            f"razonamiento={reasoning}, max_tokens={payload['max_tokens']})")
    return {
        "content": content,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "model": model,
        "provider": cfg.get("provider", "openai-compatible"),
        "cost_usd": _cost_usd(model, tokens_in, tokens_out, cached_in),
    }


async def probe(tenant: dict) -> dict:
    """Diagnóstico sin gasto de tokens: ¿la API responde y el modelo configurado
    existe todavía? Un modelo retirado (p.ej. deepseek-chat) deja al bot mudo, así
    que conviene poder comprobarlo desde el panel."""
    cfg = tenant.get("llm", {})
    model = cfg.get("model")
    api_key = T.llm_api_key(tenant)
    if not api_key:
        return {"ok": False, "model": model, "error": "sin API key de LLM configurada"}
    url = cfg.get("base_url", "https://api.deepseek.com/v1").rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.RequestError as e:
        return {"ok": False, "model": model, "error": f"LLM inalcanzable: {e}"}
    if r.status_code != 200:
        return {"ok": False, "model": model, "status": r.status_code,
                "error": r.text[:200]}
    available = [m.get("id") for m in (r.json().get("data") or [])]
    ok = model in available
    out = {"ok": ok, "model": model, "available": available}
    if not ok:
        out["error"] = (f"El modelo '{model}' ya no existe en el proveedor. "
                        f"Modelos disponibles: {', '.join(available) or 'ninguno'}.")
    return out
