from app.application.chat_models import DomainEvent, FeatureResult


class ContactFeature:
    def __init__(self, policy_engine):
        self.policy_engine = policy_engine

    def execute(self, context, decision: dict) -> FeatureResult:
        data = decision.get("extracted_data", {})
        language = decision.get("language") or "es"
        meta = decision.get("metadata") or {}
        handoff_prereq = meta.get("reason") == "handoff_prereq"
        if not data.get("name") or not data.get("last"):
            message = self.policy_engine.copy(language, "need_name")
        elif not data.get("email") and not handoff_prereq:
            message = self.policy_engine.copy(language, "need_email")
        else:
            message = (
                self.policy_engine.copy(language, "handoff_prereq_ok")
                if handoff_prereq
                else self.policy_engine.copy(language, "contact_ok")
            )
        lead_updates = dict(data)
        if handoff_prereq:
            if not data.get("name") or not data.get("last"):
                lead_updates["pending_handoff_prereq"] = True
            else:
                lead_updates["pending_handoff_prereq"] = False
        return FeatureResult(
            type="contact_prompt",
            message=message,
            lead_updates=lead_updates,
            tracking_events=[DomainEvent(name="lead_updated", payload={"fields": ["name", "last", "email"]})],
        )
