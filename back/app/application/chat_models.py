from dataclasses import dataclass, field
from typing import Any


@dataclass
class DomainEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationContext:
    user_id: str
    message: str
    history: list[dict[str, str]]
    lead_state: dict[str, Any] = field(default_factory=dict)
    score: dict[str, Any] = field(default_factory=lambda: {"score": 0})
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureResult:
    type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    lead_updates: dict[str, Any] = field(default_factory=dict)
    tracking_events: list[DomainEvent] = field(default_factory=list)
