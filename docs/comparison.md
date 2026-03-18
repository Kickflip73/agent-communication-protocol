# ACP vs. Existing Protocols

## Competitive Landscape (2026)

| Protocol | Creator | Scope | Open? | A2A? | Async? | Transport Agnostic? |
|----------|---------|-------|-------|------|--------|---------------------|
| **ACP** | Community | Agent↔Agent | ✅ Apache 2.0 | ✅ | ✅ | ✅ |
| MCP | Anthropic | Agent↔Tool | ✅ MIT | ❌ | ❌ | ⚠️ Mainly stdio/HTTP |
| A2A | Google | Agent↔Agent | ⚠️ Google-led | ✅ | ✅ | ⚠️ HTTP/gRPC |
| FIPA-ACL | FIPA (1997) | Agent↔Agent | ✅ | ✅ | ✅ | ⚠️ Dated |
| AutoGen wire | Microsoft | Agent↔Agent | ✅ | ✅ | ✅ | ❌ Framework-coupled |
| LangGraph | LangChain | Agent↔Agent | ✅ | ✅ | ✅ | ❌ Python-only |

## Why Not Use MCP?

MCP (Model Context Protocol) solves **Agent ↔ Tool** integration — connecting an LLM to databases, APIs, files. It's excellent for that purpose.

ACP solves **Agent ↔ Agent** communication — how an orchestrator delegates tasks to workers, how agents coordinate, discover each other, and report results. These are different layers.

**ACP + MCP together** = full-stack MAS:
```
Orchestrator
  │  (ACP)
  ├── Worker Agent A ──(MCP)──► Database Tool
  ├── Worker Agent B ──(MCP)──► Web Search Tool
  └── Worker Agent C ──(MCP)──► Code Execution Tool
```

## Why Not Use Google A2A?

A2A is a good protocol but is **vendor-driven** (Google). ACP is:
- Community-governed (no single company controls it)
- More minimal (A2A includes agent card, task manager, streaming as mandatory)
- More transport-agnostic (A2A strongly prefers HTTP/SSE)

ACP aims to be the **neutral ground** that any MAS framework can adopt.

## Why Not Use FIPA-ACL?

FIPA-ACL (1997) was ahead of its time but:
- XML-based, verbose
- No JSON support
- No async model
- Outdated infrastructure assumptions
- Very complex (hundreds of pages of spec)

ACP learns from FIPA's concepts (speech acts, performatives) but is JSON-native, minimal, and modern.
