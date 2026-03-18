"""
ACP Example: Orchestrator + Parallel Workers

Topology:
    Orchestrator
      ├── SearchAgent    (finds information)
      └── SummarizerAgent (summarizes results)

Run: python demo.py
"""
import asyncio
import sys
sys.path.insert(0, "../../sdk/python")

from acp_sdk import ACPMessage, ACPAgent, InProcessBus


# ─── Define Worker Agents ────────────────────────────────────────────────────

class SearchAgent(ACPAgent):
    async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
        query = msg.body["input"].get("query", "")
        print(f"  [SearchAgent] Searching for: '{query}'")
        await asyncio.sleep(0.1)  # simulate work

        return ACPMessage.task_result(
            from_aid=self.aid,
            to_aid=msg.from_aid,
            status="success",
            output={
                "results": [
                    {"title": "AI Memory Survey 2025", "url": "https://arxiv.org/..."},
                    {"title": "Episodic Memory in LLMs", "url": "https://arxiv.org/..."},
                ]
            },
            reply_to=msg.id,
            correlation_id=msg.correlation_id,
            usage={"duration_ms": 100},
        )


class SummarizerAgent(ACPAgent):
    async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
        results = msg.body["input"].get("results", [])
        print(f"  [SummarizerAgent] Summarizing {len(results)} results")
        await asyncio.sleep(0.05)  # simulate work

        titles = [r["title"] for r in results]
        return ACPMessage.task_result(
            from_aid=self.aid,
            to_aid=msg.from_aid,
            status="success",
            output={"summary": f"Found {len(titles)} papers: " + "; ".join(titles)},
            reply_to=msg.id,
            correlation_id=msg.correlation_id,
        )


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class OrchestratorAgent(ACPAgent):
    async def run_workflow(self, user_query: str) -> str:
        correlation_id = "workflow_" + user_query[:10].replace(" ", "_")
        print(f"\n[Orchestrator] Starting workflow: '{user_query}'")

        # Step 1: delegate search in parallel with prep
        search_msg = ACPMessage.task_delegate(
            from_aid=self.aid,
            to_aid="did:acp:local:search-agent",
            task="Search for relevant papers",
            input={"query": user_query},
            correlation_id=correlation_id,
        )
        search_result = await self.send(search_msg)
        print(f"[Orchestrator] Search done: status={search_result.body['status']}")

        if search_result.body["status"] != "success":
            return "Search failed."

        # Step 2: summarize the results
        summarize_msg = ACPMessage.task_delegate(
            from_aid=self.aid,
            to_aid="did:acp:local:summarizer-agent",
            task="Summarize search results",
            input=search_result.body["output"],
            correlation_id=correlation_id,
        )
        summary_result = await self.send(summarize_msg)
        print(f"[Orchestrator] Summary done: status={summary_result.body['status']}")

        return summary_result.body["output"].get("summary", "No summary.")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=== ACP Demo: Orchestrator + Workers ===\n")

    # Setup
    bus = InProcessBus()
    orchestrator = OrchestratorAgent("did:acp:local:orchestrator", bus)
    SearchAgent("did:acp:local:search-agent", bus)
    SummarizerAgent("did:acp:local:summarizer-agent", bus)

    print(f"Registered agents: {bus.agents()}\n")

    # Run workflow
    result = await orchestrator.run_workflow("AI agent memory mechanisms 2025")

    print(f"\n✅ Final result: {result}")
    print(f"\nMessage log ({len(bus.message_log)} messages):")
    for m in bus.message_log:
        print(f"  {m.type.value:25s}  {m.from_aid.split(':')[-1]:20s} → {m.to.split(':')[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
