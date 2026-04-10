from app.application.chat_models import DomainEvent, FeatureResult
from datetime import datetime


class CouponsFeature:
    def __init__(self, tool_router, policy_engine):
        self.tool_router = tool_router
        self.policy_engine = policy_engine

    def _format_date(self, value: str, language: str) -> str:
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return value
        if language == "en":
            return parsed.strftime("%m/%d/%Y")
        return parsed.strftime("%d/%m/%Y")

    def _build_message(self, items: list[dict], language: str) -> str:
        intros = {
            "es": "Estos son los cupones activos que encontré:",
            "pt": "Estes são os cupons ativos que encontrei:",
            "en": "These are the active coupons I found:",
        }
        valid_until = {
            "es": "Válido hasta",
            "pt": "Válido até",
            "en": "Valid until",
        }
        lines = [intros.get(language, intros["es"])]
        for item in items:
            end_date = self._format_date(item.get("end_date"), language)
            corridor = f"{item['origin_currency']} a {item['destination_currency']}" if language != "en" else f"{item['origin_currency']} to {item['destination_currency']}"
            lines.append(
                f"- Usa {item['code']} y obtén {item['discount_percentage']:.0f}% de descuento para operaciones de {corridor}. {valid_until.get(language, valid_until['es'])}: {end_date}."
            )
        return "\n".join(lines)

    def execute(self, context, decision: dict) -> FeatureResult:
        language = decision.get("language") or "es"
        data = decision.get("extracted_data", {})
        coupons = self.tool_router.router(
            {
                "name": "get_active_coupons",
                "args": {
                    "origin_currency": data.get("origin_currency"),
                    "destination_currency": data.get("destination_currency"),
                },
            }
        )
        items = coupons.get("coupons", [])
        if not items:
            message = self.policy_engine.copy(language, "coupons_none")
        else:
            message = self._build_message(items, language)
        return FeatureResult(
            type="coupon_result",
            message=message,
            metadata={"coupon_count": len(items)},
            lead_updates=data,
            tracking_events=[DomainEvent(name="coupon_viewed", payload={"count": len(items)})],
        )
