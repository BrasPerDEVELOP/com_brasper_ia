get_lots_data_tool_schema = {
    "name": "get_lots_data",
    "description": "Obtiene los lotes o terrenos de un proyecto específico. Debes proporcionar el ID del proyecto.",
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "El ID único del proyecto al que pertenecen los lotes."},
            "phase_number": {"type": "integer", "description": "Filtrar lotes por el número de la etapa (phase)."},
            "block_name": {"type": "string", "description": "Filtrar lotes por el nombre o letra de la manzana (block)."},
            "lot_status": {"type": "string", "description": "Filtrar lotes por su estado. 'enabled', 'blocked', 'sold', 'separed', 'cancel' "}
        },
        "required": ["project_id"]
    }
}