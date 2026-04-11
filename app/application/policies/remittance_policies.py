import re


class RemittancePolicyEngine:
    _CURRENCY_ALIASES = {
        "USD": {"usd", "dolar", "dolares", "dólar", "dólares", "dollar", "dollars", "usdt"},
        "PEN": {"pen", "sol", "soles", "nuevo sol", "nuevos soles"},
        "BRL": {"brl", "real", "reales", "real brasileño", "reais"},
    }

    _GREETINGS = ("hola", "buenas", "buen día", "buen dia", "hello", "hi", "olá", "ola")
    _COUPON_KEYWORDS = (
        "coupon",
        "coupons",
        "cupon",
        "cupones",
        "cupón",
        "cupons",
        "cupom",
        "promoción",
        "promocion",
        "descuento",
        "descuentos",
    )
    _HANDOFF_KEYWORDS = (
        "asesor",
        "advisor",
        "agente",
        "humano",
        "whatsapp",
        "representante",
        "attendant",
    )
    _SUPPORTED_QUERY_KEYWORDS = ("currency", "currencies", "moneda", "monedas", "moeda", "moedas", "pair", "par")
    _REMITTANCE_HINTS = (
        "cotiza",
        "cotizar",
        "cotizacion",
        "cotización",
        "quote",
        "cambio",
        "cambiar",
        "enviar",
        "receber",
        "recibir",
        "transferir",
        "remesa",
        "remittance",
    )
    _EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    _AMOUNT_RE = re.compile(r"(?<!\w)(\d+(?:[.,]\d{1,2})?)(?!\w)")
    _RECEIVE_KEYWORDS = ("recibir", "receive", "receber")
    _SEND_KEYWORDS = ("enviar", "send", "mandar", "transferir")

    def __init__(self, tool_router=None):
        self.tool_router = tool_router
        self._supported_cache = None

    def _supported(self):
        if self._supported_cache is not None:
            return self._supported_cache
        if self.tool_router:
            try:
                self._supported_cache = self.tool_router.router(
                    {"name": "get_supported_currencies", "args": {}}
                )
                return self._supported_cache
            except Exception:
                pass
        self._supported_cache = {
            "currencies": [{"code": "BRL"}, {"code": "PEN"}, {"code": "USD"}],
            "pairs": [
                {"origin_currency": "BRL", "destination_currency": "PEN"},
                {"origin_currency": "PEN", "destination_currency": "BRL"},
                {"origin_currency": "BRL", "destination_currency": "USD"},
                {"origin_currency": "USD", "destination_currency": "BRL"},
            ],
        }
        return self._supported_cache

    def copy(self, language: str, key: str) -> str:
        dictionary = {
            "es": {
                "greeting": "Hola, soy el asistente de Brasper. Puedo ayudarte con cotizaciones, comisiones, cupones activos y derivación por WhatsApp.",
                "fallback": "Puedo ayudarte con cotizaciones Brasper, cupones activos y derivación con un asesor.",
                "ask_origin": "¿Qué moneda deseas enviar? Por ejemplo PEN, BRL o USD.",
                "ask_destination": "¿Qué moneda deseas recibir? Por ejemplo BRL, PEN o USD.",
                "ask_amount": "Indícame cuánto deseas enviar o cuánto deseas recibir para cotizar.",
                "requirements": "Brasper cotiza corredores BRL a PEN, PEN a BRL, BRL a USD y USD a BRL.",
                "contact_ok": "Listo, registré tu contacto para continuar con tu consulta.",
                "need_name": "Para registrarte, compárteme tu nombre y apellido.",
                "need_email": "Compárteme tu correo para dejar registrada tu consulta.",
                "quote_suffix": "Si deseas, también te preparo el mensaje listo para WhatsApp.",
                "coupons_none": "Hoy no hay cupones activos disponibles para ese corredor.",
                "supported_intro": "Monedas y corredores disponibles:",
                "invalid_pair": "Brasper solo opera BRL a PEN, PEN a BRL, BRL a USD y USD a BRL.",
                "invalid_amount": "Necesito un monto válido mayor a 0 para ayudarte con la cotización.",
            },
            "pt": {
                "greeting": "Olá, sou o assistente da Brasper. Posso ajudar com cotações, comissões, cupons ativos e atendimento por WhatsApp.",
                "fallback": "Posso ajudar com cotações da Brasper, cupons ativos e encaminhamento para um assessor.",
                "ask_origin": "Qual moeda você quer enviar? Por exemplo PEN, BRL ou USD.",
                "ask_destination": "Qual moeda você quer receber? Por exemplo BRL, PEN ou USD.",
                "ask_amount": "Informe quanto deseja enviar ou quanto deseja receber para cotar.",
                "requirements": "A Brasper cota corredores BRL para PEN, PEN para BRL, BRL para USD e USD para BRL.",
                "contact_ok": "Pronto, registrei seu contato para continuar com a consulta.",
                "need_name": "Para registrar, compartilhe seu nome e sobrenome.",
                "need_email": "Compartilhe seu e-mail para registrar sua consulta.",
                "quote_suffix": "Se quiser, também posso preparar a mensagem pronta para WhatsApp.",
                "coupons_none": "Hoje não há cupons ativos disponíveis para esse corredor.",
                "supported_intro": "Moedas e corredores disponíveis:",
                "invalid_pair": "A Brasper opera apenas BRL para PEN, PEN para BRL, BRL para USD e USD para BRL.",
                "invalid_amount": "Preciso de um valor válido maior que 0 para ajudar com a cotação.",
            },
            "en": {
                "greeting": "Hello, I am the Brasper assistant. I can help with quotes, commissions, active coupons, and WhatsApp handoff.",
                "fallback": "I can help with Brasper quotes, active coupons, and advisor handoff.",
                "ask_origin": "Which currency do you want to send? For example PEN, BRL, or USD.",
                "ask_destination": "Which currency do you want to receive? For example BRL, PEN, or USD.",
                "ask_amount": "Tell me how much you want to send or receive so I can quote it.",
                "requirements": "Brasper quotes BRL to PEN, PEN to BRL, BRL to USD, and USD to BRL corridors.",
                "contact_ok": "Done, I registered your contact so we can continue your request.",
                "need_name": "To register you, please share your first and last name.",
                "need_email": "Please share your email so I can register your request.",
                "quote_suffix": "If you want, I can also prepare the ready-to-send WhatsApp message.",
                "coupons_none": "There are no active coupons available for that corridor today.",
                "supported_intro": "Available currencies and corridors:",
                "invalid_pair": "Brasper currently supports only BRL to PEN, PEN to BRL, BRL to USD, and USD to BRL.",
                "invalid_amount": "I need a valid amount greater than 0 to help with the quote.",
            },
        }
        return dictionary.get(language, dictionary["es"]).get(key, dictionary["es"]["fallback"])

    def _normalize_language(self, value) -> str:
        language = (value or "es").lower()
        if language not in {"es", "pt", "en"}:
            return "es"
        return language

    def _normalize_currency(self, value):
        if not value:
            return None
        lowered = str(value).strip().lower()
        normalized = lowered.replace("$", "").replace(".", "").strip()
        for code, aliases in self._CURRENCY_ALIASES.items():
            if normalized in aliases or lowered.upper() == code:
                return code
        return None

    def _extract_currencies_from_message(self, message: str) -> list[str]:
        normalized_text = self._normalize_text(message)
        matches = []
        for code, aliases in self._CURRENCY_ALIASES.items():
            positions = [normalized_text.find(alias) for alias in aliases if normalized_text.find(alias) >= 0]
            if positions:
                matches.append((min(positions), code))
        matches.sort(key=lambda item: item[0])
        seen = set()
        ordered = []
        for _, code in matches:
            if code in seen:
                continue
            seen.add(code)
            ordered.append(code)
        return ordered

    def _parse_amount(self, value):
        if value is None or value == "":
            return None
        try:
            return round(float(str(value).replace(",", ".")), 2)
        except (TypeError, ValueError):
            return None

    def _extract_amount(self, message: str):
        match = self._AMOUNT_RE.search(message or "")
        if not match:
            return None
        return self._parse_amount(match.group(1))

    def _normalize_text(self, message: str) -> str:
        return " ".join((message or "").lower().split())

    def _supported_pairs(self) -> set[tuple[str, str]]:
        supported = self._supported()
        return {
            (pair["origin_currency"], pair["destination_currency"])
            for pair in supported.get("pairs", [])
            if pair.get("origin_currency") and pair.get("destination_currency")
        }

    def _is_valid_pair(self, origin_currency, destination_currency) -> bool:
        if not origin_currency or not destination_currency:
            return True
        return (origin_currency, destination_currency) in self._supported_pairs()

    def _coerce_boolean(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        lowered = str(value).strip().lower()
        if lowered in {"true", "1", "yes", "si", "sí", "sim"}:
            return True
        if lowered in {"false", "0", "no", "nao", "não"}:
            return False
        return None

    def _name_parts(self, message: str):
        if self._EMAIL_RE.search(message or ""):
            return None, None
        cleaned = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñÇçãõâêôü'\-\s]", " ", message or "")
        tokens = [token for token in cleaned.split() if len(token) > 1]
        if len(tokens) < 2:
            return None, None
        lower_tokens = [token.lower() for token in tokens]
        if any(token in self._REMITTANCE_HINTS for token in lower_tokens):
            return None, None
        return tokens[0].title(), tokens[1].title()

    def _infer_language_from_message(self, message: str) -> str:
        lowered = self._normalize_text(message)
        tokens = set(re.findall(r"[a-záéíóúñçãõâêôü]+", lowered))
        if tokens.intersection({"olá", "ola", "quero", "cotação", "assessor"}):
            return "pt"
        if tokens.intersection({"hello", "quote", "advisor"}):
            return "en"
        return "es"

    def _merge_slots(self, base: dict, update: dict) -> dict:
        merged = dict(base or {})
        for key, value in (update or {}).items():
            if value is None or value == "":
                continue
            merged[key] = value
        return merged

    def _extract_message_slot_overrides(self, message: str) -> dict:
        lowered = self._normalize_text(message)
        currencies = self._extract_currencies_from_message(message)
        overrides = {}

        extracted_amount = self._extract_amount(message)
        if extracted_amount is not None:
            if any(token in lowered for token in self._RECEIVE_KEYWORDS):
                overrides["receive_amount"] = extracted_amount
                overrides["send_amount"] = None
                overrides["quote_mode"] = "receive"
            elif any(token in lowered for token in self._SEND_KEYWORDS):
                overrides["send_amount"] = extracted_amount
                overrides["receive_amount"] = None
                overrides["quote_mode"] = "send"

        if len(currencies) >= 2:
            first_currency, second_currency = currencies[0], currencies[1]
            if any(token in lowered for token in self._RECEIVE_KEYWORDS):
                overrides["origin_currency"] = second_currency
                overrides["destination_currency"] = first_currency
            else:
                overrides["origin_currency"] = first_currency
                overrides["destination_currency"] = second_currency
        elif len(currencies) == 1:
            if any(token in lowered for token in self._RECEIVE_KEYWORDS):
                overrides["destination_currency"] = currencies[0]
            elif any(token in lowered for token in self._SEND_KEYWORDS):
                overrides["origin_currency"] = currencies[0]

        email_match = self._EMAIL_RE.search(message or "")
        if email_match:
            overrides["email"] = email_match.group(0).lower()

        name, last = self._name_parts(message)
        if name:
            overrides["name"] = name
        if last:
            overrides["last"] = last

        if "whatsapp" in lowered:
            overrides["wants_whatsapp"] = True
        if any(keyword in lowered for keyword in self._HANDOFF_KEYWORDS):
            overrides["wants_advisor"] = True

        return overrides

    def _normalize_slots(self, slots: dict, message: str) -> dict:
        slots = dict(slots or {})
        message_overrides = self._extract_message_slot_overrides(message)
        slots.update({k: v for k, v in message_overrides.items() if v is not None})

        currencies = self._extract_currencies_from_message(message)
        origin_currency = self._normalize_currency(slots.get("origin_currency"))
        destination_currency = self._normalize_currency(slots.get("destination_currency"))

        amount = self._parse_amount(slots.get("send_amount"))
        receive_amount = self._parse_amount(slots.get("receive_amount"))
        extracted_amount = self._extract_amount(message)

        if amount is None and receive_amount is None and extracted_amount is not None:
            lowered = self._normalize_text(message)
            if any(token in lowered for token in ("recibir", "receive", "receber")):
                receive_amount = extracted_amount
                slots["quote_mode"] = slots.get("quote_mode") or "receive"
            else:
                amount = extracted_amount
                slots["quote_mode"] = slots.get("quote_mode") or "send"
        elif extracted_amount is not None:
            current_mode = str(slots.get("quote_mode") or "").lower()
            if current_mode == "receive":
                receive_amount = extracted_amount
                amount = None
            elif current_mode == "send" or not current_mode:
                amount = extracted_amount
                receive_amount = None
                slots["quote_mode"] = current_mode or "send"

        wants_whatsapp = self._coerce_boolean(slots.get("wants_whatsapp"))
        wants_advisor = self._coerce_boolean(slots.get("wants_advisor"))
        lowered = self._normalize_text(message)
        if wants_whatsapp is None and "whatsapp" in lowered:
            wants_whatsapp = True
        if wants_advisor is None and any(keyword in lowered for keyword in self._HANDOFF_KEYWORDS):
            wants_advisor = True

        quote_mode = str(slots.get("quote_mode") or "").lower() or None
        if not quote_mode and receive_amount is not None:
            quote_mode = "receive"
        if not quote_mode and amount is not None:
            quote_mode = "send"

        normalized = {
            "language": self._normalize_language(slots.get("language") or self._infer_language_from_message(message)),
            "name": slots.get("name"),
            "last": slots.get("last"),
            "phone": slots.get("phone"),
            "documentNumber": slots.get("documentNumber"),
            "email": slots.get("email"),
            "origin_currency": origin_currency,
            "destination_currency": destination_currency,
            "send_amount": amount,
            "receive_amount": receive_amount,
            "quote_mode": quote_mode,
            "coupon_code": slots.get("coupon_code"),
            "wants_whatsapp": wants_whatsapp,
            "wants_advisor": wants_advisor,
            "urgency": slots.get("urgency"),
        }
        return normalized

    def _detect_intent(self, message: str, normalized_slots: dict) -> tuple[str | None, str | None]:
        lowered = self._normalize_text(message)
        has_quote_signal = (
            any(keyword in lowered for keyword in self._REMITTANCE_HINTS)
            or normalized_slots.get("origin_currency")
            or normalized_slots.get("destination_currency")
            or normalized_slots.get("send_amount") is not None
            or normalized_slots.get("receive_amount") is not None
        )
        if any(keyword in lowered for keyword in self._COUPON_KEYWORDS):
            return "remittance_requirements", "coupon_lookup"
        if any(keyword in lowered for keyword in self._HANDOFF_KEYWORDS):
            return "human_handoff", "advisor_request"
        if any(keyword in lowered for keyword in self._GREETINGS) and len(lowered.split()) <= 4:
            return "greeting", "greeting"
        if any(keyword in lowered for keyword in self._SUPPORTED_QUERY_KEYWORDS):
            return "remittance_requirements", "supported_pairs"
        if has_quote_signal:
            return "remittance_quote", "quote_detected"
        if normalized_slots.get("email") or (normalized_slots.get("name") and normalized_slots.get("last")):
            return "collect_contact", "contact_data"
        return None, None

    def _validation_error(self, normalized_slots: dict) -> str | None:
        language = normalized_slots.get("language") or "es"
        amount = normalized_slots.get("send_amount")
        receive_amount = normalized_slots.get("receive_amount")
        if amount is not None and amount <= 0:
            return self.copy(language, "invalid_amount")
        if receive_amount is not None and receive_amount <= 0:
            return self.copy(language, "invalid_amount")
        origin_currency = normalized_slots.get("origin_currency")
        destination_currency = normalized_slots.get("destination_currency")
        if origin_currency and destination_currency and not self._is_valid_pair(origin_currency, destination_currency):
            return self.copy(language, "invalid_pair")
        return None

    def pre_process(self, message: str, lead_state: dict | None = None) -> dict:
        lead_state = lead_state or {}
        normalized_slots = self._normalize_slots(lead_state, message)
        intent, reason = self._detect_intent(message, normalized_slots)
        validation_error = self._validation_error(normalized_slots)
        direct_intents = {"greeting", "human_handoff", "remittance_requirements", "remittance_quote"}
        should_skip_llm = intent in direct_intents and reason != "contact_data"
        return {
            "intent": intent,
            "reason": reason,
            "normalized_slots": normalized_slots,
            "validation_error": validation_error,
            "should_skip_llm": should_skip_llm,
        }

    def post_process(self, message: str, lead_state: dict, llm_extract: dict | None, pre_analysis: dict) -> dict:
        llm_extract = llm_extract or {"intent": "", "extracted_data": {}, "answer": ""}
        llm_slots = self._normalize_slots(llm_extract.get("extracted_data", {}), message)
        merged_slots = self._merge_slots(lead_state, pre_analysis.get("normalized_slots", {}))
        merged_slots = self._merge_slots(merged_slots, llm_slots)

        intent, reason = self._detect_intent(message, merged_slots)
        final_intent = intent or llm_extract.get("intent") or pre_analysis.get("intent") or "remittance_requirements"
        if pre_analysis.get("intent") in {"human_handoff", "remittance_requirements"}:
            final_intent = pre_analysis["intent"]
        validation_error = self._validation_error(merged_slots) or pre_analysis.get("validation_error")
        metadata = {
            "reason": reason or pre_analysis.get("reason"),
            "validation_error": validation_error,
            "llm_answer": llm_extract.get("answer", ""),
        }
        tracking_events = [
            {"name": "message_received", "payload": {"message": message}},
            {"name": "intent_detected", "payload": {"intent": final_intent, "reason": metadata["reason"]}},
        ]
        return {
            "intent": final_intent,
            "language": merged_slots.get("language") or "es",
            "extracted_data": merged_slots,
            "metadata": metadata,
            "tracking_events": tracking_events,
        }
