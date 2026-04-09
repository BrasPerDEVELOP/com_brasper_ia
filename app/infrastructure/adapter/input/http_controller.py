import asyncio
import os
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from app.infrastructure.adapter.output.crm_adapter import CRMAdapter
from app.infrastructure.adapter.output.calendar_adapter import CalendarAdapter
from app.application.chat_use_case import ChatUseCase
from app.application.chat_debounce import ChatDebouncer
from app.application.crm_use_case import CRMUseCase
from app.application.calendar_use_case import CalendarUseCase
from app.application.brasper_use_case import BrasperUseCase
from app.infrastructure.redis_connection import redis_from_env
from app.infrastructure.adapter.output.redis_cache_adapter import RedisCacheAdapter
from app.infrastructure.adapter.output.llm.model_adapter import ModelAdapter
from app.infrastructure.adapter.output.llm.memory_adapter import MemoryAdapter
from app.infrastructure.adapter.output.whatsapp_adapter import WhatsappAdapter
from app.application.lead_use_case import LeadUseCase
from app.infrastructure.adapter.output.lead_scoring_adapter import LeadScoringAdapter
from app.application.orchestador.conversation_orchestador import ConversationOrchestrator
from app.infrastructure.adapter.output.llm.tool_router import ToolRouter
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "abcd")
WHATSAPP_TOKEN = os.getenv('wp_key')

router=APIRouter()
#se llama el memory adapter y se implementa en el constructor del modeladapter para almacenamiento previo

calendar_adapter=CalendarAdapter()
calendar_use_case=CalendarUseCase(calendar_adapter)

# Configuración de Redis y el adaptador de caché (REDIS_* en .env)
redis_client = redis_from_env()
redis_cache_adapter = RedisCacheAdapter(redis_client)

crm_adapter=CRMAdapter()
crm_use_case=CRMUseCase(crm_adapter, cache_adapter=redis_cache_adapter)
brasper_use_case = BrasperUseCase()

toolrouter=ToolRouter(calendar_use_case, crm_use_case, brasper_use_case)
memory_adapter=MemoryAdapter()

llm_adapter=ModelAdapter()

lead_scoring_adapter=LeadScoringAdapter()
lead_scoring_use=LeadUseCase(lead_scoring_adapter) # Corrected variable name

orquestador=ConversationOrchestrator(llm_adapter,toolrouter,redis_cache_adapter)

chat_use_case=ChatUseCase(orquestador,llm_adapter,memory_adapter,lead_scoring_use, cache_adapter=redis_cache_adapter, crm_use_case=crm_use_case)
chat_debouncer = ChatDebouncer(chat_use_case.execute)
whatsapp_adapter = WhatsappAdapter()

class Message(BaseModel):
    message: str

#adaptadores de entraa

#realizar peticion al chat
@router.post("/consulta-chat")
async def consultar(user_id: str, message_user: str):
    response = await chat_debouncer.add_and_wait(user_id, message_user)
    return {"response": response}

@router.post("/consulta-webchat")
async def consultarWebChat(message_user: Message):
    response = await chat_debouncer.add_and_wait("51990966022", message_user.message)  # type: ignore[arg-type]
    return {"response": response}

#guardar lead (pruebas)
@router.post("/save-lead")
def savelead(name:str,last:str,phone:str):
    response=crm_use_case.execute(name,last,phone)
    return {"response":response}

#guardar cita
@router.post("/create-date")
def createDate(summary:str,start:str,end:str):
    response=calendar_use_case.execute(summary,start,end)
    return {"response":response}

#obtener citas de google calendar

@router.get("/dates")
def getDate():
    response=calendar_use_case.execute_date()
    return {"response":response}

#Webhook whatsapp
@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: int = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return hub_challenge
    raise HTTPException(status_code=403, detail="Error de verificación")

@router.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    print("Mensaje recibido:", body)

    try:
        # Verifica si es un mensaje de texto de WhatsApp
        if (
            body.get("object") == "whatsapp_business_account"
            and body.get("entry")
            and body["entry"][0].get("changes")
            and body["entry"][0]["changes"][0].get("value")
            and body["entry"][0]["changes"][0]["value"].get("messages")
            and body["entry"][0]["changes"][0]["value"]["messages"][0].get("type") == "text"
        ):
            value = body["entry"][0]["changes"][0]["value"]
            message_info = value["messages"][0]
            phone_number_id = value["metadata"]["phone_number_id"]
            from_number = message_info["from"]
            msg_body = message_info["text"]["body"]

            # Debounce: una sola llamada al LLM por ráfaga; 200 OK rápido a Meta
            asyncio.create_task(
                chat_debouncer.enqueue_whatsapp(
                    from_number, phone_number_id, msg_body, whatsapp_adapter.send_message
                )
            )

    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        # No relanzar la excepción para asegurar que Meta reciba un 200 OK

    # Meta requiere una respuesta 200 OK para confirmar la recepción
    return {"status": "ok"}
