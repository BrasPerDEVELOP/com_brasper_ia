from app.application.chat_models import ConversationContext


class ConversationStateService:
    """
    Modo stateless estricto.

    El chat no guarda ni recupera conversaciones, perfiles, cotizaciones,
    scores, resúmenes ni métricas personales. Tampoco usa Redis para purgar
    claves por usuario: si no hay un identificador confiable de sesión o
    WhatsApp, cada mensaje se procesa únicamente con su propio contenido.
    """

    def __init__(self, memory_port, cache_adapter):
        self.memory_port = memory_port
        self.cache_adapter = cache_adapter

    def load(self, user_id: str, message: str, conversation_id: str = "default") -> ConversationContext:
        return ConversationContext(
            user_id=user_id,
            message=message,
            history=[],
            lead_state={},
            score={"score": 0},
            summary={},
        )

    def remember_turn(self, user_id: str, message: str, answer: str, conversation_id: str = "default"):
        return "Turn not persisted"

    def save_score(self, user_id: str, score: int):
        return {"status": "not_persisted"}

    def save_lead_profile(self, user_id: str, lead_profile: dict):
        return {"status": "not_persisted"}

    def save_summary(self, user_id: str, summary: dict):
        return {"status": "not_persisted"}

    def save_metrics(self, user_id: str, extract: dict, score: dict):
        return {"status": "not_persisted"}
