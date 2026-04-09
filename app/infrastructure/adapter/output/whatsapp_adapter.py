import os
import httpx
from app.domain.ports.output.notificationport import NotificationPort

WHATSAPP_TOKEN = os.getenv('wp_key')

class WhatsappAdapter(NotificationPort):
    
    async def send_message(self, message: str, recipient_id: str, sender_id: str):
        """
        Sends a WhatsApp message using Meta's Graph API.
        - message: The text to send.
        - recipient_id: The user's phone number.
        - sender_id: The business phone number ID from which to send.
        """
        if not WHATSAPP_TOKEN:
            print("Error: La variable de entorno WHATSAPP_TOKEN (o wp_key) no está configurada.")
            return

        url = f"https://graph.facebook.com/v23.0/{sender_id}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "text",
            "text": {"body": message},
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=data)
                response.raise_for_status()
                print("Respuesta enviada a WhatsApp:", response.json())
            except httpx.HTTPStatusError as e:
                print(f"Error al enviar mensaje a WhatsApp: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                print(f"Ocurrió un error inesperado al enviar el mensaje: {e}")
