"""Conocimiento Brasper con fuente (etapa 1 del plan de atención autónoma; Fase 3 del roadmap).

Recuperación determinista por palabras clave sobre `data/knowledge/brasper/faq.json`.
Sin LLM, sin vector DB: cada respuesta cita `source` y `reviewed_at`. Solo se sirven
entradas `status == "approved"`; si no hay coincidencia suficiente el bot declara
incertidumbre explícita y ofrece un asesor (nunca inventa).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import util

FAQ_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "brasper" / "faq.json"

# Señales de pregunta informativa (se evalúan DESPUÉS de la intención de cotizar).
_INFO_HINTS = (
    "que es brasper", "qué es brasper", "o que e brasper", "o que é brasper", "como funciona", "cómo funciona",
    "requisitos", "documentos", "documento", "que necesito", "qué necesito", "o que preciso",
    "como pago", "cómo pago", "donde pago", "dónde pago", "metodos de pago", "métodos de pago",
    "formas de pagamento", "como faco o pagamento", "como faço o pagamento", "yape", "pix",
    "comprobante", "comprovante", "ya pague", "ya pagué", "ya deposite", "ya deposité", "ja paguei", "já paguei",
    "cuanto demora", "cuánto demora", "cuanto tarda", "cuánto tarda", "quanto demora", "quanto tempo",
    "horario", "horarios", "horário", "limite", "límite", "minimo", "mínimo", "maximo", "máximo",
    "vigencia", "validez", "validade", "idioma", "idiomas", "portugues", "portugués", "ingles", "inglés", "english",
    "hablan", "falam", "como cotizo", "cómo cotizo", "como cotizar", "cómo cotizar", "como cotar", "pedir cotizacion",
    "pedir cotización", "pedir cotacao", "pedir cotação", "hablar con alguien", "falar com alguem",
    "falar com alguém", "atencion humana", "atención humana", "es seguro", "é seguro",
)


def has_intent(text: str) -> bool:
    low = util.normalize_text(text)
    return any(util.normalize_text(h) in low for h in _INFO_HINTS)


def _tokens(text: str) -> set[str]:
    return {t for t in util.normalize_text(text).replace("¿", " ").replace("?", " ").split() if len(t) > 2}


@lru_cache(maxsize=4)
def _load(mtime: float) -> dict:  # mtime solo invalida la caché
    with open(FAQ_PATH, encoding="utf-8") as f:
        return json.load(f)


def load() -> dict:
    try:
        return _load(FAQ_PATH.stat().st_mtime)
    except (OSError, ValueError):
        return {"version": None, "entries": []}


def entries(approved_only: bool = True) -> list[dict]:
    items = load().get("entries", [])
    return [e for e in items if (not approved_only or e.get("status") == "approved")]


def search(query: str, lang: str = "es") -> dict | None:
    """Mejor entrada aprobada para la consulta o None si no hay evidencia suficiente.

    Puntaje: cada palabra clave contenida en la consulta suma 3; cada token compartido
    con la pregunta suma 1; misma lengua +1. Umbral mínimo: 3 (al menos una palabra
    clave completa o tres tokens de la pregunta).
    """
    q_norm = util.normalize_text(query)
    q_tokens = _tokens(query)
    best, best_score = None, 0
    for e in entries():
        score = 0
        for kw in e.get("keywords", []):
            if util.normalize_text(kw) in q_norm:
                score += 3
        score += len(q_tokens & _tokens(e.get("question", "")))
        if e.get("lang") == lang:
            score += 1
        if score > best_score:
            best, best_score = e, score
    if not best or best_score < 3:
        return None
    # Si hay una variante del mismo grupo en el idioma del usuario, preferirla.
    for e in entries():
        if e.get("group") == best.get("group") and e.get("lang") == lang:
            best = e
            break
    return {"entry": best, "score": best_score, "source": best.get("source"), "reviewed_at": best.get("reviewed_at")}


_SOURCE_LABEL = {"es": "Fuente", "pt": "Fonte", "en": "Source"}
_NO_ANSWER = {
    "es": ("No tengo esa información confirmada todavía, así que prefiero no adivinar. "
           "Si quieres, escribe *asesor* y una persona del equipo te la confirma aquí mismo. "
           "Mientras tanto puedo cotizar tu envío: por ejemplo *Cotizar 500 PEN a BRL*."),
    "pt": ("Ainda não tenho essa informação confirmada, então prefiro não adivinhar. "
           "Se quiser, escreva *atendente* e uma pessoa da equipe confirma aqui mesmo. "
           "Enquanto isso posso cotar seu envio: por exemplo *Cotizar 500 BRL a PEN*."),
    "en": ("I don't have that information confirmed yet, so I'd rather not guess. "
           "Type *advisor* and a team member will confirm it right here. "
           "Meanwhile I can quote your transfer, e.g. *Cotizar 500 PEN a BRL*."),
}


def reply(hit: dict, lang: str = "es") -> str:
    e = hit["entry"]
    label = _SOURCE_LABEL.get(lang, "Fuente")
    rev = f" · rev. {e['reviewed_at']}" if e.get("reviewed_at") else ""
    return f"{e['answer']}\n\n📌 {label}: {e.get('source', '—')}{rev}"


def no_answer_reply(lang: str = "es") -> str:
    return _NO_ANSWER.get(lang, _NO_ANSWER["es"])


def summary() -> dict:
    """Para el panel: estado del corpus (aprobadas vs. borradores)."""
    data = load()
    items = data.get("entries", [])
    return {
        "version": data.get("version"),
        "path": str(FAQ_PATH.relative_to(FAQ_PATH.parents[3])) if FAQ_PATH.parents else str(FAQ_PATH),
        "approved": sum(1 for e in items if e.get("status") == "approved"),
        "draft": sum(1 for e in items if e.get("status") != "approved"),
        "entries": [{k: e.get(k) for k in ("id", "group", "lang", "status", "question", "source", "reviewed_at")} for e in items],
    }
