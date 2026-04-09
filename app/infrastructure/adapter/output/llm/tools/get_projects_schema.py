get_projects_data_tool_schema={
    "name":"get_projects_data",
    "description":"Obtiene una lista de todos los proyectos inmobiliarios disponibles de Zefiron. Úsalo cuando un usuario pregunte sobre las propiedades o proyectos que tienes.",
    "parameters": {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Filtrar proyectos por nombre exacto o parcial."},
        "project_type": {"type": "string", "description": "Filtrar por tipo de proyecto(únicas opciones) : 'urbanPlanning', 'building'."},
        "department": {"type": "string", "description": "Filtrar por departamento o ubicación, ej: 'Lima'."},
        "min_price": {"type": "string", "description": "Precio mínimo de venta."},
        "max_price": {"type": "string", "description": "Precio máximo de venta que se pide."}
    }
    }
}