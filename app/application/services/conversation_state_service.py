from app.application.chat_models import ConversationContext


class ConversationStateService:
    def __init__(self, memory_port, cache_adapter):
        self.memory_port = memory_port
        self.cache_adapter = cache_adapter

    def load(self, user_id: str, message: str) -> ConversationContext:
        # Cada consulta entra aislada: no reutilizamos historial conversacional previo.
        history = []
        cached_lead = self.cache_adapter.get(f"lead:{user_id}") or {}
        memory_lead = self.memory_port.get_memory_lead(user_id) or {}
        lead_state = {**cached_lead, **memory_lead}
        score = self.memory_port.get_memory_score(user_id) or {"score": 0}
        summary = self.cache_adapter.get(f"summary{user_id}") or {}
        return ConversationContext(
            user_id=user_id,
            message=message,
            history=history,
            lead_state=lead_state,
            score=score,
            summary=summary,
        )

    def remember_turn(self, user_id: str, message: str, answer: str):
        # Se desactiva la persistencia del chat para evitar contexto acumulado
        # entre preguntas independientes.
        return None

    def save_score(self, user_id: str, score: int):
        self.memory_port.save_memory_score(user_id, {"score": score})

    def save_lead_profile(self, user_id: str, lead_profile: dict):
        self.memory_port.save_memory_lead(user_id, lead_profile)

    def save_summary(self, user_id: str, summary: dict):
        self.cache_adapter.save(f"summary{user_id}", summary)

    def save_metrics(self, user_id: str, extract: dict, score: dict):
        self.cache_adapter.save(f"scoreMetrics{user_id}", extract)
        self.cache_adapter.save(f"score{user_id}", score)
