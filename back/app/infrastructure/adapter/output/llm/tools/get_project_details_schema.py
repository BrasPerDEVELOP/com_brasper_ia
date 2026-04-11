get_project_details_schema={
    "name":"get_project_details",
    "description":"Obtiene los detalles de un solo projecto, incluyendo información de lotes o unidades",
    "parameters":{
        "type":"object",
        "properties":{
            "name":{"type":"string", "description":"Nombre del proyecto"}
        },
        "required":["name"]
    }
}