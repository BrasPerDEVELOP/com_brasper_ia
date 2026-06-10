class ChatUseCase:
    def __init__(
        self,
        orchestador,
        llm_port,
        memory_port,
        lead_scoring_case,
        cache_adapter,
        crm_use_case,
        conversation_state_service,
        lead_tracking_service,
        response_builder,
    ):
        self.orchestador = orchestador
        self.memory_port = memory_port
        self.lead_scoring_case = lead_scoring_case
        self.cache_adapter = cache_adapter
        self.crm_use_case = crm_use_case
        self.llm_port = llm_port
        self.conversation_state_service = conversation_state_service
        self.lead_tracking_service = lead_tracking_service
        self.response_builder = response_builder

    def _final_answer_with_llm(self, user_message: str, result, decision: dict, draft: str) -> str:
        if not draft:
            return draft
        try:
            response = self.llm_port.generate_response(
                [
                    {
                        "role": "system",
                        "content": (
                            "Eres el asistente de Brasper. Redacta el mensaje final para el cliente usando "
                            "solo el borrador y los datos estructurados entregados por el backend. "
                            "No inventes tasas, montos, comisiones, cupones, fechas, monedas ni enlaces. "
                            "Conserva exactamente todos los números, códigos de cupón, monedas y URLs. "
                            "No hagas preguntas de seguimiento. Si el borrador indica que faltan datos para "
                            "cotizar, mantén una instrucción breve con el formato requerido."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Mensaje del cliente: {user_message}\n"
                            f"Intent: {decision.get('intent')}\n"
                            f"Tipo de resultado: {getattr(result, 'type', '')}\n"
                            f"Datos backend: {getattr(result, 'metadata', {})}\n"
                            f"Borrador seguro:\n{draft}\n\n"
                            "Devuelve solo el mensaje final."
                        ),
                    },
                ]
            )
            content = str(getattr(response, "content", "") or "").strip()
            return content or draft
        except Exception:
            return draft

    def execute(self, user_id: str, message_user: str, conversation_id: str = "default") -> str:
        context = self.conversation_state_service.load(user_id, message_user, conversation_id=conversation_id)
        result, decision = self.orchestador.run(context)
        self.lead_tracking_service.apply(context, decision, result)

        draft = self.response_builder.build(result)
        answer = self._final_answer_with_llm(message_user, result, decision, draft)
        print(f"USE CASE RESPUESTA ({conversation_id})", answer)
        return answer
