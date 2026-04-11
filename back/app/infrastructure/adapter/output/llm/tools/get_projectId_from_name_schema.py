get_projectId_from_name_tool_schema = {
    "name": "get_projectId_from_name",
    "description": "Obtiene el projectId desde su nombre",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "El nombre del proyecto."},
        },
        "required": ["name"]
    }
}