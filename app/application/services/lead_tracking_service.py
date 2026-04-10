from app.application.chat_models import DomainEvent, FeatureResult


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
        return {
            "language": extracted_data.get("language", "es"),
            "origin_currency": extracted_data.get("origin_currency", "No mencionado"),
            "destination_currency": extracted_data.get("destination_currency", "No mencionado"),
            "send_amount": extracted_data.get("send_amount", "No mencionado"),
            "receive_amount": extracted_data.get("receive_amount", "No mencionado"),
            "quote_mode": extracted_data.get("quote_mode", "No mencionado"),
            "coupon_code": extracted_data.get("coupon_code", "No mencionado"),
            "urgency": extracted_data.get("urgency", "No mencionado"),
            "name": extracted_data.get("name", "-"),
            "phone": user_id,
            "last": extracted_data.get("last"),
            "documentNumber": extracted_data.get("documentNumber", "-"),
        }

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
