"""
Unit tests for ACP message envelope.
Run: pytest tests/
"""
import pytest
import json
import sys
sys.path.insert(0, "..")

from acp_sdk.message import ACPMessage, MessageType


def test_task_delegate_factory():
    msg = ACPMessage.task_delegate(
        from_aid="did:acp:local:orchestrator",
        to_aid="did:acp:local:worker",
        task="Summarize this text",
        input={"text": "Hello world"},
        correlation_id="session_123",
    )
    assert msg.type == MessageType.TASK_DELEGATE
    assert msg.from_aid == "did:acp:local:orchestrator"
    assert msg.to == "did:acp:local:worker"
    assert msg.body["task"] == "Summarize this text"
    assert msg.correlation_id == "session_123"
    assert msg.id.startswith("msg_")
    assert msg.acp == "0.1"


def test_message_roundtrip_json():
    msg = ACPMessage.task_result(
        from_aid="did:acp:local:worker",
        to_aid="did:acp:local:orchestrator",
        status="success",
        output={"result": 42},
        reply_to="msg_abc",
    )
    d = msg.to_dict()
    assert d["from"] == "did:acp:local:worker"  # 'from' not 'from_aid' in wire format
    assert d["type"] == "task.result"

    restored = ACPMessage.from_dict(d)
    assert restored.type == MessageType.TASK_RESULT
    assert restored.from_aid == "did:acp:local:worker"
    assert restored.body["output"]["result"] == 42


def test_error_message():
    msg = ACPMessage.error(
        from_aid="did:acp:local:bus",
        to_aid="did:acp:local:orchestrator",
        code="acp.unknown_agent",
        message="Agent not found",
    )
    assert msg.type == MessageType.ERROR
    assert msg.body["code"] == "acp.unknown_agent"


def test_agent_hello():
    msg = ACPMessage.agent_hello(
        from_aid="did:acp:local:worker",
        registry_aid="did:acp:local:registry",
        name="Worker Agent",
        capabilities=["summarize", "translate"],
    )
    assert msg.type == MessageType.AGENT_HELLO
    assert "summarize" in msg.body["capabilities"]


@pytest.mark.asyncio
async def test_inprocess_bus():
    from acp_sdk.bus import InProcessBus
    from acp_sdk.agent import ACPAgent

    class EchoAgent(ACPAgent):
        async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
            return ACPMessage.task_result(
                from_aid=self.aid,
                to_aid=msg.from_aid,
                status="success",
                output={"echo": msg.body["input"]},
                reply_to=msg.id,
            )

    bus = InProcessBus()
    sender = ACPAgent("did:acp:local:sender", bus)
    echo = EchoAgent("did:acp:local:echo", bus)

    msg = ACPMessage.task_delegate(
        from_aid="did:acp:local:sender",
        to_aid="did:acp:local:echo",
        task="Echo this",
        input={"data": "hello"},
    )
    result = await bus.route(msg)

    assert result is not None
    assert result.type == MessageType.TASK_RESULT
    assert result.body["output"]["echo"]["data"] == "hello"
