class ConversationOrchestrator:
    def __init__(self, llm_adapter, policy_engine, chat_router):
        self.llm_adapter = llm_adapter
        self.policy_engine = policy_engine
        self.chat_router = chat_router

    def _build_system_prompt(self, history: list[dict], message: str):
        return [
            {
                "role": "system",
                "content": """
                Eres un sistema de extracción de información para un chatbot de remesas y tipo de cambio de Brasper.

                Tu única tarea es:
                1. Clasificar la intención del usuario
                2. Extraer los datos presentes en el mensaje

                El backend decidirá la respuesta final. No inventes tasas, montos ni datos faltantes.
                Detecta siempre el idioma del usuario: "es", "pt" o "en".

                Intents:
                ["greeting","remittance_quote","remittance_requirements","human_handoff","collect_contact"]

                Devuelve SOLO JSON puro:
                {
                  "answer": "respuesta breve para el usuario",
                  "intent": "string",
                  "extracted_data": {
                    "language": "es|pt|en",
                    "name": null,
                    "last": null,
                    "phone": null,
                    "documentNumber": null,
                    "email": null,
                    "origin_currency": null,
                    "destination_currency": null,
                    "send_amount": null,
                    "receive_amount": null,
                    "quote_mode": null,
                    "coupon_code": null,
                    "wants_whatsapp": null,
                    "wants_advisor": null,
                    "urgency": null
                  }
                }
                """,
            },
            *history,
            {"role": "user", "content": message},
        ]

    def _extract_with_llm(self, context):
        response = self.llm_adapter.generate_response(
            self._build_system_prompt(context.history, context.message)
        )
        if not response:
            return {"answer": "", "intent": "", "extracted_data": {}}
        parsed = self.llm_adapter.extract_intent(response.content)
        if "answer" not in parsed:
            parsed["answer"] = response.content or ""
        return parsed

    def run(self, context):
        pre_analysis = self.policy_engine.pre_process(context.message, context.lead_state)
        llm_extract = None if pre_analysis.get("should_skip_llm") else self._extract_with_llm(context)
        decision = self.policy_engine.post_process(
            context.message,
            context.lead_state,
            llm_extract,
            pre_analysis,
        )
        result = self.chat_router.route(context, decision)
        return result, decision
