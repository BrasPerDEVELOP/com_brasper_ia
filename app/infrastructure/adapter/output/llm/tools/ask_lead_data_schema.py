
ask_lead_data_tool_schema={
    "name":"save_lead",
    "description":"Guarda la información de un cliente potencial (lead) cuando este la proporciona. Se necesita nombre, apellido y teléfono.",
    "parameters":{
        "type":"object",
        "properties":{
            #Datos iniciales
            "name":{"type":"string", "description": "Nombre del lead"},
            "last":{"type":"string", "description": "Apellido del lead"},
            "phone":{"type":"string", "description": "Teléfono del lead"},
            "email":{"type":"string", "description": "Email del lead"},
            #Datos avanzados
            "documentType":{"type":"string", "description": "Tipo de documento del lead"},
            "documentNumber":{"type":"string", "description": "Número de documento del lead"},
            #Datos una vez se interese por un proyecto
            "projectOfInterest":{"type":"string", "description": "Proyecto de interés del lead"},
            #Datos que el llm debe llenar solo
            "leadStage":{"type":"string", "description":"Etapa del lead"},
            "interestLevel":{"type":"string", "description":"Nivel de interés"},
            "sourceChannel":{"type":"string", "description":"Canal de origen"},
            "method":{"type":"string", "description":"Medio de captación"},
            "agent":{"type":"string", "description":"Agente asignado"},
            #extra(to not post)
            "summary":{"type":"string", "description":"Resumen del lead"},
            "visit_start_time":{"type":"string", "description":"Hora de inicio de la visita"},
            "visit_end_time":{"type":"string", "description":"Hora de fin de la visita"},
            "project_type":{"type":"string", "description":"Tipo de proyecto"},
            "zone":{"type":"string", "description":"Zona de interés"},
            "budget":{"type":"string", "description":"Presupuesto"},
            "visit_date":{"type":"string", "description":"Fecha de interés"},
            "urgency":{"type":"string", "description":"Urgencia"}

        },
        "required":["name", "last", "phone"]
    }
}