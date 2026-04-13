from app.domain.ports.output.memoryport import MemoryPort


class MemoryAdapter(MemoryPort):
    def __init__(self, cache_adapter=None):
        self._storage = {}
        self.score_storage = {}
        self.lead_profile_storage = {}
        self.cache_adapter = cache_adapter
        super().__init__()

    def _history_key(self, user_id: str) -> str:
        return f"memory:history:{user_id}"

    def _score_key(self, user_id: str) -> str:
        return f"memory:score:{user_id}"

    def _lead_key(self, user_id: str) -> str:
        return f"memory:lead:{user_id}"

    def save_memory(self, user_id: str, memory: list) -> str:
        print(f"Se guardo la memoria {memory}")
        if user_id not in self._storage:
            self._storage[user_id] = []

        persisted = []
        if self.cache_adapter:
            persisted = self.cache_adapter.get(self._history_key(user_id)) or []

        self._storage[user_id].extend(memory)
        persisted.extend(memory)

        self._storage[user_id] = self._storage[user_id][-10:]
        persisted = persisted[-10:]

        if self.cache_adapter:
            self.cache_adapter.save(self._history_key(user_id), persisted, ttl=None)
        return "okay"

    def get_memory(self, user_id: str):
        if self.cache_adapter:
            persisted = self.cache_adapter.get(self._history_key(user_id))
            if persisted is not None:
                self._storage[user_id] = persisted
                return persisted
        return self._storage.get(user_id, [])

    def save_memory_score(self, user_id: str, memory: dict):
        if user_id not in self.score_storage:
            self.score_storage[user_id] = {"score": 0}

        self.score_storage[user_id] = {"score": memory["score"]}
        if self.cache_adapter:
            self.cache_adapter.save(self._score_key(user_id), self.score_storage[user_id], ttl=None)
        return {"status": "ok"}

    def get_memory_score(self, user_id: str):
        if self.cache_adapter:
            persisted = self.cache_adapter.get(self._score_key(user_id))
            if persisted is not None:
                self.score_storage[user_id] = persisted
                return persisted
        return self.score_storage.get(user_id, {"score": 0})

    def get_memory_lead(self, user_id: str):
        if self.cache_adapter:
            persisted = self.cache_adapter.get(self._lead_key(user_id))
            if persisted is not None:
                self.lead_profile_storage[user_id] = persisted
                return persisted
        return self.lead_profile_storage.get(
            user_id,
            {
                "language": None,
                "destination_currency": None,
                "send_amount": None,
                "origin_currency": None,
                "urgency": None,
            },
        )

    def save_memory_lead(self, user_id: str, memory: dict):
        if user_id not in self.lead_profile_storage:
            self.lead_profile_storage[user_id] = {
                "language": None,
                "destination_currency": None,
                "send_amount": None,
                "origin_currency": None,
                "urgency": None,
            }

        profile = self.lead_profile_storage[user_id]
        for key in ["language", "destination_currency", "send_amount", "origin_currency", "urgency"]:
            if memory.get(key) is not None:
                profile[key] = memory[key]
        if self.cache_adapter:
            self.cache_adapter.save(self._lead_key(user_id), profile, ttl=None)
        return {"status": "ok"}
