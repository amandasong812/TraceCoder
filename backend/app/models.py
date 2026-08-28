from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NodeStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    revised = "revised"


class PlanNode(BaseModel):
    id: str
    title: str
    detail: str = ""
    status: NodeStatus = NodeStatus.pending


class ToolCall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    node_id: str


class ToolObservation(BaseModel):
    node_id: str
    tool: str
    ok: bool
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


ActionKind = Literal["plan", "tool", "final"]


class AgentAction(BaseModel):
    kind: ActionKind
    thought: str = ""
    plan: list[PlanNode] = Field(default_factory=list)
    tool_call: ToolCall | None = None
    final_report: str | None = None


class TraceEvent(BaseModel):
    type: str
    payload: dict[str, Any]
    created_at: str = Field(default_factory=utc_now)


ChatRole = Literal["user", "assistant", "tool", "system", "error"]


class ChatMessage(BaseModel):
    role: ChatRole
    title: str
    content: str
    event_type: str | None = None
    created_at: str = Field(default_factory=utc_now)


class TraceRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    task: str
    status: Literal["created", "running", "success", "failed"] = "created"
    plan: list[PlanNode] = Field(default_factory=list)
    observations: list[ToolObservation] = Field(default_factory=list)
    final_report: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    events: list[TraceEvent] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    def add_event(self, event_type: str, payload: dict[str, Any]) -> TraceEvent:
        event = TraceEvent(type=event_type, payload=payload)
        self.events.append(event)
        self.updated_at = utc_now()
        return event

    def add_message(self, role: ChatRole, title: str, content: str, event_type: str | None = None) -> ChatMessage:
        message = ChatMessage(role=role, title=title, content=content, event_type=event_type)
        self.messages.append(message)
        self.updated_at = utc_now()
        return message
