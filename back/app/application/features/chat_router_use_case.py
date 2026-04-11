from app.application.features.contact_feature import ContactFeature
from app.application.features.coupons_feature import CouponsFeature
from app.application.features.greeting_feature import GreetingFeature
from app.application.features.handoff_feature import HandoffFeature
from app.application.features.remittance_quote_feature import RemittanceQuoteFeature
from app.application.features.remittance_requirements_feature import RemittanceRequirementsFeature


class ChatRouterUseCase:
    def __init__(self, tool_router, policy_engine):
        self.policy_engine = policy_engine
        self.greeting_feature = GreetingFeature(policy_engine)
        self.requirements_feature = RemittanceRequirementsFeature(tool_router, policy_engine)
        self.coupons_feature = CouponsFeature(tool_router, policy_engine)
        self.contact_feature = ContactFeature(policy_engine)
        self.handoff_feature = HandoffFeature(tool_router)
        self.quote_feature = RemittanceQuoteFeature(tool_router, policy_engine)

    def route(self, context, decision: dict):
        metadata = decision.get("metadata", {})
        if decision.get("intent") == "greeting":
            return self.greeting_feature.execute(context, decision)
        if metadata.get("reason") == "coupon_lookup":
            return self.coupons_feature.execute(context, decision)
        if decision.get("intent") == "human_handoff":
            return self.handoff_feature.execute(context, decision)
        if decision.get("intent") == "collect_contact":
            return self.contact_feature.execute(context, decision)
        if decision.get("intent") == "remittance_quote":
            return self.quote_feature.execute(context, decision)
        return self.requirements_feature.execute(context, decision)
