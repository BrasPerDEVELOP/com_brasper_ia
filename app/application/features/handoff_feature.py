from app.application.chat_models import DomainEvent, FeatureResult
from app.application.services.lead_tracking_service import build_advisor_summary_data


class HandoffFeature:
    def __init__(self, tool_router, llm_port):
        self.tool_router = tool_router
        self._llm_port = llm_port

    def execute(self, context, decision: dict) -> FeatureResult:
        language = decision.get("language") or "es"
        merged = {**(context.lead_state or {}), **(decision.get("extracted_data") or {})}
        payload = build_advisor_summary_data(context.user_id, merged)
        summary = (self._llm_port.generate_summary(payload) or {}).get("summary", "")
        handoff = self.tool_router.router(
            {
                "name": "handoff_to_advisor",
                "args": {"language": language, "summary": summary},
            }
        )
        message = handoff.get("message", "")
        wa_link = handoff.get("wa_link")
        if wa_link:
            message = f"{message}\n\n{wa_link}"
        handoff_lead = {**(decision.get("extracted_data") or {}), "pending_handoff_prereq": False}
        return FeatureResult(
            type="handoff_result",
            message=message,
            metadata={"wa_link": wa_link},
            lead_updates=handoff_lead,
            tracking_events=[DomainEvent(name="handoff_requested", payload={"language": language})],
        )
