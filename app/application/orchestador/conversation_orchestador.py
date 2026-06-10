from app.application.chat_models import FeatureResult

try:
    from langgraph.graph import StateGraph, START, END
    from app.application.orchestador.graph_state import AgentState
except ImportError:
    StateGraph = START = END = None
    AgentState = dict


class ConversationOrchestrator:
    def __init__(self, llm_adapter, policy_engine, chat_router):
        self.llm_adapter = llm_adapter
        self.policy_engine = policy_engine
        self.chat_router = chat_router
        self.graph = self._build_graph()

    def _build_system_prompt(self, history: list[dict], message: str):
        return [
            {
                "role": "system",
                "content": """
                Eres un sistema de extracción de información para un chatbot de remesas y tipo de cambio de Brasper.

                Tu única tarea es:
                1. Clasificar la intención del usuario
                2. Extraer los datos presentes en el mensaje

                El backend decidirá la respuesta final. No inventes tasas, montos ni datos faltantes.
                No uses historial ni supongas datos de mensajes anteriores.
                No hagas preguntas de seguimiento para completar datos.
                Detecta siempre el idioma del usuario: "es", "pt" o "en".

                Intents:
                ["greeting","remittance_quote","remittance_requirements","human_handoff","collect_contact"]

                Devuelve SOLO JSON puro:
                {
                  "answer": "respuesta breve para el usuario",
                  "intent": "string",
                  "extracted_data": {
                    "language": "es|pt|en",
                    "name": null,
                    "last": null,
                    "phone": null,
                    "documentNumber": null,
                    "email": null,
                    "origin_currency": null,
                    "destination_currency": null,
                    "send_amount": null,
                    "receive_amount": null,
                    "quote_mode": null,
                    "coupon_code": null,
                    "wants_whatsapp": null,
                    "wants_advisor": null,
                    "urgency": null
                  }
                }
                """,
            },
            {"role": "user", "content": message},
        ]

    def _extract_with_llm(self, context):
        response = self.llm_adapter.generate_response(
            self._build_system_prompt(context.history, context.message)
        )
        if not response:
            return {"answer": "", "intent": "", "extracted_data": {}}
        parsed = self.llm_adapter.extract_intent(response.content)
        if "answer" not in parsed:
            parsed["answer"] = response.content or ""
        return parsed

    def _run_legacy(self, context):
        pre_analysis = self.policy_engine.pre_process(context.message, context.lead_state)
        llm_extract = None if pre_analysis.get("should_skip_llm") else self._extract_with_llm(context)
        decision = self.policy_engine.post_process(
            context.message,
            context.lead_state,
            llm_extract,
            pre_analysis,
        )
        result = self.chat_router.route(context, decision)
        return result, decision

    def _node_pre_process(self, state: AgentState):
        message = state["messages"][-1].content if state["messages"] else ""
        pre_analysis = self.policy_engine.pre_process(message, state["lead_state"])
        return {"pre_analysis": pre_analysis}

    def _node_llm_extract(self, state: AgentState):
        message = state["messages"][-1].content if state["messages"] else ""
        response = self.llm_adapter.generate_response(
            self._build_system_prompt([], message)
        )
        if not response:
            return {"answer": "", "intent": "", "extracted_data": {}}
        parsed = self.llm_adapter.extract_intent(response.content)
        if "answer" not in parsed:
            parsed["answer"] = response.content or ""
        return {
            "answer": parsed.get("answer", ""),
            "intent": parsed.get("intent", ""),
            "extracted_data": parsed.get("extracted_data", {}),
        }

    def _node_post_process(self, state: AgentState):
        message = state["messages"][-1].content if state["messages"] else ""
        llm_extract = None
        if not state["pre_analysis"].get("should_skip_llm"):
            llm_extract = {
                "answer": state.get("answer", ""),
                "intent": state.get("intent", ""),
                "extracted_data": state.get("extracted_data", {}),
            }
        decision = self.policy_engine.post_process(
            message,
            {},
            llm_extract,
            state["pre_analysis"],
        )
        return {"decision": decision}

    def _context_from_state(self, state: AgentState):
        class GraphContext:
            def __init__(self, user_id, msg, lead, summary=None, score=None):
                self.user_id = user_id
                self.message = msg
                self.lead_state = lead
                self.summary = summary or {}
                self.score = score or {"score": 0}

        message = state["messages"][-1].content if state["messages"] else ""
        return GraphContext(
            state.get("user_id", ""),
            message,
            {},
            state.get("summary") or {},
            state.get("score") or {"score": 0},
        )

    def _node_route_action(self, state: AgentState):
        result = self.chat_router.route(self._context_from_state(state), state["decision"])
        return {"result": result, "answer": result.message}

    def _should_skip_llm(self, state: AgentState) -> str:
        if state["pre_analysis"].get("should_skip_llm"):
            return "post_process"
        return "llm_extract"

    def _build_graph(self):
        if StateGraph is None:
            return None
        workflow = StateGraph(AgentState)
        workflow.add_node("pre_process", self._node_pre_process)
        workflow.add_node("llm_extract", self._node_llm_extract)
        workflow.add_node("post_process", self._node_post_process)
        workflow.add_node("route_action", self._node_route_action)
        workflow.add_edge(START, "pre_process")
        workflow.add_conditional_edges(
            "pre_process",
            self._should_skip_llm,
            {
                "llm_extract": "llm_extract",
                "post_process": "post_process",
            },
        )
        workflow.add_edge("llm_extract", "post_process")
        workflow.add_edge("post_process", "route_action")
        workflow.add_edge("route_action", END)
        return workflow.compile()

    def run(self, context):
        if self.graph is None:
            return self._run_legacy(context)

        from langchain_core.messages import AIMessage, HumanMessage

        initial_messages = []
        initial_messages.append(HumanMessage(content=context.message))

        initial_state = {
            "messages": initial_messages,
            "lead_state": {},
            "user_id": context.user_id,
            "summary": context.summary,
            "score": context.score,
            "intent": None,
            "extracted_data": {},
            "pre_analysis": {},
            "decision": {},
            "answer": "",
            "result": None,
        }
        final_state = self.graph.invoke(initial_state)
        result = final_state.get("result")
        if not isinstance(result, FeatureResult):
            result = FeatureResult(type="fallback", message=final_state.get("answer", ""))
        decision = final_state.get("decision", {})
        return result, decision
