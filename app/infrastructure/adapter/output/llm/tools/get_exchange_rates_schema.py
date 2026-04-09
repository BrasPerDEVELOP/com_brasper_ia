get_exchange_rates_schema = {
    "name": "get_exchange_rates",
    "description": "Obtiene tipos de cambio de Brasper para un corredor válido.",
    "parameters": {
        "type": "object",
        "properties": {
            "origin_currency": {"type": "string"},
            "destination_currency": {"type": "string"},
        },
    },
}
