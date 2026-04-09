get_active_coupons_schema = {
    "name": "get_active_coupons",
    "description": "Obtiene los cupones activos hoy en Brasper, opcionalmente por corredor.",
    "parameters": {
        "type": "object",
        "properties": {
            "origin_currency": {"type": "string"},
            "destination_currency": {"type": "string"},
        },
    },
}
