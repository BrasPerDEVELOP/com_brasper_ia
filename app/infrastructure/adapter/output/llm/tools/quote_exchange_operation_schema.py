quote_exchange_operation_schema = {
    "name": "quote_exchange_operation",
    "description": "Cotiza una operación de remesa Brasper usando tasa, comisión y cupón activo.",
    "parameters": {
        "type": "object",
        "properties": {
            "origin_currency": {"type": "string"},
            "destination_currency": {"type": "string"},
            "amount": {"type": "number"},
            "mode": {"type": "string", "description": "send o receive"},
            "language": {"type": "string", "description": "es, pt o en"},
        },
        "required": ["origin_currency", "destination_currency", "amount", "mode", "language"],
    },
}
