from typing import Annotated, Any, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    lead_state: dict
    user_id: str
    summary: dict
    score: dict
    intent: Optional[str]
    extracted_data: dict
    pre_analysis: dict
    decision: dict
    answer: str
    result: Any
