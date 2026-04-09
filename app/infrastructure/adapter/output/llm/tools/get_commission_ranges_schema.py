get_commission_ranges_schema = {
    "name": "get_commission_ranges",
    "description": "Obtiene los rangos de comisión para un par de monedas de Brasper.",
    "parameters": {
        "type": "object",
        "properties": {
            "origin_currency": {"type": "string"},
            "destination_currency": {"type": "string"},
        },
        "required": ["origin_currency", "destination_currency"],
    },
}
