from app.application.chat_models import DomainEvent, FeatureResult


def _display_field(value, default="No indicado"):
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    if value is False:
        return default
    return str(value).strip()


def build_advisor_summary_data(user_id: str, extracted_data: dict) -> dict:
    """
    Estructura transitoria para construir el mensaje de derivación. No se persiste.
    """
    name = _display_field(extracted_data.get("name"), "")
    last = _display_field(extracted_data.get("last"), "")
    full_name = " ".join(part for part in (name, last) if part).strip() or "Sin nombre registrado"
    return {
        "language": _display_field(extracted_data.get("language"), "es"),
        "origin_currency": _display_field(extracted_data.get("origin_currency")),
        "destination_currency": _display_field(extracted_data.get("destination_currency")),
        "send_amount": _display_field(extracted_data.get("send_amount")),
        "receive_amount": _display_field(extracted_data.get("receive_amount")),
        "quote_mode": _display_field(extracted_data.get("quote_mode")),
        "coupon_code": _display_field(extracted_data.get("coupon_code")),
        "urgency": _display_field(extracted_data.get("urgency")),
        "name": full_name,
        "documentNumber": _display_field(extracted_data.get("documentNumber")),
        "phone": user_id,
    }


class LeadTrackingService:
    def __init__(self, state_service, lead_scoring_case, crm_use_case, llm_port):
        self.state_service = state_service
        self.lead_scoring_case = lead_scoring_case
        self.crm_use_case = crm_use_case
        self.llm_port = llm_port

    def apply(self, context, decision: dict, result: FeatureResult):
        """
        Privacidad: no guarda historial, score, perfil, resumen, métricas ni lead en CRM.
        Mantiene solo un evento transitorio dentro del resultado actual para observabilidad local.
        """
        result.tracking_events.append(
            DomainEvent(
                name="lead_processed_transient",
                payload={"result_type": result.type},
            )
        )

        return {
            "score": 0,
            "level": "none",
            "lead_updates": {},
        }
