from app.application.chat_models import DomainEvent, FeatureResult


class RemittanceRequirementsFeature:
    def __init__(self, tool_router, policy_engine):
        self.tool_router = tool_router
        self.policy_engine = policy_engine

    def execute(self, context, decision: dict) -> FeatureResult:
        language = decision.get("language") or "es"
        metadata = decision.get("metadata", {})
        message = self.policy_engine.copy(language, "requirements")
        if metadata.get("reason") == "supported_pairs":
            supported = self.tool_router.router({"name": "get_supported_currencies", "args": {}})
            currencies = ", ".join(item["code"] for item in supported.get("currencies", []))
            pairs = ", ".join(
                f"{pair['origin_currency']}->{pair['destination_currency']}"
                for pair in supported.get("pairs", [])
            )
            message = f"{self.policy_engine.copy(language, 'supported_intro')} {currencies}. {pairs}"
        return FeatureResult(
            type="requirements_result",
            message=message,
            metadata=metadata,
            lead_updates=decision.get("extracted_data", {}),
            tracking_events=[DomainEvent(name="intent_detected", payload={"intent": decision.get('intent')})],
        )
