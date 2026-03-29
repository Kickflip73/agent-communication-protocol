# ADR-003: Event Replay via `?since=<seq>` — Reconnect Without Data Loss

**Status**: Accepted  
**Date**: 2026-03-29  
**Author**: J.A.R.V.I.S. / Stark

---

## Context

SSE and WebSocket connections drop. When a subscriber reconnects, it misses events
that occurred during the disconnection window. Without replay, the client must either
poll `/history` or accept data loss — both are unsatisfactory.

The standard SSE spec includes `Last-Event-ID` header as a reconnect hint, but:
1. It requires server-assigned IDs in the `id:` field of each SSE event
2. Browser SSE handles it automatically, but non-browser clients (AI agents) rarely do
3. WebSocket has no equivalent standard

ACP already assigns monotonically-increasing `seq` numbers to all events. This makes
seq-based replay trivially implementable.

## Decision

**Both `/stream` (SSE) and `/ws/stream` (WebSocket) support `?since=<seq>` query parameter.**

On connect:
1. Server parses `?since=<seq>` from the request URL
2. Server immediately delivers all buffered events with `seq > since`
3. Connection then enters normal live-push mode

**Ring buffer**: Last `_EVENT_LOG_MAX` (500) events are kept in `_event_log` (a list),
protected by `_event_log_lock` (threading.Lock). Events are appended by
`_broadcast_sse_event()`, which is called for every dispatched message.

**No `since`**: Normal behavior unchanged — no replay, live-only.

**Example reconnect flow:**
```
# Client received events up to seq=42, then disconnected
GET /stream?since=42
→ Server immediately sends events 43, 44, 45 (replay)
→ Then streams new events as they arrive
```

## Rationale

- **Seq is already there**: Every ACP event has a monotonic `seq` assigned server-side
- **Client simplicity**: Client just needs to remember `last_seq`; no HTTP headers
- **Works for both SSE and WS**: Uniform API across both stream endpoints
- **Bounded memory**: 500-event ring buffer caps memory at ~500KB worst case
- **No A2A equivalent**: Differentiates ACP in a meaningful operational way

## Consequences

### Positive
- Reconnect-safe clients can achieve zero data loss (within 500-event window)
- No polling required during reconnect
- Uniform behavior across SSE and WebSocket
- `capabilities.event_replay: true` advertised in AgentCard for discovery

### Negative
- Events older than 500 are lost on reconnect (acceptable trade-off vs unbounded memory)
- Ring buffer is in-memory — relay restart clears history (by design; use `/history` for persistence)
- Since=0 replay of 500 events adds initial latency for new subscribers (mitigated by fast local TCP)

## Implementation Notes

- Bug discovered during implementation: `client.send_ws_text()` was called but the
  method is named `client.send()`. The typo was silently swallowed by `except Exception: break`,
  causing WS replay to never execute. Fixed in commit `4aa78ce`.
- Always test both SSE and WS paths when modifying broadcast/replay logic.

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|----------------|
| HTTP `Last-Event-ID` header (SSE standard) | Non-browser agents don't send it automatically; WS has no equivalent |
| `/history` polling after reconnect | Polling latency; requires client-side diff logic |
| Client-side dedup only | Data loss still occurs; just hidden |
| Persistent event store (DB) | Overengineering for personal/team use case; contradicts zero-ops |

## Related

- ACP v2.13 implementation: `relay/acp_relay.py`
- Tests: `tests/test_event_replay.py` (RP1–RP6, 6/6 PASS)
- A2A has no event replay mechanism as of 2026-03-29
