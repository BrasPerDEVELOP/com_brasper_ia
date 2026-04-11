import unittest
import sys
import types

from app.application.chat_models import ConversationContext
httpx_stub = types.ModuleType("httpx")
httpx_stub.Client = object
sys.modules.setdefault("httpx", httpx_stub)

from app.application.brasper_use_case import BrasperUseCase
from app.application.features.chat_router_use_case import ChatRouterUseCase
from app.application.orchestador.conversation_orchestador import ConversationOrchestrator
from app.application.policies.remittance_policies import RemittancePolicyEngine


class FakeToolRouter:
    def router(self, tool_call):
        name = tool_call["name"]
        args = tool_call.get("args") or {}
        if name == "get_supported_currencies":
            return {
                "currencies": [{"code": "BRL"}, {"code": "PEN"}, {"code": "USD"}],
                "pairs": [
                    {"origin_currency": "BRL", "destination_currency": "PEN"},
                    {"origin_currency": "PEN", "destination_currency": "BRL"},
                    {"origin_currency": "BRL", "destination_currency": "USD"},
                    {"origin_currency": "USD", "destination_currency": "BRL"},
                ],
            }
        if name == "get_active_coupons":
            if args.get("origin_currency") == "BRL" and args.get("destination_currency") == "PEN":
                return {
                    "coupons": [
                        {
                            "code": "PROMO10",
                            "discount_percentage": 10.0,
                            "origin_currency": "BRL",
                            "destination_currency": "PEN",
                            "start_date": "2026-01-01",
                            "end_date": "2026-12-31",
                        }
                    ]
                }
            return {"coupons": []}
        if name == "quote_exchange_operation":
            return {
                "origin_currency": args["origin_currency"],
                "destination_currency": args["destination_currency"],
                "amount_send": 100.0,
                "amount_receive": 72.5,
                "commission": 3.0,
                "rate": 0.75,
                "total_to_send": 97.0,
                "coupon_code": "PROMO10",
                "coupon_savings_amount": 1.0,
                "summary_text": "Cotización Brasper: Monto a enviar 100.00 USD, Total a recibir 72.50 BRL.",
            }
        if name == "build_whatsapp_quote_message":
            return {"wa_link": "https://wa.me/test"}
        if name == "handoff_to_advisor":
            return {"message": "Te derivo con un asesor.", "wa_link": "https://wa.me/advisor"}
        raise AssertionError(f"Unexpected tool call: {name}")


class FakeLLM:
    def __init__(self, content=None):
        self.content = content

    def generate_response(self, messages):
        class Response:
            def __init__(self, content):
                self.content = content

        if self.content is None:
            return None
        return Response(self.content)

    def extract_intent(self, content):
        return {
            "answer": "",
            "intent": "collect_contact",
            "extracted_data": {"name": "Juan", "last": "Perez", "email": "juan@test.com", "language": "es"},
        }


class ChatArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.tool_router = FakeToolRouter()
        self.policy_engine = RemittancePolicyEngine(self.tool_router)
        self.chat_router = ChatRouterUseCase(self.tool_router, self.policy_engine)

    def _context(self, message):
        return ConversationContext(user_id="51999999999", message=message, history=[], lead_state={})

    def test_direct_quote_without_llm(self):
        orchestrator = ConversationOrchestrator(FakeLLM(None), self.policy_engine, self.chat_router)
        result, decision = orchestrator.run(self._context("Quiero enviar 100 dolares a reales"))
        self.assertEqual(decision["intent"], "remittance_quote")
        self.assertEqual(decision["extracted_data"]["origin_currency"], "USD")
        self.assertEqual(decision["extracted_data"]["destination_currency"], "BRL")
        self.assertIn("Cotización Brasper", result.message)
        self.assertIn("https://wa.me/test", result.message)

    def test_coupon_query_routes_to_coupon_feature(self):
        orchestrator = ConversationOrchestrator(FakeLLM(None), self.policy_engine, self.chat_router)
        result, decision = orchestrator.run(self._context("Hay cupones activos de reales a soles?"))
        self.assertEqual(decision["metadata"]["reason"], "coupon_lookup")
        self.assertEqual(result.type, "coupon_result")
        self.assertIn("PROMO10", result.message)
        self.assertIn("Estos son los cupones activos", result.message)
        self.assertIn("Válido hasta: 31/12/2026", result.message)

    def test_invalid_pair_is_rejected_deterministically(self):
        orchestrator = ConversationOrchestrator(FakeLLM(None), self.policy_engine, self.chat_router)
        result, decision = orchestrator.run(self._context("Quiero enviar 100 dolares a soles"))
        self.assertEqual(decision["intent"], "remittance_quote")
        self.assertIn("Brasper", result.message)
        self.assertIn("BRL a USD", result.message)

    def test_handoff_skips_quote(self):
        orchestrator = ConversationOrchestrator(FakeLLM(None), self.policy_engine, self.chat_router)
        context = self._context("Quiero hablar con un asesor por whatsapp")
        context.summary = {"summary": "Resumen previo"}
        result, decision = orchestrator.run(context)
        self.assertEqual(decision["intent"], "human_handoff")
        self.assertEqual(result.type, "handoff_result")
        self.assertIn("https://wa.me/advisor", result.message)

    def test_llm_is_used_for_contact_collection_when_needed(self):
        orchestrator = ConversationOrchestrator(FakeLLM("{}"), self.policy_engine, self.chat_router)
        result, decision = orchestrator.run(self._context("Mi correo es juan@test.com"))
        self.assertEqual(decision["intent"], "collect_contact")
        self.assertEqual(result.type, "contact_prompt")
        self.assertIn("registré tu contacto", result.message)

    def test_email_after_quote_context_stays_in_quote_flow(self):
        orchestrator = ConversationOrchestrator(FakeLLM("{}"), self.policy_engine, self.chat_router)
        context = ConversationContext(
            user_id="51999999999",
            message="alberthxen@gmail.com",
            history=[],
            lead_state={
                "origin_currency": "PEN",
                "destination_currency": "BRL",
                "send_amount": 100.0,
                "quote_mode": "send",
                "language": "es",
            },
        )
        result, decision = orchestrator.run(context)
        self.assertEqual(decision["intent"], "remittance_quote")
        self.assertIn("https://wa.me/test", result.message)

    def test_new_amount_overrides_previous_context_amount(self):
        normalized = self.policy_engine.post_process(
            "quiero recibir 1000 reales a soles",
            {
                "origin_currency": "PEN",
                "destination_currency": "BRL",
                "send_amount": 100.0,
                "quote_mode": "send",
                "language": "es",
            },
            None,
            self.policy_engine.pre_process(
                "quiero recibir 1000 reales a soles",
                {
                    "origin_currency": "PEN",
                    "destination_currency": "BRL",
                    "send_amount": 100.0,
                    "quote_mode": "send",
                    "language": "es",
                },
            ),
        )
        self.assertEqual(normalized["extracted_data"]["receive_amount"], 1000.0)
        self.assertEqual(normalized["extracted_data"]["quote_mode"], "receive")

    def test_receive_phrase_flips_currency_direction(self):
        normalized = self.policy_engine.post_process(
            "quiero recibir 1000 reales a soles",
            {},
            None,
            self.policy_engine.pre_process("quiero recibir 1000 reales a soles", {}),
        )
        self.assertEqual(normalized["intent"], "remittance_quote")
        self.assertEqual(normalized["extracted_data"]["origin_currency"], "PEN")
        self.assertEqual(normalized["extracted_data"]["destination_currency"], "BRL")
        self.assertEqual(normalized["extracted_data"]["receive_amount"], 1000.0)

    def test_bare_amount_updates_existing_send_quote(self):
        normalized = self.policy_engine.post_process(
            "250",
            {
                "origin_currency": "PEN",
                "destination_currency": "BRL",
                "send_amount": 100.0,
                "quote_mode": "send",
                "language": "es",
            },
            None,
            self.policy_engine.pre_process(
                "250",
                {
                    "origin_currency": "PEN",
                    "destination_currency": "BRL",
                    "send_amount": 100.0,
                    "quote_mode": "send",
                    "language": "es",
                },
            ),
        )
        self.assertEqual(normalized["extracted_data"]["send_amount"], 250.0)
        self.assertIsNone(normalized["extracted_data"]["receive_amount"])
        self.assertEqual(normalized["extracted_data"]["quote_mode"], "send")

    def test_inverse_quote_matches_direct_formula(self):
        class TestBrasperUseCase(BrasperUseCase):
            def get_exchange_rates(self, args=None):
                return {"rates": [{"id": 1, "origin_currency": "PEN", "destination_currency": "BRL", "rate": 0.75}]}

            def get_commission_ranges(self, args=None):
                return {
                    "commission_ranges": [
                        {
                            "id": 10,
                            "origin_currency": "PEN",
                            "destination_currency": "BRL",
                            "percentage": 3.0,
                            "reverse": 0,
                            "min_amount": 0,
                            "max_amount": 100000,
                            "updated_at": None,
                        }
                    ]
                }

            def get_active_coupons(self, args=None):
                return {
                    "coupons": [
                        {
                            "id": 99,
                            "code": "PROMO10",
                            "discount_percentage": 10.0,
                            "origin_currency": "PEN",
                            "destination_currency": "BRL",
                            "start_date": "2026-01-01",
                            "end_date": "2026-12-31",
                        }
                    ]
                }

        use_case = TestBrasperUseCase()
        quote = use_case.quote_exchange_operation(
            {
                "origin_currency": "PEN",
                "destination_currency": "BRL",
                "receive_amount": 100,
                "mode": "receive",
                "language": "es",
            }
        )
        expected_receive = round(quote["total_to_send"] * quote["rate"], 2)
        self.assertEqual(quote["amount_receive"], expected_receive)
        self.assertAlmostEqual(quote["commission"], 3.7, places=2)
        self.assertAlmostEqual(quote["coupon_savings_amount"], 0.41, places=2)
        self.assertAlmostEqual(quote["amount_send"], 137.03, places=2)


if __name__ == "__main__":
    unittest.main()
