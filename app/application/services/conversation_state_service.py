from app.application.chat_models import ConversationContext


class ConversationStateService:
    def __init__(self, memory_port, cache_adapter):
        self.memory_port = memory_port
        self.cache_adapter = cache_adapter

    def load(self, user_id: str, message: str, conversation_id: str = "default") -> ConversationContext:
        # Cargamos el historial desde el memory_port (ahora persistente en Redis)
        # Usamos una clave que combina user_id y conversation_id para aislamiento
        full_user_id = f"{user_id}:{conversation_id}"
        history = self.memory_port.get_memory(full_user_id) or []
        
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

    def remember_turn(self, user_id: str, message: str, answer: str, conversation_id: str = "default"):
        # Guardamos el turno en el historial persistente
        full_user_id = f"{user_id}:{conversation_id}"
        turn = [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer}
        ]
        self.memory_port.save_memory(full_user_id, turn)
        
        # También podemos guardar un "log" de la conversación para identificación
        chat_log_key = f"chats:{user_id}"
        self.cache_adapter.add_to_set(chat_log_key, conversation_id)
        
        return "Turn remembered"

    def save_score(self, user_id: str, score: int):
        self.memory_port.save_memory_score(user_id, {"score": score})

    def save_lead_profile(self, user_id: str, lead_profile: dict):
        self.memory_port.save_memory_lead(user_id, lead_profile)

    def save_summary(self, user_id: str, summary: dict):
        self.cache_adapter.save(f"summary{user_id}", summary)

    def save_metrics(self, user_id: str, extract: dict, score: dict):
        self.cache_adapter.save(f"scoreMetrics{user_id}", extract)
        self.cache_adapter.save(f"score{user_id}", score)
