from app.application.chat_models import DomainEvent, FeatureResult


class HandoffFeature:
    def __init__(self, tool_router):
        self.tool_router = tool_router

    def execute(self, context, decision: dict) -> FeatureResult:
        language = decision.get("language") or "es"
        summary = (context.summary or {}).get("summary", "")
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
        return FeatureResult(
            type="handoff_result",
            message=message,
            metadata={"wa_link": wa_link},
            lead_updates=decision.get("extracted_data", {}),
            tracking_events=[DomainEvent(name="handoff_requested", payload={"language": language})],
        )
