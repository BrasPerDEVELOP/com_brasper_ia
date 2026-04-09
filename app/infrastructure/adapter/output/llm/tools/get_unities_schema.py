get_unities_data_tool_schema = {
    "name": "get_unities_data",
    "description": "Obtiene las unidades (departamentos, oficinas) de un proyecto de edificación específico. Debes proporcionar el ID del proyecto.",
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "El ID único del proyecto al que pertenecen las unidades."},
            "phase_number": {"type": "integer", "description": "Filtrar unidades por el número de la etapa (phase)."},
            "level_name": {"type": "string", "description": "Filtrar unidades por el nombre o número del nivel/piso."},
            "unity_status": {"type": "string", "description": "Filtrar unidades por su estado. 'enabled', 'blocked', 'sold', 'separed', 'cancel'."}
        },
        "required": ["project_id"]
    }
}