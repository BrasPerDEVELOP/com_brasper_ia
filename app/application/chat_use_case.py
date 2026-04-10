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

    def execute(self, user_id: str, message_user: str) -> str:
        context = self.conversation_state_service.load(user_id, message_user)
        result, decision = self.orchestador.run(context)
        self.lead_tracking_service.apply(context, decision, result)

        answer = self.response_builder.build(result)
        self.conversation_state_service.remember_turn(user_id, message_user, answer)
        print("USE CASE RESPUESTA", answer)
        return answer
