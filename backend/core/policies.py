"""Primitivas puras y agnosticas del motor de politicas (portadas del bot original).

Este modulo NO depende de ningun tenant ni de Brasper: son funciones puras,
sin estado, sin I/O y sin efectos secundarios, faciles de testear. Se usan
para el pre-procesado ligero de un mensaje de usuario antes de invocar al LLM.

Funciones publicas:
    - detect_language(text) -> 'es' | 'pt' | 'en'
    - normalize_currency(token) -> codigo ISO ('USD'|'PEN'|'BRL'|...) | None
    - extract_amount(text) -> float | None
    - detect_intent(text, intents_keywords) -> str | None
    - pre_process(text) -> {language, amount, currencies, has_greeting}

Doctests / ejemplos (comprobables con `python -m doctest core/policies.py -v`):

    >>> detect_language("Hola, quiero cotizar")
    'es'
    >>> detect_language("Ola, quero uma cotacao")
    'pt'
    >>> detect_language("Hello, I want a quote please")
    'en'
    >>> normalize_currency("$")
    'USD'
    >>> normalize_currency("soles")
    'PEN'
    >>> normalize_currency("reais")
    'BRL'
    >>> normalize_currency("banana") is None
    True
    >>> extract_amount("quiero enviar 500 a Peru")
    500.0
    >>> extract_amount("son 1.500,50 reais")
    1500.5
    >>> extract_amount("that is 1,500.50 usd")
    1500.5
    >>> extract_amount("sin monto") is None
    True
    >>> detect_intent("necesito un asesor", {"handoff": ["asesor", "advisor"]})
    'handoff'
    >>> detect_intent("hola que tal", {"handoff": ["asesor"]}) is None
    True
    >>> r = pre_process("Hola, quiero enviar 500 dolares a soles")
    >>> r["language"], r["amount"], r["currencies"], r["has_greeting"]
    ('es', 500.0, ['USD', 'PEN'], True)
"""
import re
import unicodedata
from typing import Optional

# --- Constantes de deteccion (multilingues, agnosticas) ---------------------

_GREETINGS = (
    "hola", "buenas", "buen dia", "buenos dias", "buenas tardes", "buenas noches",
    "hello", "hi", "hey", "good morning", "good afternoon",
    "ola", "oi", "bom dia", "boa tarde", "boa noite",
)

# Marcadores fuertes por idioma (palabras/tokens distintivos).
_PT_MARKERS = frozenset({
    "ola", "oi", "quero", "cotacao", "assessor", "voce", "obrigado", "obrigada",
    "bom", "dia", "boa", "tarde", "noite", "reais", "por", "favor", "sim", "nao",
    "enviar", "receber", "quanto", "para",
})
_EN_MARKERS = frozenset({
    "hello", "hi", "hey", "quote", "advisor", "please", "thanks", "thank", "you",
    "want", "need", "how", "much", "send", "receive", "the", "dollars", "dollar",
    "good", "morning", "what", "is",
})
_ES_MARKERS = frozenset({
    "hola", "quiero", "cotizacion", "cotizar", "asesor", "gracias", "por", "favor",
    "necesito", "enviar", "recibir", "cuanto", "soles", "dolares", "buenas",
})

# Alias de monedas -> codigo ISO. Ampliable sin acoplar a un tenant concreto.
_CURRENCY_ALIASES = {
    "USD": {"usd", "usdt", "dolar", "dolares", "dollar", "dollars", "$", "us$", "u$s"},
    "PEN": {"pen", "sol", "soles", "nuevo sol", "nuevos soles", "s/", "s/.", "s\\"},
    "BRL": {"brl", "real", "reales", "reais", "r$"},
    "EUR": {"eur", "euro", "euros", "€"},
}

# Regex de montos: captura enteros y decimales con separadores de miles/decimales.
# Ej: 500 | 1.500,50 | 1,500.50 | 1500.5
_AMOUNT_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?![\w])")


# --- Helpers internos -------------------------------------------------------

def _strip_accents(value: str) -> str:
    """Quita tildes/diacriticos para comparar de forma robusta.

    >>> _strip_accents("cotización")
    'cotizacion'
    """
    nfkd = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _normalize_text(text: str) -> str:
    """Minusculas, sin tildes, espacios colapsados. Preserva simbolos ($, /, etc.).

    >>> _normalize_text("  Hola   MUNDO  ")
    'hola mundo'
    """
    return " ".join(_strip_accents((text or "").lower()).split())


def _tokens(text: str) -> set:
    """Conjunto de palabras alfabeticas normalizadas."""
    return set(re.findall(r"[a-z]+", _normalize_text(text)))


# --- API publica ------------------------------------------------------------

def detect_language(text: str) -> str:
    """Detecta idioma por marcadores; devuelve 'es' | 'pt' | 'en' (default 'es').

    Cuenta coincidencias de tokens distintivos por idioma y elige el maximo;
    ante empate o ausencia de senales, cae a 'es'.

    >>> detect_language("Olá, quanto custa enviar para o Brasil?")
    'pt'
    >>> detect_language("Hello, how much to send money?")
    'en'
    >>> detect_language("")
    'es'
    """
    toks = _tokens(text)
    if not toks:
        return "es"
    scores = {
        "pt": len(toks & _PT_MARKERS),
        "en": len(toks & _EN_MARKERS),
        "es": len(toks & _ES_MARKERS),
    }
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "es"
    # Desempate estable: si es empata con el ganador, prefiere 'es'.
    if scores["es"] == scores[best]:
        return "es"
    return best


