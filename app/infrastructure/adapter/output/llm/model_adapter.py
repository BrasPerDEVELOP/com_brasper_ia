from app.domain.ports.output.llmport import LLMPort

from langchain_openai import ChatOpenAI
from app.infrastructure.adapter.output.llm.tools.get_supported_currencies_schema import get_supported_currencies_schema
from app.infrastructure.adapter.output.llm.tools.get_exchange_rates_schema import get_exchange_rates_schema
from app.infrastructure.adapter.output.llm.tools.get_commission_ranges_schema import get_commission_ranges_schema
from app.infrastructure.adapter.output.llm.tools.get_active_coupons_schema import get_active_coupons_schema
from app.infrastructure.adapter.output.llm.tools.quote_exchange_operation_schema import quote_exchange_operation_schema
from app.infrastructure.adapter.output.llm.tools.build_whatsapp_quote_message_schema import build_whatsapp_quote_message_schema
from app.infrastructure.adapter.output.llm.tools.handoff_to_advisor_schema import handoff_to_advisor_schema
import os
import re
from dotenv import load_dotenv
load_dotenv()
import json

# DeepSeek: usa DEEPSEEK_API_KEY; si no existe, OPENAI_API_KEY (compatible con LangChain)
api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError(
        "Falta la API key del LLM. Define DEEPSEEK_API_KEY o OPENAI_API_KEY en tu .env"
    )
tool_calls = [
    get_supported_currencies_schema,
    get_exchange_rates_schema,
    get_commission_ranges_schema,
    get_active_coupons_schema,
    quote_exchange_operation_schema,
    build_whatsapp_quote_message_schema,
    handoff_to_advisor_schema,
]

class ModelAdapter(LLMPort):
    #instanciar en el constructor el memoryport
    def __init__(self):
        self.llm=ChatOpenAI(
                            model="deepseek-chat",
                            api_key=api_key,
                            base_url="https://api.deepseek.com/v1",
                            temperature=0,
                            max_tokens=500
        )
        #extraer respuesta
    def generate_response(self, messages:list):
        try:
            #primera llamda
            response=self.llm.invoke(messages)
            return response

        except Exception as e:
            print("Error LLM:", e)
            return None
        
    def _fallback(self):
        return {
            "intent": "unknown",
            "extracted_data": {}
        }    
    
    def extract_intent(self, messages:str):
       
        if not messages:
            return self._fallback()

        content = messages.strip()
        print("CONTENIDO STRIP ",content)
        # 1. limpiar markdown ```json
        if content.startswith("```"):
            content = content.replace("```json", "").replace("```", "").strip()

        # 2. extraer JSON aunque venga con texto
        try:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                content = match.group()
        except:
            return self._fallback()

        # 3. parsear JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return self._fallback()

        #  4. validar estructura mínima
        if "intent" not in data or "extracted_data" not in data:
            return self._fallback()

        return data
    def extract(self, text: str, userId: str) -> dict:
       
        try:

            content = text or ""
            print("respuesta cruda:", content)

            #match = re.search(r"\{.*\}", content, re.DOTALL)
            
            extract = {
                "answer": content,
                "intent": [],
                "extracted_data": {}
            }
            match = re.search(r"\{[\s\S]*", content, re.DOTALL)
            if match:
                json_str = match.group(0)

                # cerrar JSON si el modelo lo cortó
                if not json_str.strip().endswith("}"):
                    json_str = json_str + "}}"

                try:
                    parsed = json.loads(json_str)

                    extract["answer"] = parsed.get("answer", content)
                    extract["intent"] = parsed.get("intent", [])
                    extract["extracted_data"] = parsed.get("extracted_data", {})
                except json.JSONDecodeError:
                    pass
            # asegurar estructura
            if "extracted_data" not in extract or not isinstance(extract["extracted_data"], dict):
                extract["extracted_data"] = {}

            # guardar telefono desde userId
            if userId:
                extract["extracted_data"]["phone"] = userId

            # eliminar phone si vino afuera
            extract.pop("phone", None)

            return extract
            

        except Exception as e:
            print("Error en extractor:", e)

            return {
                "answer": text,
                "intent": [],
                "extracted_data": {"phone": userId}
        }
        
    def generate_summary(self,data:dict):
        try:
            
            message= (
                f"Cliente {data.get('name')} con DNI {data.get('documentNumber')} "
                f"Telefono {data.get('phone')}. Consulta remesa en idioma {data.get('language')} "
                f"desde {data.get('origin_currency')} hacia {data.get('destination_currency')}. "
                f"Monto a enviar {data.get('send_amount')} y monto a recibir {data.get('receive_amount')}. "
                f"Modo {data.get('quote_mode')} cupón {data.get('coupon_code')} y urgencia {data.get('urgency')}."                
            )
            #f"Cliente {bullets_list[4]}  con DNI {bullets_list[6]} y telefono {bullets_list[6]}. busca en zonas {bullets_list[0]} su presupuesto es de {bullets_list[1]} agendo cita: {bullets_list[2]} es urgente {bullets_list[3]}"
            return {"summary":message}
        except Exception as e:
            print("Hubo un error", e)
