
calendar_tool_schema={
    "name":"create_calendar_event",
    "description":"Crear evento en google calendar",
    "parameters":{
        "type":"object",
        "properties":{
            "summary":{"type":"string", "description":"Título o resumen del evento."},
            "start":{"type":"string", "description":"Fecha y hora de inicio en formato YYYY-MM-DDTHH:MM:SS. Debes calcular esto a partir de la conversación."},
            "end":{"type":"string", "description":"Fecha y hora de fin en formato YYYY-MM-DDTHH:MM:SS. Debes calcular esto. Si no se especifica duración, asume 1 hora después del inicio."},
            "description":{"type":"string", "description":"Descripción detallada del evento."},
            "location":{"type":"string", "description":"Ubicación del evento."},
            "attendees": {
                "type": "array",
                "description": "Lista de invitados al evento",
                "items": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "Correo del invitado"
                        }
                    }
                }
            }
        },
        "required":["summary","start","end","email"]
    }
}