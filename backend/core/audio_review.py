"""Revisión de transcripciones de audio (etapa 3): detectar cifras ambiguas antes de
actuar. Un audio legible sigue con la IA; uno ambiguo pide confirmación puntual.
Puro (sin red ni DB) para poder probarlo en run_checks y evals.
"""
from __future__ import annotations

import re

from . import policies, util

_NUM_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,](\d{1,2}))?(?![\w])")
_UNREADABLE = ("[inaudible]", "[inaudível]", "[ruido]", "[música]", "[musica]", "...")
_MIL_WORDS = ("mil", "mill", "millon", "millones", "milhao", "milhões", "milhoes")
_ACTION_HINTS = ("enviar", "mandar", "cotizar", "cotar", "transferir", "depositar", "pagar",
                 "quiero", "quero", "deseo", "preciso", "necesito")


def _amounts(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUM_RE.finditer(text):
        whole = m.group(1).replace(".", "").replace(",", "")
        try:
            value = float(whole + ("." + m.group(2) if m.group(2) else ""))
        except ValueError:
            continue
        out.append(value)
    return out


def review_transcript(text: str) -> dict:
    """Devuelve {ok, ambiguous, reason, amounts, currencies, text}.

    Ambiguo cuando: la transcripción marca partes inaudibles; hay dos o más montos
    distintos relevantes (≥ 10) en un pedido de acción; aparece "mil/millón" junto a
    un número (500 mil vs 500); o hay monto sin moneda en un pedido de envío.
    """
    t = (text or "").strip()
    low = util.normalize_text(t)
    if not t:
        return {"ok": False, "ambiguous": True, "reason": "empty", "amounts": [], "currencies": [], "text": t}
    if any(u in t.lower() for u in _UNREADABLE):
        return {"ok": True, "ambiguous": True, "reason": "unreadable_parts", "amounts": _amounts(t),
                "currencies": policies.extract_currencies(t), "text": t}
    amounts = [a for a in _amounts(t) if a >= 10]
    distinct = sorted(set(amounts))
    currencies = policies.extract_currencies(t)
    action = any(h in low for h in _ACTION_HINTS)
    if action and len(distinct) >= 2:
        return {"ok": True, "ambiguous": True, "reason": "multiple_amounts", "amounts": distinct,
                "currencies": currencies, "text": t}
    if distinct and any(re.search(rf"\d\s*{w}\b", low) for w in _MIL_WORDS):
        return {"ok": True, "ambiguous": True, "reason": "thousands_word", "amounts": distinct,
                "currencies": currencies, "text": t}
    if action and distinct and not currencies:
        return {"ok": True, "ambiguous": True, "reason": "amount_without_currency", "amounts": distinct,
                "currencies": currencies, "text": t}
    return {"ok": True, "ambiguous": False, "reason": None, "amounts": distinct, "currencies": currencies, "text": t}


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ") if v == int(v) else f"{v:,.2f}".replace(",", " ")


def confirmation_reply(review: dict, lang: str = "es") -> str:
    text = review.get("text") or ""
    amounts = review.get("amounts") or []
    shown = text if len(text) <= 160 else text[:157] + "…"
    opts = " / ".join(_fmt(a) for a in amounts[:3])
    if lang == "pt":
        base = f"Ouvi: «{shown}»."
        if review.get("reason") == "multiple_amounts":
            return f"{base} Encontrei mais de um valor ({opts}). Qual é o valor correto e em que moeda? Pode escrever, por exemplo, *Cotizar 500 BRL a PEN*."
        if review.get("reason") == "amount_without_currency":
            return f"{base} Em que moeda é o valor {opts}? Soles (PEN), reais (BRL) ou dólares (USD)?"
        if review.get("reason") == "thousands_word":
            return f"{base} O valor é {opts} ou {opts} mil? Confirme o número exato para eu cotar certo."
        return f"{base} Não entendi tudo com clareza. Pode escrever o pedido em texto? Por exemplo *Cotizar 500 BRL a PEN*."
    base = f"Escuché: «{shown}»."
    if review.get("reason") == "multiple_amounts":
        return f"{base} Encontré más de un monto ({opts}). ¿Cuál es el monto correcto y en qué moneda? Puedes escribir, por ejemplo, *Cotizar 500 PEN a BRL*."
    if review.get("reason") == "amount_without_currency":
        return f"{base} ¿En qué moneda es el monto {opts}? ¿Soles (PEN), reales (BRL) o dólares (USD)?"
    if review.get("reason") == "thousands_word":
        return f"{base} ¿El monto es {opts} o {opts} mil? Confírmame la cifra exacta para cotizarte bien."
    return f"{base} No entendí todo con claridad. ¿Me lo escribes en texto? Por ejemplo *Cotizar 500 PEN a BRL*."
