import os
import tempfile
import unittest

from app.application.webchat_flow_use_case import WebchatFlowUseCase
from app.infrastructure.adapter.output.client_directory_adapter import ClientDirectoryAdapter
from app.infrastructure.adapter.output.llm.memory_adapter import MemoryAdapter
from app.infrastructure.adapter.output.webchat_persistence_adapter import WebchatPersistenceAdapter


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.hashes = {}
        self.sets = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def hset(self, key, mapping):
        self.hashes[key] = mapping

    def hgetall(self, key):
        return self.hashes.get(key, {})

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    def sinter(self, keys):
        if not keys:
            return set()
        return set.intersection(*(self.sets.get(key, set()) for key in keys))

    def smembers(self, key):
        return self.sets.get(key, set())

    def keys(self, pattern):
        prefix = pattern.rstrip("*")
        return [key for key in self.store if key.startswith(prefix)]

    def exists(self, key):
        return 1 if key in self.store else 0

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)


class FakeChatUseCase:
    def execute(self, user_id: str, message_user: str) -> str:
        return f"chat:{user_id}:{message_user}"


class SimpleCacheAdapter:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def save(self, key, data, ttl=None):
        self.store[key] = data


class WebchatFlowTests(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        db_path = os.path.join(tmp_dir.name, "webchat.sqlite3")
        self.persistence = WebchatPersistenceAdapter(db_path)
        self.persistence.seed_clients(
            [
                {
                    "id": "client-1",
                    "names": "Esperanza",
                    "lastnames": "Tello Rodríguez",
                    "email": "esperanzacalro10@gmail.com",
                    "document_number": "48647757",
                    "document_type": "dni",
                    "phone": "953090374",
                    "code_phone": "+51",
                }
            ]
        )
        self.cache = SimpleCacheAdapter()
        self.client_directory = ClientDirectoryAdapter(self.persistence)
        self.flow = WebchatFlowUseCase(self.cache, self.persistence, self.client_directory, FakeChatUseCase())

    def test_start_session_returns_profile_buttons(self):
        response = self.flow.start_session()
        self.assertEqual(response["step"], "choose_profile_type")
        self.assertEqual(response["input_mode"], "options")
        self.assertEqual(response["options"][0]["value"], "person")

    def test_identified_customer_goes_to_free_chat(self):
        start = self.flow.start_session()
        session_id = start["session_id"]
        self.flow.handle_message(session_id, "person")
        self.flow.handle_message(session_id, "dni")
        response = self.flow.handle_message(session_id, "48647757")
        self.assertEqual(response["step"], "free_chat")
        self.assertEqual(response["customer_status"], "identified")
        self.assertEqual(response["customer_profile"]["id"], "client-1")

    def test_new_lead_requests_name_after_missing_document(self):
        start = self.flow.start_session()
        session_id = start["session_id"]
        self.flow.handle_message(session_id, "person")
        self.flow.handle_message(session_id, "passport")
        response = self.flow.handle_message(session_id, "AB123456")
        self.assertEqual(response["step"], "confirm_or_complete_profile")
        self.assertEqual(response["customer_status"], "not_found")

    def test_profile_capture_enters_chat(self):
        start = self.flow.start_session()
        session_id = start["session_id"]
        self.flow.handle_message(session_id, "person")
        self.flow.handle_message(session_id, "passport")
        self.flow.handle_message(session_id, "AB123456")
        response = self.flow.handle_message(session_id, "Alberth Castillo")
        self.assertEqual(response["step"], "free_chat")
        self.assertEqual(response["lead_status"], "captured_new_lead")

    def test_free_chat_uses_stable_identity(self):
        start = self.flow.start_session()
        session_id = start["session_id"]
        self.flow.handle_message(session_id, "person")
        self.flow.handle_message(session_id, "dni")
        self.flow.handle_message(session_id, "48647757")
        response = self.flow.handle_message(session_id, "hola")
        self.assertIn("chat:customer:client-1:hola", response["messages"][-1]["text"])

    def test_memory_adapter_persists_to_cache(self):
        memory = MemoryAdapter(self.cache)
        memory.save_memory("web:test", [{"role": "user", "content": "hola"}])
        self.assertEqual(memory.get_memory("web:test")[0]["content"], "hola")
