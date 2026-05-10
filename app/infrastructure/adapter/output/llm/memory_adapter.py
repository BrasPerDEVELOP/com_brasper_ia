from app.domain.ports.output.memoryport import MemoryPort

class MemoryAdapter(MemoryPort):
    def __init__(self, cache_adapter=None):
        self.cache_adapter = cache_adapter
        # Fallback for when cache_adapter is not provided (legacy or testing)
        self._storage = {}
        self.score_storage = {}
        self.lead_profile_storage = {}
        super().__init__()

    def _get_key(self, user_id: str, suffix: str) -> str:
        return f"user:{user_id}:{suffix}"

    # memoria conversacional
    def save_memory(self, user_id: str, memory: list) -> str:
        print(f"Persistiendo memoria en Redis para {user_id}: {memory}")
        if self.cache_adapter:
            key = self._get_key(user_id, "history")
            existing = self.cache_adapter.get(key) or []
            existing.extend(memory)
            # Limitar a los últimos 15 mensajes para no saturar el contexto
            self.cache_adapter.save(key, existing[-15:], ttl=86400) # 24h
            return "okay"
        
        # Fallback in-memory
        if user_id not in self._storage:
            self._storage[user_id] = []
        self._storage[user_id].extend(memory)
        self._storage[user_id] = self._storage[user_id][-10:]
        return "okay"

    # obtener memoria conversacional
    def get_memory(self, user_id: str):
        if self.cache_adapter:
            return self.cache_adapter.get(self._get_key(user_id, "history")) or []
        return self._storage.get(user_id, [])

    # memoria score
    def save_memory_score(self, user_id: str, memory: dict):
        if self.cache_adapter:
            self.cache_adapter.save(self._get_key(user_id, "score"), memory, ttl=86400)
            return {"status": "ok"}
        
        self.score_storage[user_id] = {"score": memory["score"]}
        return {"status": "ok"}

    # obtener memoria score
    def get_memory_score(self, user_id: str):
        if self.cache_adapter:
            return self.cache_adapter.get(self._get_key(user_id, "score")) or {"score": 0}
        return self.score_storage.get(user_id, {"score": 0})

    # obtener memoria bullets
    def get_memory_lead(self, user_id: str):
        default_lead = {
            "language": None,
            "destination_currency": None,
            "send_amount": None,
            "origin_currency": None,
            "urgency": None
        }
        if self.cache_adapter:
            return self.cache_adapter.get(self._get_key(user_id, "lead_profile")) or default_lead
        return self.lead_profile_storage.get(user_id, default_lead)

    # memoria bullets importantes
    def save_memory_lead(self, user_id: str, memory: dict):
        current = self.get_memory_lead(user_id)
        for key in ["language", "destination_currency", "send_amount", "origin_currency", "urgency"]:
            if memory.get(key) is not None:
                current[key] = memory[key]
        
        if self.cache_adapter:
            self.cache_adapter.save(self._get_key(user_id, "lead_profile"), current, ttl=86400)
        else:
            self.lead_profile_storage[user_id] = current
            
        return {"status": "ok"}
