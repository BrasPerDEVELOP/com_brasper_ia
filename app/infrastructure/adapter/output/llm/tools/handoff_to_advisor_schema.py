handoff_to_advisor_schema = {
    "name": "handoff_to_advisor",
    "description": "Genera una derivación a un asesor Brasper con enlace de WhatsApp.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "language": {"type": "string"},
        },
        "required": ["language"],
    },
}
