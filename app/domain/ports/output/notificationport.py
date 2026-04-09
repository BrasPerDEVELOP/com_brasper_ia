from abc import ABC, abstractmethod

class NotificationPort(ABC):
    @abstractmethod
    async def send_message(self, message: str, recipient_id: str, sender_id: str):
        """Sends a message to a recipient."""
        pass
