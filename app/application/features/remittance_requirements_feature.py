from app.application.chat_models import DomainEvent, FeatureResult


class RemittanceRequirementsFeature:
    def __init__(self, tool_router, policy_engine, llm_port=None):
        self.tool_router = tool_router
        self.policy_engine = policy_engine
        self.llm_port = llm_port

    def _answer_brasper_info(self, question: str, language: str) -> str:
        fallback = self.policy_engine.copy(language, "brasper_info")
        if not self.llm_port:
            return fallback
        knowledge = """
        Brasper Transferencias:
        - Se dedica a remesas online, cambio de divisas y transferencias internacionales.
        - Está enfocada en operaciones entre Brasil y Perú.
        - Trabaja principalmente con reales brasileños (BRL), soles peruanos (PEN) y dólares estadounidenses (USD).
        - Facilita envíos de dinero y cambios de moneda con rapidez, seguridad, transparencia, tasas competitivas y atención personalizada.
        - Antes de confirmar una operación muestra tipo de cambio, comisión y monto a recibir.
        - Corredores disponibles: BRL a PEN, PEN a BRL, BRL a USD y USD a BRL.
        - No inventes datos legales, licencias, horarios, direcciones, bancos, montos, tasas ni promociones si no están en esta ficha.
        """
        try:
            response = self.llm_port.generate_response(
                [
                    {
                        "role": "system",
                        "content": (
                            "Eres el asistente de Brasper. Responde como una persona de soporte, "
                            "natural y breve, usando solo la ficha de conocimiento. "
                            "Responde exactamente a la pregunta del cliente. "
                            "No conviertas preguntas informativas en cotizaciones. "
                            "No hagas preguntas de seguimiento."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Idioma: {language}\n"
                            f"Ficha de conocimiento:\n{knowledge}\n"
                            f"Pregunta del cliente: {question}\n"
                            "Respuesta:"
                        ),
                    },
                ]
            )
            answer = str(getattr(response, "content", "") or "").strip()
            return answer or fallback
        except Exception:
            return fallback

    def execute(self, context, decision: dict) -> FeatureResult:
        language = decision.get("language") or "es"
        metadata = decision.get("metadata", {})
        message = self.policy_engine.copy(language, "requirements")
        if metadata.get("reason") == "brasper_info":
            message = self._answer_brasper_info(context.message, language)
        elif metadata.get("reason") == "supported_pairs":
            supported = self.tool_router.router({"name": "get_supported_currencies", "args": {}})
            currencies = ", ".join(item["code"] for item in supported.get("currencies", []))
            pairs = ", ".join(
                f"{pair['origin_currency']}->{pair['destination_currency']}"
                for pair in supported.get("pairs", [])
            )
            message = f"{self.policy_engine.copy(language, 'supported_intro')} {currencies}. {pairs}"
        return FeatureResult(
            type="requirements_result",
            message=message,
            metadata=metadata,
            lead_updates=decision.get("extracted_data", {}),
            tracking_events=[DomainEvent(name="intent_detected", payload={"intent": decision.get('intent')})],
        )
