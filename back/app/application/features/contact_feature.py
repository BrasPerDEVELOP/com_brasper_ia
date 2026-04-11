from app.application.chat_models import DomainEvent, FeatureResult


class ContactFeature:
    def __init__(self, policy_engine):
        self.policy_engine = policy_engine

    def execute(self, context, decision: dict) -> FeatureResult:
        data = decision.get("extracted_data", {})
        language = decision.get("language") or "es"
        if not data.get("name") or not data.get("last"):
            message = self.policy_engine.copy(language, "need_name")
        elif not data.get("email"):
            message = self.policy_engine.copy(language, "need_email")
        else:
            message = self.policy_engine.copy(language, "contact_ok")
        return FeatureResult(
            type="contact_prompt",
            message=message,
            lead_updates=data,
            tracking_events=[DomainEvent(name="lead_updated", payload={"fields": ["name", "last", "email"]})],
        )
