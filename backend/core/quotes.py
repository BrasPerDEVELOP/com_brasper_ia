"""Cotizador de remesas por tenant — portado del bot Brasper real (app/).

Matemática idéntica a `app/application/brasper_use_case.py`:
  - comisión por rangos de monto (porcentaje sobre el monto bruto enviado),
  - cupón como descuento porcentual SOBRE LA COMISIÓN (no sobre el monto),
  - total_convertible = monto_enviado - comisión_neta; recibe = total * tasa,
  - modo "receive": búsqueda iterativa del monto a enviar (paso 0.01).

Configuración por tenant (config.quote):
  {
    "enabled": true,
    "pairs": [["PEN","BRL"], ["BRL","PEN"], ["USD","BRL"], ["BRL","USD"]],
    "api": {"enabled": true, "base_url": "https://apibras.finzeler.com"}
  }
Cuando la API está activa, tasas, comisiones y cupones vienen exclusivamente de
Brasper. No se cruzan monedas ni se usan valores locales como respaldo.
"""
from __future__ import annotations

from typing import Any, Optional

from core import tenants as T
from . import brasper_api, policies

_RECEIVE_KEYWORDS = ("recibir", "receive", "receber", "reciba", "receba", "llegue", "lleguen", "llegar", "cheguem", "chegar")
# Países -> moneda ("enviar a Brasil", "recibir en Perú"). El texto se normaliza
# sin tildes, por eso las claves van sin acento.
_COUNTRY_CURRENCY = {"peru": "PEN", "brasil": "BRL", "brazil": "BRL"}
# Verbos que indican dirección de ENVÍO (para distinguir un pedido con dirección
# nueva de un seguimiento tipo "¿y para 2000 soles?").
_SEND_KEYWORDS = ("enviar", "envio", "mandar", "mando", "manda", "mandes", "envie", "enviaria", "desde")
# Señales FUERTES: pedidos de cotización inequívocos -> ruta cotizador aunque
# falten datos (se le piden). Señales DÉBILES: verbos comunes (enviar, cambio…)
# que solo cuentan si vienen acompañados de monto o moneda — así "¿qué documentos
# necesito para el envío?" va al LLM y no al cotizador.
_STRONG_HINTS = (
    "cotiza", "cotizar", "cotizacion", "cotar", "cotacao", "quote",
    "remesa", "remessa", "remittance", "cuanto cuesta", "cuanto me cuesta",
    "quanto custa", "how much",
)
_WEAK_HINTS = (
    "cambio", "cambiar", "cambio", "enviar", "envio", "mandar",
    "recibir", "receber", "receive", "transferir",
)

_COPY = {
    "es": {
        "title": "Cotización",
        "send": "envías", "rate": "tasa", "commission": "comisión", "receive": "recibes",
        "coupon": "Cupón aplicado", "saving": "ahorro",
        "incomplete": ("Para cotizar necesito el monto, la moneda de origen y la de destino "
                       "en un solo mensaje. Ejemplo: Cotizar 500 PEN a BRL."),
        "invalid_pair": "Ese corredor no está disponible. Pares soportados: {pairs}.",
        "invalid_amount": "Necesito un monto válido mayor a 0 para cotizar.",
        "referential": "Cotización referencial; un asesor la confirma antes de operar.",
        "validity": "⏱️ Tipo de cambio válido por {minutes} minutos; luego se recotiza.",
        "cta": ("Para realizar el envío escribe *continuar* y un asesor te atiende aquí mismo, "
                "o envía tu comprobante de pago 📎 y lo revisamos."),
    },
    "pt": {
        "title": "Cotação",
        "send": "você envia", "rate": "taxa", "commission": "comissão", "receive": "você recebe",
        "coupon": "Cupom aplicado", "saving": "economia",
        "incomplete": ("Para cotar preciso do valor, moeda de origem e de destino em uma "
                       "única mensagem. Exemplo: Cotar 500 BRL para PEN."),
        "invalid_pair": "Esse corredor não está disponível. Pares suportados: {pairs}.",
        "invalid_amount": "Preciso de um valor válido maior que 0 para cotar.",
        "referential": "Cotação referencial; um assessor confirma antes de operar.",
        "validity": "⏱️ Taxa de câmbio válida por {minutes} minutos; depois é recotada.",
        "cta": ("Para concluir o envio escreva *continuar* e um assessor te atende aqui mesmo, "
                "ou envie seu comprovante de pagamento 📎 e nós revisamos."),
    },
    "en": {
        "title": "Quote",
        "send": "you send", "rate": "rate", "commission": "fee", "receive": "you receive",
        "coupon": "Coupon applied", "saving": "savings",
        "incomplete": ("To quote I need the amount, origin currency and destination currency "
                       "in one message. Example: Quote 500 PEN to BRL."),
        "invalid_pair": "That corridor is not available. Supported pairs: {pairs}.",
        "invalid_amount": "I need a valid amount greater than 0 to quote.",
        "referential": "Referential quote; an advisor confirms it before operating.",
        "validity": "⏱️ Exchange rate valid for {minutes} minutes; it is re-quoted afterwards.",
        "cta": ("To complete your transfer reply *continue* and an advisor will assist you here, "
                "or send your payment receipt 📎 and we'll review it."),
    },
}


