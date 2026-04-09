from datetime import date
class ChatUseCase:
    def __init__(self,orchestador,llm_port,memory_port,lead_scoring_case, cache_adapter, crm_use_case):

        self.orchestador=orchestador
        self.memory_port=memory_port
        self.lead_scoring_case=lead_scoring_case
        self.cache_adapter=cache_adapter
        self.crm_use_case=crm_use_case
        self.llm_port=llm_port


    def execute(self,user_id:str,message_user:str)->str:
        history=self.memory_port.get_memory(user_id) or []
        #limitar la memoria
        history = history[-4:]
        today_str = date.today().strftime("%A, %Y-%m-%d")
        system_prompt=[
            {
            "role": "system",
            "content": f"""
            Eres un sistema de extracción de información para un chatbot de remesas y tipo de cambio de Brasper.

            Tu única tarea es:

            1. Clasificar la intención del usuario
            2. Extraer los datos presentes en el mensaje

            Da una respuesta breve y útil para el usuario solo si el mensaje ya permite responder.
            NO inventes tasas, montos ni datos faltantes.
            NO confirmes operaciones como si ya hubieran sido ejecutadas.
            NO completes información faltante.
            Detecta siempre el idioma del usuario: "es", "pt" o "en".

            El backend se encargará de la conversación.
            
            Intents:
            ["greeting","remittance_quote","remittance_requirements","human_handoff","collect_contact"]

            Devuelve SOLO JSON puro:
            NO incluyas:
            - ```json
            - ``` 
            - texto adicional
            - explicaciones
            {{
            "answer": "respuesta para el usuario",
            "intent": "string",
            "extracted_data": {{
            "language": "es|pt|en",
            "name": null,
            "last": null,
            "phone": null,
            "documentNumber": null,
            "email": null,
            "origin_currency": null,
            "destination_currency": null,
            "send_amount": null,
            "receive_amount": null,
            "quote_mode": null,
            "coupon_code": null,
            "wants_whatsapp": null,
            "wants_advisor": null,
            "urgency": null
            }}
            }}
            """
            },
                *history,
            {"role": "user", "content":message_user}
        ]
        
        #respuesta final y extract
        
        llm_response_content, parsed_data = self.orchestador.run(system_prompt, user_id)
        print("Datos del orquestador:",llm_response_content,"\n",parsed_data)
        answer=llm_response_content
        print("RESPUESTA",answer)
        extract = parsed_data.get("extracted_data", {})
        intent=parsed_data.get("intent") or ""
        # obtener perfil actual de scoring
        lead_profile=self.memory_port.get_memory_lead(user_id)
        new_data={}
        #recorrer y detectar solo campos que antes estaban vacíos.
        for key, value in extract.items():
            if not value:
                continue
            old_value=lead_profile.get(key)
            if old_value is None:
                new_data[key]=value
        scoring=self.lead_scoring_case.calculate({
            "intent": intent,
            "destination_currency": new_data.get("destination_currency"),
            "origin_currency": new_data.get("origin_currency"),
            "send_amount": new_data.get("send_amount"),
            "urgency": new_data.get("urgency"),
        })

        #Calcular nuevo score
        prev_score=self.memory_port.get_memory_score(user_id)["score"]
        new_score=prev_score+scoring["score"]
        self.memory_port.save_memory_score(user_id,{"score":new_score})
        current_score={"score":new_score}
        current_level = self.lead_scoring_case.get_level(current_score["score"])

        #guardar datos del score
        self.memory_port.save_memory_lead(user_id,{
            "language": extract.get("language"),
            "destination_currency":extract.get("destination_currency"),
            "send_amount":extract.get("send_amount"),
            "origin_currency": extract.get("origin_currency"),
            "urgency":extract.get("urgency"),
        })
        #print("CURRENT SCORE: ",current_score)
        #print("CURRENT LEVEL: ",current_level)

        #Resumen de la conversacion
        if any(v for k,v in extract.items() if k != "phone"):
            summary=self.orchestador.summary({
            "language": extract.get("language","es"),
            "origin_currency":extract.get("origin_currency","No mencionado"),
            "destination_currency":extract.get("destination_currency","No mencionado"),
            "send_amount":extract.get("send_amount","No mencionado"),
            "receive_amount":extract.get("receive_amount","No mencionado"),
            "quote_mode": extract.get("quote_mode","No mencionado"),
            "coupon_code": extract.get("coupon_code","No mencionado"),
            "urgency":extract.get("urgency","No mencionado"),
            "name":extract.get("name","-"),
            "phone":user_id,
            "last":extract.get("last"),
            "documentNumber":extract.get("documentNumber","-")
            })
            #print("SUMMARY",summary)
            self.cache_adapter.save(f"summary{user_id}",summary)
        print(f"INTENCION: {intent}")
        self.cache_adapter.save(f"scoreMetrics{user_id}",extract)
        self.cache_adapter.save(f"score{user_id}", current_score)

        '''if extract.get("name"):
            lead_data_to_update = {
                "name"          : extract.get("name"),
                "last"          : extract.get("last"),
                "email"        : extract.get("email"),
                "documentNumber": extract.get("documentNumber"),
                "documentType"  : extract.get("documentType"),
                "phone"         : user_id,
                "projectOfInterest": extract.get("interestedProjectName"),
                "interestLevel": current_level, # Inyectar el nivel de interés calculado
            }
            clean_lead_data = {k: v for k, v in lead_data_to_update.items() if v is not None}
            self.crm_use_case.save_lead_with_cache(clean_lead_data)
            print(f"Lead actualizado/guardado con interestLevel: {current_level} para el teléfono: {extract.get('phone')}")'''
        lead_data_to_save = extract.copy()
        lead_data_to_save['phone'] = user_id
        lead_data_to_save['interestLevel'] = current_level
        lead_data_to_save['serviceOfInterest'] = 'remesas'

        if any(extract.values()):
            self.crm_use_case.save_lead_with_cache(lead_data_to_save)
            #print(f"Datos del lead actualizados en caché para el usuario {user_id}")

        messages_for_memory = [
        {"role": "user", "content": message_user},
        {"role": "assistant", "content": answer}
        ]

        self.memory_port.save_memory(user_id, messages_for_memory)



        print("USE CASE RESPUESTA",answer)
        return answer
