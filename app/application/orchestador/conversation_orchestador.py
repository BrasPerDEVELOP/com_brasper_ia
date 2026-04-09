class ConversationOrchestrator:

    def __init__(self, llm_adapter, tool_router, cache_adapter):
        self.llm_adapter = llm_adapter
        self.tool_router = tool_router
        self.cache_adapter = cache_adapter

    def run(self, messages, userId):
        response = self.llm_adapter.generate_response(messages)
        if not response:
            return "En este momento no puedo responder insufficient TOKEN", {}

        extract = self.llm_adapter.extract_intent(response.content)
        intent = extract.get("intent")
        data = extract.get("extracted_data", {})

        existing_lead_data = self.cache_adapter.get(f"lead:{userId}") or {}
        clean_new_data = {k: v for k, v in data.items() if v is not None}
        combined_data = {**existing_lead_data, **clean_new_data}
        self.cache_adapter.save(f"lead:{userId}", combined_data)
        data = combined_data
        extract["extracted_data"] = data
        language = data.get("language") or "es"

        if intent == "greeting":
            # Priorizar la respuesta del LLM (JSON "answer"); el texto fijo solo como respaldo.
            answer_text = (extract.get("answer") or "").strip()
            if answer_text:
                return answer_text, extract
            return self._copy(language, "greeting"), extract

        if intent == "remittance_requirements":
            return self._handle_requirements(data, messages[-1]["content"], language), extract

        if intent == "human_handoff":
            handoff = self.tool_router.router({
                "name": "handoff_to_advisor",
                "args": {
                    "language": language,
                    "summary": (self.cache_adapter.get(f"summary{userId}") or {}).get("summary", ""),
                },
            })
            return self._format_handoff_response(handoff, language), extract

        if intent == "collect_contact":
            return self._handle_contact_collection(data, language), extract

        if intent == "remittance_quote":
            return self._handle_quote(data, language), extract

        answer = extract.get("answer", response.content or "")
        if not answer or answer.strip() == "":
            answer = self._copy(language, "fallback")
        return answer, extract

    def extract(self, text: str, userId) -> dict:
        return self.llm_adapter.extract(text, userId)

    def summary(self, data: dict):
        return self.llm_adapter.generate_summary(data)

    def _copy(self, language, key):
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
            },
        }
        return dictionary.get(language, dictionary["es"]).get(key, dictionary["es"]["fallback"])

    def _format_handoff_response(self, handoff, language):
        message = handoff.get("message", self._copy(language, "fallback"))
        wa_link = handoff.get("wa_link")
        return f"{message}\n\n{wa_link}" if wa_link else message

    def _handle_contact_collection(self, data, language):
        if not data.get("name") or not data.get("last"):
            return self._copy(language, "need_name")
        if not data.get("email"):
            return self._copy(language, "need_email")
        return self._copy(language, "contact_ok")

    def _handle_requirements(self, data, user_message, language):
        lowered = (user_message or "").lower()
        if any(keyword in lowered for keyword in ["coupon", "cupon", "cupón", "cupom"]):
            coupons = self.tool_router.router({
                "name": "get_active_coupons",
                "args": {
                    "origin_currency": data.get("origin_currency"),
                    "destination_currency": data.get("destination_currency"),
                },
            })
            items = coupons.get("coupons", [])
            if not items:
                return self._copy(language, "coupons_none")
            return "\n".join(
                f"{item['code']} - {item['discount_percentage']:.0f}% - {item['origin_currency']}->{item['destination_currency']} - {item['start_date']} / {item['end_date']}"
                for item in items
            )

        if any(keyword in lowered for keyword in ["currency", "currencies", "moneda", "monedas", "moeda", "moedas", "pair", "par"]):
            supported = self.tool_router.router({"name": "get_supported_currencies", "args": {}})
            currencies = ", ".join(item["code"] for item in supported.get("currencies", []))
            pairs = ", ".join(
                f"{pair['origin_currency']}->{pair['destination_currency']}"
                for pair in supported.get("pairs", [])
            )
            return f"{self._copy(language, 'supported_intro')} {currencies}. {pairs}"

        return self._copy(language, "requirements")

    def _handle_quote(self, data, language):
        if not data.get("origin_currency"):
            return self._copy(language, "ask_origin")
        if not data.get("destination_currency"):
            return self._copy(language, "ask_destination")

        amount = data.get("send_amount")
        mode = "send"
        if amount is None and data.get("receive_amount") is not None:
            amount = data.get("receive_amount")
            mode = "receive"
        if data.get("quote_mode") in ("send", "receive"):
            mode = data.get("quote_mode")
        if amount is None:
            return self._copy(language, "ask_amount")

        quote = self.tool_router.router({
            "name": "quote_exchange_operation",
            "args": {
                "origin_currency": data.get("origin_currency"),
                "destination_currency": data.get("destination_currency"),
                "amount": amount,
                "mode": mode,
                "language": language,
            },
        })
        if quote.get("error"):
            return quote["error"]

        answer = quote.get("summary_text", self._copy(language, "fallback"))
        wants_whatsapp = str(data.get("wants_whatsapp") or "").lower() in ("true", "1", "yes", "si", "sí", "sim")
        wants_advisor = str(data.get("wants_advisor") or "").lower() in ("true", "1", "yes", "si", "sí", "sim")

        if wants_whatsapp:
            whatsapp = self.tool_router.router({
                "name": "build_whatsapp_quote_message",
                "args": {
                    "origin_currency": quote.get("origin_currency"),
                    "destination_currency": quote.get("destination_currency"),
                    "amount_send": quote.get("amount_send"),
                    "amount_receive": quote.get("amount_receive"),
                    "commission": quote.get("commission"),
                    "total_to_send": quote.get("total_to_send"),
                    "rate": quote.get("rate"),
                    "coupon_code": quote.get("coupon_code"),
                    "coupon_savings_amount": quote.get("coupon_savings_amount"),
                    "language": language,
                },
            })
            return f"{answer}\n\n{whatsapp.get('wa_link')}"

        if wants_advisor:
            handoff = self.tool_router.router({
                "name": "handoff_to_advisor",
                "args": {"language": language, "summary": answer},
            })
            return self._format_handoff_response(handoff, language)

        return f"{answer}\n\n{self._copy(language, 'quote_suffix')}"