def _cfg() -> dict:
    tenant = T.get_config()
    return tenant.get("quote") or {}


def enabled() -> bool:
    tenant = T.get_config()
    return bool(_cfg().get("enabled"))


def _copy(language: str) -> dict:
    return _COPY.get(language, _COPY["es"])


def _round(value: float) -> float:
    return round(float(value), 2)


def _fmt(value: Any) -> str:
    return f"{float(value or 0):,.2f}"


def pairs() -> list[tuple[str, str]]:
    tenant = T.get_config()
    out = []
    for pair in _cfg().get("pairs", []):
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            out.append((str(pair[0]).upper(), str(pair[1]).upper()))
    return out


def rate_for(origin: str, destination: str) -> Optional[float]:
    tenant = T.get_config()
    # Un tenant conectado a Brasper usa exclusivamente su API. Si la API falla o
    # no publica el corredor, no se cotiza con un valor local potencialmente viejo.
    if brasper_api.enabled(tenant):
        return brasper_api.rate_for(tenant, origin, destination)
    raw = (_cfg().get("rates") or {}).get(f"{origin}->{destination}")
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return None
    return rate if rate > 0 else None


def has_intent(text: str) -> bool:
    """Señal de cotización: pedido explícito, o verbo de envío CON monto/moneda."""
    tenant = T.get_config()
    if not enabled():
        return False
    low = policies._normalize_text(text)
    if any(k in low for k in _STRONG_HINTS):
        return True
    currencies = policies.extract_currencies(text)
    amount = policies.extract_amount(text)
    if any(k in low for k in _WEAK_HINTS):
        return bool(currencies) or amount is not None
    return bool(currencies and amount is not None) or len(currencies) >= 2


def _ordered_currencies(text: str) -> list[str]:
    """Monedas por palabra (soles/reales/…) MÁS países mapeados a su moneda
    (Perú→PEN, Brasil→BRL), en orden de aparición y sin duplicados."""
    low = policies._normalize_text(text)
    pos_by_code: dict[str, int] = {}

    def note(code: str, pos: int) -> None:
        if pos >= 0 and (code not in pos_by_code or pos < pos_by_code[code]):
            pos_by_code[code] = pos

    for code in policies.extract_currencies(text):
        aliases = policies._CURRENCY_ALIASES.get(code, ())
        found = [low.find(a) for a in aliases if a in low]
        note(code, min(found) if found else 0)
    for name, code in _COUNTRY_CURRENCY.items():
        note(code, low.find(name))
    return [code for code, _ in sorted(pos_by_code.items(), key=lambda kv: kv[1])]


