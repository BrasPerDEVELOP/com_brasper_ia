from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict

@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    messages: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.updated_at = datetime.now()
