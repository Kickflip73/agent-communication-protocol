"""
ACP Message envelope definition.
"""
from __future__ import annotations
import uuid
import datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


class MessageType(str, Enum):
    # Task lifecycle
    TASK_DELEGATE = "task.delegate"
    TASK_ACCEPT   = "task.accept"
    TASK_REJECT   = "task.reject"
    TASK_RESULT   = "task.result"
    TASK_PROGRESS = "task.progress"
    TASK_CANCEL   = "task.cancel"

    # Events
    EVENT_BROADCAST   = "event.broadcast"
    EVENT_SUBSCRIBE   = "event.subscribe"
    EVENT_UNSUBSCRIBE = "event.unsubscribe"

    # Coordination
    COORD_PROPOSE = "coord.propose"
    COORD_VOTE    = "coord.vote"

    # Lifecycle
    AGENT_HELLO     = "agent.hello"
    AGENT_BYE       = "agent.bye"
    AGENT_HEARTBEAT = "agent.heartbeat"

    # Human-in-the-loop
    HITL_ESCALATE = "hitl.escalate"
    HITL_RESPONSE = "hitl.response"

    # Error
    ERROR = "error"


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()).replace("-", ""))
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16].replace("-", ""))
    parent_span_id: Optional[str] = None


@dataclass
class ACPMessage:
    """
    ACP message envelope (v0.1).

    Usage:
        msg = ACPMessage.task_delegate(
            from_aid="did:acp:local:orchestrator",
            to_aid="did:acp:local:worker",
            task="Summarize this document",
            input={"text": "..."},
        )
    """
    type: MessageType
    from_aid: str         # 'from' is a Python keyword, use from_aid
    to: str
    body: dict[str, Any]

    # Auto-generated fields
    acp: str = "0.1"
    id: str = field(default_factory=lambda: "msg_" + str(uuid.uuid4()).replace("-", "")[:16])
    ts: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    # Optional fields
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    ttl: Optional[int] = None
    trace: Optional[TraceContext] = field(default_factory=TraceContext)

    def to_dict(self) -> dict:
        d = {
            "acp": self.acp,
            "id": self.id,
            "type": self.type.value if isinstance(self.type, MessageType) else self.type,
            "from": self.from_aid,
            "to": self.to,
            "ts": self.ts,
            "body": self.body,
        }
        if self.correlation_id:
            d["correlation_id"] = self.correlation_id
        if self.reply_to:
            d["reply_to"] = self.reply_to
        if self.ttl is not None:
            d["ttl"] = self.ttl
        if self.trace:
            d["trace"] = asdict(self.trace)
        return d

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "ACPMessage":
        return cls(
            type=MessageType(data["type"]),
            from_aid=data["from"],
            to=data["to"],
            body=data.get("body", {}),
            acp=data.get("acp", "0.1"),
            id=data.get("id", ""),
            ts=data.get("ts", ""),
            correlation_id=data.get("correlation_id"),
            reply_to=data.get("reply_to"),
            ttl=data.get("ttl"),
            trace=TraceContext(**data["trace"]) if data.get("trace") else None,
        )

    # --- Factory methods ---

    @classmethod
    def task_delegate(
        cls,
        from_aid: str,
        to_aid: str,
        task: str,
        input: dict = None,
        constraints: dict = None,
        context: list = None,
        correlation_id: str = None,
    ) -> "ACPMessage":
        return cls(
            type=MessageType.TASK_DELEGATE,
            from_aid=from_aid,
            to=to_aid,
            correlation_id=correlation_id,
            body={
                "task": task,
                "input": input or {},
                "constraints": constraints or {},
                "context": context or [],
            },
        )

    @classmethod
    def task_result(
        cls,
        from_aid: str,
        to_aid: str,
        status: str,
        output: dict = None,
        reply_to: str = None,
        correlation_id: str = None,
        usage: dict = None,
        error: dict = None,
    ) -> "ACPMessage":
        body = {"status": status, "output": output or {}}
        if usage:
            body["usage"] = usage
        if error:
            body["error"] = error
        return cls(
            type=MessageType.TASK_RESULT,
            from_aid=from_aid,
            to=to_aid,
            reply_to=reply_to,
            correlation_id=correlation_id,
            body=body,
        )

    @classmethod
    def error(
        cls,
        from_aid: str,
        to_aid: str,
        code: str,
        message: str,
        reply_to: str = None,
    ) -> "ACPMessage":
        return cls(
            type=MessageType.ERROR,
            from_aid=from_aid,
            to=to_aid,
            reply_to=reply_to,
            body={"code": code, "message": message},
        )

    @classmethod
    def agent_hello(
        cls,
        from_aid: str,
        registry_aid: str,
        name: str,
        capabilities: list[str],
        version: str = "1.0.0",
        metadata: dict = None,
    ) -> "ACPMessage":
        return cls(
            type=MessageType.AGENT_HELLO,
            from_aid=from_aid,
            to=registry_aid,
            body={
                "name": name,
                "version": version,
                "capabilities": capabilities,
                "metadata": metadata or {},
            },
        )
