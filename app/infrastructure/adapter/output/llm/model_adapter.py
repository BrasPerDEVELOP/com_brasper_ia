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
        
    def generate_summary(self, data: dict):
        """Texto breve para el usuario y el prefill de WhatsApp: solo datos conocidos (sin 'No indicado')."""

        def _present(value) -> bool:
            if value is None:
                return False
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return False
                if s.lower() in ("no indicado", "sin nombre registrado", "n/a", "na"):
                    return False
            return True

        try:
            lang = str(data.get("language") or "es").strip().lower()
            if lang.startswith("pt"):
                lang = "pt"
            elif lang.startswith("en"):
                lang = "en"
            else:
                lang = "es"

            raw_name = str(data.get("name") or "").strip()
            has_name = _present(raw_name) and raw_name.lower() != "sin nombre registrado"

            if lang == "pt":
                lines = (
                    [f"Olá, gostaria de falar com um assessor. Sou {raw_name}."]
                    if has_name
                    else ["Olá, gostaria de falar com um assessor Brasper."]
                )
            elif lang == "en":
                lines = (
                    [f"Hi, I'd like to connect with an advisor. I'm {raw_name}."]
                    if has_name
                    else ["Hi, I'd like to connect with a Brasper advisor."]
                )
            else:
                lines = (
                    [f"Hola, quiero conectar con un asesor. Soy {raw_name}."]
                    if has_name
                    else ["Hola, quiero conectar con un asesor Brasper."]
                )

            doc = str(data.get("documentNumber") or "").strip()
            if _present(doc):
                if lang == "pt":
                    lines.append(f"Documento: {doc}.")
                elif lang == "en":
                    lines.append(f"ID: {doc}.")
                else:
                    lines.append(f"DNI/documento: {doc}.")

            origin = data.get("origin_currency")
            dest = data.get("destination_currency")
            if _present(origin) and _present(dest):
                pair = f"{str(origin).strip().upper()} → {str(dest).strip().upper()}"
                if lang == "pt":
                    lines.append(f"Operação: {pair}.")
                elif lang == "en":
                    lines.append(f"Route: {pair}.")
                else:
                    lines.append(f"Operación: {pair}.")

            send_amt = data.get("send_amount")
            recv_amt = data.get("receive_amount")
            amount_bits = []
            if _present(send_amt):
                if lang == "pt":
                    amount_bits.append(f"enviar {send_amt}")
                elif lang == "en":
                    amount_bits.append(f"send {send_amt}")
                else:
                    amount_bits.append(f"enviar {send_amt}")
            if _present(recv_amt):
                if lang == "pt":
                    amount_bits.append(f"receber {recv_amt}")
                elif lang == "en":
                    amount_bits.append(f"receive {recv_amt}")
                else:
                    amount_bits.append(f"recibir {recv_amt}")
            if amount_bits:
                if lang == "pt":
                    lines.append("Valores: " + " / ".join(amount_bits) + ".")
                elif lang == "en":
                    lines.append("Amounts: " + " / ".join(amount_bits) + ".")
                else:
                    lines.append("Montos: " + " / ".join(amount_bits) + ".")

            if _present(data.get("quote_mode")):
                qm = str(data.get("quote_mode")).strip()
                if lang == "pt":
                    lines.append(f"Modo de cotação: {qm}.")
                elif lang == "en":
                    lines.append(f"Quote mode: {qm}.")
                else:
                    lines.append(f"Modo de cotización: {qm}.")

            if _present(data.get("coupon_code")):
                cc = str(data.get("coupon_code")).strip()
                if lang == "pt":
                    lines.append(f"Cupom: {cc}.")
                elif lang == "en":
                    lines.append(f"Coupon: {cc}.")
                else:
                    lines.append(f"Cupón: {cc}.")

            if _present(data.get("urgency")):
                u = str(data.get("urgency")).strip()
                if lang == "pt":
                    lines.append(f"Urgência: {u}.")
                elif lang == "en":
                    lines.append(f"Urgency: {u}.")
                else:
                    lines.append(f"Urgencia: {u}.")

            # No incluir teléfono (privacidad / el canal ya identifica al usuario).
            message = " ".join(lines)
            return {"summary": message}
        except Exception as e:
            print("Hubo un error", e)
            return {"summary": ""}
