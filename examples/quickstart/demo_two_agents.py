"""
ACP Quickstart: Two agents communicating in 10 lines of user code.

This demo shows the MINIMUM code needed to make two agents talk to each other.
No framework dependency, no complex setup.

Run:
    # Terminal 1 — start gateway
    cd gateway && python server.py

    # Terminal 2 — run this demo
    python demo_two_agents.py
"""
import asyncio
import sys
sys.path.insert(0, "../../sdk/python")

from acp_sdk import ACPMessage, ACPAgent, InProcessBus

# ════════════════════════════════════════════════════════════════
#  THE ONLY CODE YOUR USERS NEED TO WRITE (10 lines)
# ════════════════════════════════════════════════════════════════

class TranslatorAgent(ACPAgent):
    """An agent that translates text. 5 lines to implement."""

    async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
        text = msg.body["input"].get("text", "")
        lang = msg.body["input"].get("target_lang", "English")
        # (In real code, call your LLM here)
        translated = f"[Translated to {lang}]: {text}"
        return ACPMessage.task_result(
            from_aid=self.aid, to_aid=msg.from_aid,
            status="success", output={"translated": translated},
            reply_to=msg.id, correlation_id=msg.correlation_id,
        )


class SummarizerAgent(ACPAgent):
    """An agent that summarizes text. 5 lines to implement."""

    async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
        text = msg.body["input"].get("text", "")
        summary = text[:50] + "..." if len(text) > 50 else text
        return ACPMessage.task_result(
            from_aid=self.aid, to_aid=msg.from_aid,
            status="success", output={"summary": summary},
            reply_to=msg.id,
        )

# ════════════════════════════════════════════════════════════════
#  WIRING: connect them with 3 lines
# ════════════════════════════════════════════════════════════════

async def main():
    bus = InProcessBus()
    translator = TranslatorAgent("did:acp:local:translator", bus)
    summarizer  = SummarizerAgent("did:acp:local:summarizer",  bus)

    print("=== ACP Quickstart: Two Agents ===\n")

    # Agent A asks Agent B to translate
    print("1. Translator asks Summarizer to summarize:")
    result = await translator.send(
        ACPMessage.task_delegate(
            from_aid="did:acp:local:translator",
            to_aid="did:acp:local:summarizer",
            task="Summarize this article",
            input={"text": "Artificial intelligence is transforming every industry..."},
        )
    )
    print(f"   Result: {result.body['output']}\n")

    # Agent B asks Agent A to translate
    print("2. Summarizer asks Translator to translate:")
    result2 = await summarizer.send(
        ACPMessage.task_delegate(
            from_aid="did:acp:local:summarizer",
            to_aid="did:acp:local:translator",
            task="Translate to Chinese",
            input={"text": "Hello world", "target_lang": "Chinese"},
        )
    )
    print(f"   Result: {result2.body['output']}\n")

    print("✅ Done. Two agents communicated via ACP.")
    print(f"   Total messages: {len(bus.message_log)}")


if __name__ == "__main__":
    asyncio.run(main())
