"""
ACP Quickstart — Summarizer Agent (stdio transport)

This agent:
1. Reads ACP messages from stdin (newline-delimited JSON)
2. Handles task.delegate messages: reverses + uppercases the input text (simulates summarization)
3. Writes task.result to stdout

Run standalone:
    echo '{"acp":"0.1","id":"msg_001","type":"agent.hello","from":"did:acp:local:client","to":"did:acp:local:summarizer","ts":"2026-03-18T10:00:00Z","body":{"name":"Client","version":"1.0.0","acp_version":"0.1","capabilities":[]}}' | python agent_summarizer.py

Or run via the orchestrator:
    python orchestrator.py
"""
import sys
import json
import datetime
import uuid

AID = "did:acp:local:summarizer"


def now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def make_id() -> str:
    return "msg_" + uuid.uuid4().hex[:12]


def handle(msg: dict) -> dict | None:
    msg_type = msg.get("type")
    msg_id   = msg.get("id", "")
    from_aid = msg.get("from", "")

    if msg_type == "agent.hello":
        # Capability negotiation: echo back our hello
        return {
            "acp": "0.1", "id": make_id(), "type": "agent.hello",
            "from": AID, "to": from_aid, "ts": now(),
            "reply_to": msg_id,
            "body": {
                "name": "Summarizer Agent", "version": "1.0.0", "acp_version": "0.1",
                "capabilities": ["summarize"],
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                },
            },
        }

    elif msg_type == "task.delegate":
        text = msg.get("body", {}).get("input", {}).get("text", "")
        if not text:
            return {
                "acp": "0.1", "id": make_id(), "type": "error",
                "from": AID, "to": from_aid, "ts": now(), "reply_to": msg_id,
                "body": {"code": "acp.invalid_message", "message": "'input.text' is required"},
            }

        # Simulate summarization: take first 50 chars + "..."
        summary = text[:50].strip() + ("..." if len(text) > 50 else "")
        word_count = len(text.split())

        return {
            "acp": "0.1", "id": make_id(), "type": "task.result",
            "from": AID, "to": from_aid, "ts": now(),
            "reply_to": msg_id,
            "correlation_id": msg.get("correlation_id"),
            "body": {
                "status": "success",
                "output": {"summary": summary, "word_count": word_count},
                "usage": {"tokens_in": word_count, "tokens_out": len(summary.split()), "duration_ms": 12},
            },
        }

    elif msg_type == "agent.bye":
        return None  # No reply needed; the loop will exit on EOF

    else:
        return {
            "acp": "0.1", "id": make_id(), "type": "error",
            "from": AID, "to": from_aid, "ts": now(), "reply_to": msg_id,
            "body": {"code": "acp.unsupported_type", "message": f"Unknown type: {msg_type}"},
        }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg  = json.loads(line)
            resp = handle(msg)
            if resp:
                print(json.dumps(resp, ensure_ascii=False), flush=True)
        except json.JSONDecodeError as e:
            err = {"acp": "0.1", "id": make_id(), "type": "error",
                   "from": AID, "to": "unknown", "ts": now(),
                   "body": {"code": "acp.invalid_message", "message": str(e)}}
            print(json.dumps(err), flush=True)


if __name__ == "__main__":
    main()
