from app.application.chat_models import DomainEvent, FeatureResult


class RemittanceQuoteFeature:
    def __init__(self, tool_router, policy_engine):
        self.tool_router = tool_router
        self.policy_engine = policy_engine

    def _is_true(self, value) -> bool:
        return str(value or "").lower() in {"true", "1", "yes", "si", "sí", "sim"}

    def _build_whatsapp_link(self, quote: dict, language: str) -> str:
        whatsapp = self.tool_router.router(
            {
                "name": "build_whatsapp_quote_message",
                "args": {
                    "origin_currency": quote.get("origin_currency"),
                    "destination_currency": quote.get("destination_currency"),
                    "amount_send": quote.get("amount_send"),
                    "amount_receive": quote.get("amount_receive"),
                    "commission": quote.get("commission_gross", quote.get("commission")),
                    "total_to_send": quote.get("total_to_send"),
                    "rate": quote.get("rate"),
                    "coupon_code": quote.get("coupon_code"),
                    "coupon_savings_amount": quote.get("coupon_savings_amount"),
                    "language": language,
                },
            }
        )
        return whatsapp.get("wa_link", "")

    def execute(self, context, decision: dict) -> FeatureResult:
        data = decision.get("extracted_data", {})
        language = decision.get("language") or "es"
        validation_error = (decision.get("metadata") or {}).get("validation_error")

        if validation_error:
            return FeatureResult(
                type="quote_result",
                message=validation_error,
                lead_updates=data,
                tracking_events=[DomainEvent(name="quote_requested", payload={"valid": False})],
            )
        if not data.get("origin_currency"):
            return FeatureResult(
                type="quote_result",
                message=self.policy_engine.copy(language, "ask_origin"),
                lead_updates=data,
                tracking_events=[DomainEvent(name="quote_requested", payload={"missing": "origin_currency"})],
            )
        if not data.get("destination_currency"):
            return FeatureResult(
                type="quote_result",
                message=self.policy_engine.copy(language, "ask_destination"),
                lead_updates=data,
                tracking_events=[DomainEvent(name="quote_requested", payload={"missing": "destination_currency"})],
            )

        amount = data.get("send_amount")
        mode = "send"
        if amount is None and data.get("receive_amount") is not None:
            amount = data.get("receive_amount")
            mode = "receive"
        if data.get("quote_mode") in ("send", "receive"):
            mode = data.get("quote_mode")
        if amount is None:
            return FeatureResult(
                type="quote_result",
                message=self.policy_engine.copy(language, "ask_amount"),
                lead_updates=data,
                tracking_events=[DomainEvent(name="quote_requested", payload={"missing": "amount"})],
            )

        quote = self.tool_router.router(
            {
                "name": "quote_exchange_operation",
                "args": {
                    "origin_currency": data.get("origin_currency"),
                    "destination_currency": data.get("destination_currency"),
                    "amount": amount,
                    "mode": mode,
                    "language": language,
                },
            }
        )
        if quote.get("error"):
            return FeatureResult(
                type="quote_result",
                message=quote["error"],
                lead_updates=data,
                tracking_events=[DomainEvent(name="quote_requested", payload={"valid": False})],
            )

        message = quote.get("summary_text", self.policy_engine.copy(language, "fallback"))
        whatsapp_link = self._build_whatsapp_link(quote, language)
        if self._is_true(data.get("wants_advisor")):
            handoff = self.tool_router.router(
                {
                    "name": "handoff_to_advisor",
                    "args": {"language": language, "summary": message},
                }
            )
            wa_link = handoff.get("wa_link")
            message = handoff.get("message", message)
            if wa_link:
                message = f"{message}\n\n{wa_link}"
        else:
            message = f"{message}\n\n{whatsapp_link}"

        lead_updates = data.copy()
        lead_updates.update(
            {
                "origin_currency": quote.get("origin_currency"),
                "destination_currency": quote.get("destination_currency"),
                "send_amount": quote.get("amount_send"),
                "receive_amount": quote.get("amount_receive"),
                "coupon_code": quote.get("coupon_code"),
                "quote_mode": mode,
            }
        )

        return FeatureResult(
            type="quote_result",
            message=message,
            metadata={"quote": quote, "whatsapp_link": whatsapp_link},
            lead_updates=lead_updates,
            tracking_events=[
                DomainEvent(name="quote_requested", payload={"mode": mode}),
                DomainEvent(name="quote_completed", payload={"origin": quote.get("origin_currency"), "destination": quote.get("destination_currency")}),
            ],
        )
