from app.application.chat_models import DomainEvent, FeatureResult


class GreetingFeature:
    def __init__(self, policy_engine):
        self.policy_engine = policy_engine

    def execute(self, context, decision: dict) -> FeatureResult:
        language = decision.get("language") or "es"
        return FeatureResult(
            type="greeting_result",
            message=self.policy_engine.copy(language, "greeting"),
            lead_updates=decision.get("extracted_data", {}),
            tracking_events=[DomainEvent(name="message_received", payload={"user_id": context.user_id})],
        )