def _infer_pair(origin: Optional[str],
                destination: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Completa el lado faltante si el corredor es ÚNICO en los pares del tenant.
    Ej. Brasper: origen PEN ⇒ destino BRL; recibir PEN ⇒ origen BRL."""
    tenant = T.get_config()
    prs = pairs()
    if not prs:
        return origin, destination
    if origin and not destination:
        cands = {b for a, b in prs if a == origin}
        if len(cands) == 1:
            destination = next(iter(cands))
    elif destination and not origin:
        cands = {a for a, b in prs if b == destination}
        if len(cands) == 1:
            origin = next(iter(cands))
    return origin, destination


def extract_request(text: str, prev: Optional[dict] = None) -> dict:
    """Extrae origen/destino/monto/modo del mensaje (reglas del bot real).

    Entiende monedas explícitas Y países ("a Brasil", "en Perú"), e infiere el
    lado faltante cuando el corredor es único (ej. recibir soles ⇒ enviar reales).

    `prev` = última cotización de la conversación ({origin, destination, mode}).
    Si el mensaje NO indica una dirección nueva (p.ej. "¿y para 2000 soles?"),
    se CONTINÚA la misma línea (mismo modo y corredor), solo cambia el monto —
    así no se resetea a "enviar" cuando el cliente venía en modo "recibir".
    """
    tenant = T.get_config()
    low = policies._normalize_text(text)
    currencies = _ordered_currencies(text)
    amount = policies.extract_amount(text)

    has_receive = any(k in low for k in _RECEIVE_KEYWORDS)
    has_send = any(k in low for k in _SEND_KEYWORDS)
    has_country = any(name in low for name in _COUNTRY_CURRENCY)
    explicit_direction = has_receive or has_send or has_country or len(currencies) >= 2

    # Seguimiento: sin dirección nueva + hay cotización previa -> misma línea.
    if not explicit_direction and prev and prev.get("origin") and prev.get("destination"):
        return {
            "origin": prev["origin"], "destination": prev["destination"],
            "amount": amount, "mode": prev.get("mode") or "send",
            "missing": [] if amount is not None else ["amount"],
            "followup": True,
        }

    mode = "receive" if has_receive else "send"
    origin = destination = None
    if len(currencies) >= 2:
        # "recibir 500 BRL de PEN" -> destino=BRL (primera), origen=PEN (segunda)
        if mode == "receive":
            destination, origin = currencies[0], currencies[1]
        else:
            origin, destination = currencies[0], currencies[1]
    elif len(currencies) == 1:
        if mode == "receive":
            destination = currencies[0]
        else:
            origin = currencies[0]

    # Inferir el lado faltante por el corredor (no depende del formato exacto).
    origin, destination = _infer_pair(origin, destination)

    missing = []
    if origin is None:
        missing.append("origin_currency")
    if destination is None:
        missing.append("destination_currency")
    if amount is None:
        missing.append("amount")
    return {"origin": origin, "destination": destination, "amount": amount,
            "mode": mode, "missing": missing}


def _commission_rate_for(ranges: list[dict], amount: float) -> float:
    for item in ranges or []:
        try:
            if float(item.get("min", 0)) <= amount <= float(item.get("max", 0)):
                return float(item.get("rate", 0))
        except (TypeError, ValueError):
            continue
    return 0.0


def _coupon_discount(coupon: Optional[dict], base_commission: float) -> float:
    if not coupon or base_commission <= 0:
        return 0.0
    try:
        pct = float(coupon.get("discount_percentage", 0))
    except (TypeError, ValueError):
        return 0.0
    return _round(base_commission * max(pct, 0) / 100)


def _quote_from_gross_send(amount_send: float, rate: float,
                           ranges: list[dict], coupon: Optional[dict]) -> dict:
    """Núcleo de la matemática Brasper (portado 1:1 de app/brasper_use_case.py)."""
    amount_send = _round(amount_send)
    commission_rate = _commission_rate_for(ranges, amount_send)
    base_commission = _round(amount_send * commission_rate)
    saving = _coupon_discount(coupon, base_commission)
    commission_net = _round(max(base_commission - saving, 0))
    total_to_send = _round(amount_send - commission_net)
    amount_receive = _round(total_to_send * rate)
    return {
        "amount_send": amount_send,
        "amount_receive": amount_receive,
        "rate": float(rate),
        "commission": commission_net,
        "commission_gross": base_commission,
        "commission_rate": _round(commission_rate * 100),
        "total_to_send": total_to_send,
        "coupon_code": (coupon or {}).get("code"),
        "coupon_savings_amount": saving,
    }


def _quote_inverse(desired_receive: float, rate: float,
                   ranges: list[dict], coupon: Optional[dict]) -> dict:
    """Modo 'recibir': busca el monto a enviar que produce el monto deseado."""
    target = _round(desired_receive)
    # Estimación analítica: invierte la comisión neta para arrancar cerca del valor
    # (send*(1-c_neta)*rate = target). El bucle fino ajusta el residuo por redondeos.
    guess = target / rate if rate else 0.01
    rate_c = _commission_rate_for(ranges, guess)
    try:
        disc = float((coupon or {}).get("discount_percentage", 0) or 0) / 100
    except (TypeError, ValueError):
        disc = 0.0
    net_c = rate_c * (1 - min(max(disc, 0), 1))
    send = _round(max(guess / (1 - net_c) if net_c < 1 else guess, 0.01))
    best = _quote_from_gross_send(send, rate, ranges, coupon)
    best_err = abs(best["amount_receive"] - target)
    q = best
    for _ in range(600):
        if best_err <= 0.005:
            break
        if q["amount_receive"] < target - 0.002:
            send = _round(send + 0.01)
        elif q["amount_receive"] > target + 0.002:
            send = _round(max(0.01, send - 0.01))
        else:
            break
        q = _quote_from_gross_send(send, rate, ranges, coupon)
        err = abs(q["amount_receive"] - target)
        if err < best_err:
            best_err, best = err, q
    return best


def compute(origin: str, destination: str,
            amount: float, mode: str = "send") -> dict:
    """Cotiza validando par/tasa/monto. Devuelve {'error': msg} o el quote."""
    tenant = T.get_config()
    cfg = _cfg()
    language = "es"
    copy = _copy(language)
    supported = pairs()
    if supported and (origin, destination) not in supported:
        listed = ", ".join(f"{a}→{b}" for a, b in supported)
        return {"error": copy["invalid_pair"].format(pairs=listed)}
    if amount is None or amount <= 0:
        return {"error": copy["invalid_amount"]}
    rate = rate_for(origin, destination)
    if rate is None:
        listed = ", ".join(f"{a}→{b}" for a, b in supported) or "—"
        return {"error": copy["invalid_pair"].format(pairs=listed)}
    ranges = cfg.get("commission_ranges") or []
    coupon = cfg.get("coupon") or None
    # Con API activa tampoco se usan comisiones o cupones locales.
    if brasper_api.enabled(tenant):
        ranges = brasper_api.commission_ranges(tenant, origin, destination)
        coupon = brasper_api.best_coupon(tenant, origin, destination)
    fn = _quote_inverse if mode == "receive" else _quote_from_gross_send
    quote = fn(amount, rate, ranges, coupon)
    quote.update({"origin_currency": origin, "destination_currency": destination, "mode": mode})
    return quote


def reply(quote: dict, language: str = "es") -> str:
    """Resumen legible de la cotización (formato del bot real) + CTA de contacto."""
    tenant = T.get_config()
    c = _copy(language)
    if quote.get("error"):
        return quote["error"]
    parts = (
        f"💱 {c['title']} {tenant.get('name', '')}: {c['send']} "
        f"{_fmt(quote['amount_send'])} {quote['origin_currency']}, "
        f"{c['rate']} {quote['rate']:.4f}, "
        f"{c['commission']} {_fmt(quote['commission_gross'])} {quote['origin_currency']}, "
        f"{c['receive']} {_fmt(quote['amount_receive'])} {quote['destination_currency']}."
    )
    if quote.get("coupon_code") and quote.get("coupon_savings_amount"):
        parts += (f" 🎟️ {c['coupon']}: {quote['coupon_code']} "
        f"(-{_fmt(quote['coupon_savings_amount'])} {quote['origin_currency']}).")
    parts += f"\n{c['referential']}"
    # Vigencia del TC (regla del proceso Brasper: la tasa "vive" ~20 min).
    minutes = _tc_validity_minutes()
    if minutes:
        parts += "\n" + c["validity"].format(minutes=minutes)
    # CTA de cierre: con takeover el asesor atiende dentro del bot (no WhatsApp externo).
    parts += "\n" + c["cta"]
    return parts


def _tc_validity_minutes() -> int:
    """Minutos de vigencia del tipo de cambio (0 = sin vigencia). Def: 20."""
    tenant = T.get_config()
    raw = _cfg().get("tc_validity_minutes", 20)
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return 20


def incomplete_reply(language: str = "es") -> str:
    return _copy(language)["incomplete"]


def clarify_reply(request: dict, language: str = "es") -> str:
    """Pregunta concreta cuando el pedido de cotización viene incompleto.

    Nunca decimos que 'no tenemos el tipo de cambio' (las tasas son deterministas):
    pedimos SOLO el dato que falta, con las opciones reales del corredor.
    """
    tenant = T.get_config()
    origin = request.get("origin")
    destination = request.get("destination")
    amount = request.get("amount")
    mode = request.get("mode", "send")
    prs = pairs()
    names = {
        "es": {"PEN": "soles (PEN)", "BRL": "reales (BRL)", "USD": "dólares (USD)"},
        "pt": {"PEN": "soles (PEN)", "BRL": "reais (BRL)", "USD": "dólares (USD)"},
    }
    nm = names.get(language, names["es"])

    def listed(codes: list[str]) -> str:
        return " o ".join(nm.get(c, c) for c in codes)

    if language in ("es", "pt"):
        if origin and not destination:
            opts = sorted({b for a, b in prs if a == origin})
            if opts:
                q = "¿A qué moneda quieres que llegue el dinero" if language == "es" \
                    else "Para qual moeda o dinheiro deve chegar"
                return f"{q}: {listed(opts)}?"
        if destination and not origin:
            opts = sorted({a for a, b in prs if b == destination})
            if opts:
                q = "¿Desde qué moneda vas a enviar" if language == "es" \
                    else "De qual moeda você vai enviar"
                return f"{q}: {listed(opts)}?"
        if amount is None and (origin or destination):
            if language == "es":
                verbo = "recibir" if mode == "receive" else "enviar"
                return f"¿Qué monto quieres {verbo}? Por ejemplo: 500."
            verbo = "receber" if mode == "receive" else "enviar"
            return f"Qual valor você quer {verbo}? Por exemplo: 500."
    return incomplete_reply(language)
