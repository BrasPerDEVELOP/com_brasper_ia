build_whatsapp_quote_message_schema = {
    "name": "build_whatsapp_quote_message",
    "description": "Construye el mensaje final y enlace de WhatsApp para una cotización Brasper.",
    "parameters": {
        "type": "object",
        "properties": {
            "origin_currency": {"type": "string"},
            "destination_currency": {"type": "string"},
            "amount_send": {"type": "number"},
            "amount_receive": {"type": "number"},
            "commission": {"type": "number"},
            "total_to_send": {"type": "number"},
            "rate": {"type": "number"},
            "coupon_code": {"type": "string"},
            "coupon_savings_amount": {"type": "number"},
            "language": {"type": "string"},
        },
        "required": [
            "origin_currency",
            "destination_currency",
            "amount_send",
            "amount_receive",
            "commission",
            "total_to_send",
            "rate",
            "language",
        ],
    },
}