def normalize_currency(token: str) -> Optional[str]:
    """Normaliza un token de moneda a codigo ISO, o None si no reconoce.

    >>> normalize_currency("Dólares")
    'USD'
    >>> normalize_currency("R$")
    'BRL'
    >>> normalize_currency("PEN")
    'PEN'
    >>> normalize_currency("s/")
    'PEN'
    >>> normalize_currency(None) is None
    True
    """
    if not token:
        return None
    raw = str(token).strip()
    lowered = _strip_accents(raw.lower())
    # Coincidencia directa por alias (incluye simbolos como $, r$, s/).
    for code, aliases in _CURRENCY_ALIASES.items():
        if lowered in aliases:
            return code
    # ISO explicito en mayusculas (USD, PEN, BRL, EUR...).
    upper = raw.upper()
    if upper in _CURRENCY_ALIASES:
        return upper
    # Variante sin simbolos residuales.
    stripped = lowered.replace("$", "").replace(".", "").strip()
    if stripped:
        for code, aliases in _CURRENCY_ALIASES.items():
            if stripped in aliases:
                return code
    return None


def extract_currencies(text: str) -> list:
    """Devuelve los codigos ISO detectados en el texto, en orden de aparicion.

    >>> extract_currencies("cambio de dolares a soles")
    ['USD', 'PEN']
    >>> extract_currencies("nada de dinero")
    []
    """
    normalized = _normalize_text(text)
    matches = []
    for code, aliases in _CURRENCY_ALIASES.items():
        positions = [normalized.find(a) for a in aliases if normalized.find(a) >= 0]
        if positions:
            matches.append((min(positions), code))
    matches.sort(key=lambda item: item[0])
    seen, ordered = set(), []
    for _, code in matches:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def _parse_amount(raw: str) -> Optional[float]:
    """Convierte un string numerico con separadores ambiguos a float.

    Heuristica de separadores de miles vs decimales:
      - '1.500,50' (europeo)  -> 1500.50
      - '1,500.50' (anglo)    -> 1500.50
      - '1500'                -> 1500.0
    """
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    has_dot = "." in s
    has_comma = "," in s
    try:
        if has_dot and has_comma:
            # El ultimo separador que aparece es el decimal.
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif has_comma:
            # Coma sola: decimal si hay 1-2 digitos tras ella, si no miles.
            if re.search(r",\d{1,2}$", s):
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")
        elif has_dot:
            # Punto solo: miles si es exactamente xxx.ddd (3 digitos), si no decimal.
            if re.search(r"^\d{1,3}\.\d{3}$", s):
                s = s.replace(".", "")
            # en otro caso se deja como decimal
        return round(float(s), 2)
    except (TypeError, ValueError):
        return None


def extract_amount(text: str) -> Optional[float]:
    """Extrae el primer monto numerico del texto, o None.

    >>> extract_amount("Cotizar 500 BRL a PEN")
    500.0
    >>> extract_amount("1.500,50")
    1500.5
    >>> extract_amount("1,500.50")
    1500.5
    >>> extract_amount("2500.75 dolares")
    2500.75
    >>> extract_amount("sin numeros") is None
    True
    """
    match = _AMOUNT_RE.search(text or "")
    if not match:
        return None
    return _parse_amount(match.group(1))


def has_greeting(text: str) -> bool:
    """True si el mensaje contiene un saludo comun (cualquier idioma).

    >>> has_greeting("hola, buenas")
    True
    >>> has_greeting("quiero cotizar")
    False
    """
    normalized = _normalize_text(text)
    return any(g in normalized for g in _GREETINGS)


def detect_intent(text: str, intents_keywords: dict) -> Optional[str]:
    """Detecta intent segun un mapa {intent: [palabras_clave, ...]} parametrizable.

    Coincide por substring sobre el texto normalizado (sin tildes, minusculas).
    Las palabras clave tambien se normalizan. Devuelve el primer intent con match
    (por orden de insercion del dict), o None.

    >>> kws = {"handoff": ["asesor", "advisor"], "coupon": ["cupon", "descuento"]}
    >>> detect_intent("quiero un descuento", kws)
    'coupon'
    >>> detect_intent("necesito ASESOR ya", kws)
    'handoff'
    >>> detect_intent("solo una consulta", kws) is None
    True
    """
    if not intents_keywords:
        return None
    normalized = _normalize_text(text)
    if not normalized:
        return None
    for intent, keywords in intents_keywords.items():
        for kw in (keywords or []):
            if _normalize_text(str(kw)) in normalized:
                return intent
    return None


def pre_process(text: str) -> dict:
    """Pre-analisis ligero de un mensaje. Combina las primitivas anteriores.

    Devuelve un dict con:
      - language: 'es' | 'pt' | 'en'
      - amount: float | None
      - currencies: [codigos ISO en orden de aparicion]
      - has_greeting: bool

    >>> r = pre_process("Ola, quero enviar 1.500,50 reais para soles")
    >>> r["language"]
    'pt'
    >>> r["amount"]
    1500.5
    >>> r["currencies"]
    ['BRL', 'PEN']
    >>> r["has_greeting"]
    True
    >>> pre_process("")
    {'language': 'es', 'amount': None, 'currencies': [], 'has_greeting': False}
    """
    return {
        "language": detect_language(text),
        "amount": extract_amount(text),
        "currencies": extract_currencies(text),
        "has_greeting": has_greeting(text),
    }
