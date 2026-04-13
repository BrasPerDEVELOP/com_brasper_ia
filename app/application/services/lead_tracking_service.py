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
    Campos listos para `generate_summary`: sin None en valores (evita 'None' en textos)
    y sin exponer el teléfono en el mensaje al asesor (no se incluye en esta estructura).
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
        # Solo referencia interna / CRM; no se imprime en el texto del enlace al asesor
        "phone": user_id,
    }


class LeadTrackingService:
    def __init__(self, state_service, lead_scoring_case, crm_use_case, llm_port):
        self.state_service = state_service
        self.lead_scoring_case = lead_scoring_case
        self.crm_use_case = crm_use_case
        self.llm_port = llm_port

    def _score_payload(self, intent: str, extracted_data: dict, result: FeatureResult) -> dict:
        return {
            "intent": intent,
            "destination_currency": extracted_data.get("destination_currency"),
            "origin_currency": extracted_data.get("origin_currency"),
            "send_amount": extracted_data.get("send_amount"),
            "urgency": extracted_data.get("urgency"),
            "events": [event.name for event in result.tracking_events],
            "result_type": result.type,
        }

    def _select_new_profile_data(self, lead_state: dict, extracted_data: dict) -> dict:
        new_data = {}
        for key, value in extracted_data.items():
            if value in (None, "", False):
                continue
            if lead_state.get(key) is None:
                new_data[key] = value
        return new_data

    def _summary_payload(self, user_id: str, extracted_data: dict) -> dict:
        return build_advisor_summary_data(user_id, extracted_data)

    def _should_update_summary(self, extracted_data: dict, result: FeatureResult) -> bool:
        if result.type in {"quote_result", "coupon_result", "handoff_result", "contact_prompt"}:
            return True
        return any(v for k, v in extracted_data.items() if k != "phone")

    def apply(self, context, decision: dict, result: FeatureResult):
        extracted_data = decision.get("extracted_data", {})
        lead_updates = {**extracted_data, **result.lead_updates}
        new_profile_data = self._select_new_profile_data(context.lead_state, lead_updates)

        scoring = self.lead_scoring_case.calculate(
            self._score_payload(decision.get("intent", ""), lead_updates, result)
        )
        current_score_value = (context.score or {}).get("score", 0) + scoring["score"]
        current_level = self.lead_scoring_case.get_level(current_score_value)

        self.state_service.save_score(context.user_id, current_score_value)
        self.state_service.save_lead_profile(
            context.user_id,
            {
                "language": lead_updates.get("language"),
                "destination_currency": lead_updates.get("destination_currency"),
                "send_amount": lead_updates.get("send_amount"),
                "origin_currency": lead_updates.get("origin_currency"),
                "urgency": lead_updates.get("urgency"),
            },
        )

        if self._should_update_summary(lead_updates, result):
            summary = self.llm_port.generate_summary(self._summary_payload(context.user_id, lead_updates))
            self.state_service.save_summary(context.user_id, summary)

        self.state_service.save_metrics(context.user_id, lead_updates, {"score": current_score_value})

        payload = lead_updates.copy()
        payload["phone"] = context.user_id
        payload["interestLevel"] = current_level
        payload["serviceOfInterest"] = "remesas"

        if any(payload.values()):
            self.crm_use_case.save_lead_with_cache(payload)

        result.tracking_events.append(
            DomainEvent(
                name="lead_updated",
                payload={
                    "user_id": context.user_id,
                    "interest_level": current_level,
                    "new_fields": sorted(new_profile_data.keys()),
                },
            )
        )

        return {
            "score": current_score_value,
            "level": current_level,
            "lead_updates": payload,
        }
