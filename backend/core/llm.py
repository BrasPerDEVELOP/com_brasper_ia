"""Cliente LLM OpenAI-compatible por tenant (DeepSeek/OpenAI) con captura de uso."""
import httpx

from . import tenants as T


class LLMError(Exception):
    pass


async def chat(tenant: dict, messages: list[dict]) -> dict:
    """Devuelve {content, tokens_in, tokens_out, model, provider, cost_usd}."""
    cfg = tenant.get("llm", {})
    api_key = T.llm_api_key(tenant)
    if not api_key:
        raise LLMError(f"Tenant {tenant['id']}: sin API key de LLM configurada")
    model = cfg.get("model", "deepseek-chat")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": cfg.get("temperature", 0.7),
        "max_tokens": cfg.get("max_tokens", 500),
    }
    url = cfg.get("base_url", "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload,
                              headers={"Authorization": f"Bearer {api_key}"})
    if r.status_code != 200:
        raise LLMError(f"LLM {r.status_code}: {r.text[:200]}")
    data = r.json()
    usage = data.get("usage", {})
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)
    price = T.model_price(model)
    cost = tokens_in / 1e6 * price["in"] + tokens_out / 1e6 * price["out"]
    return {
        "content": data["choices"][0]["message"]["content"],
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "model": model,
        "provider": cfg.get("provider", "openai-compatible"),
        "cost_usd": round(cost, 8),
    }
