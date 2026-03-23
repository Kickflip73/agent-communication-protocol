"""
Suite: SSE Stream (ACP spec §6)
Tests the /stream endpoint for event-stream compliance.

Spec requirements:
  MUST: /stream endpoint returns text/event-stream content-type
  MUST: Each SSE event has 'event:' type line
  MUST: Each SSE event has valid JSON in 'data:' line
  SHOULD: First event within 5 seconds of connect
  SHOULD: Events include acp.message, acp.status, acp.artifact types
  MAY: Supports ?since=<server_seq> for replay

Note: This suite uses stdlib only (urllib + raw socket read).
SSE streams are long-lived; tests use short read windows (2s) to avoid blocking.
"""
import json
import socket
import time
import threading
import urllib.request
import urllib.error
import uuid
from compat_base import Compat, PASS, FAIL, WARN, SKIP


def _read_sse_events(base_url: str, path: str, timeout: float = 3.0) -> list[dict]:
    """
    Open an SSE stream and collect events for `timeout` seconds.
    Returns list of parsed event dicts: {"event": str, "data": dict, "raw": str}
    Uses raw socket to avoid urllib blocking on streaming responses.
    """
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or 80
    request_path = path

    events = []
    raw_lines = []

    try:
        conn = socket.create_connection((host, port), timeout=timeout)
        request = (
            f"GET {request_path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Accept: text/event-stream\r\n"
            f"Cache-Control: no-cache\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        conn.sendall(request.encode())
        conn.settimeout(timeout)

        buffer = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk
            except socket.timeout:
                break

        conn.close()

        # Parse HTTP response
        text = buffer.decode("utf-8", errors="replace")
        if "\r\n\r\n" in text:
            _, body = text.split("\r\n\r\n", 1)
        else:
            body = text

        # Parse SSE events (blank-line separated)
        current_event = {}
        for line in body.splitlines():
            raw_lines.append(line)
            if line.startswith("event:"):
                current_event["event"] = line[6:].strip()
            elif line.startswith("data:"):
                raw_data = line[5:].strip()
                try:
                    current_event["data"] = json.loads(raw_data)
                except json.JSONDecodeError:
                    current_event["data"] = raw_data
                current_event["raw"] = raw_data
            elif line == "" and current_event:
                events.append(current_event)
                current_event = {}

        if current_event:
            events.append(current_event)

    except Exception:
        pass

    return events


def _check_content_type(base_url: str, path: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Check that the /stream endpoint returns text/event-stream Content-Type."""
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or 80

    try:
        conn = socket.create_connection((host, port), timeout=timeout)
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Accept: text/event-stream\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        conn.sendall(request.encode())
        conn.settimeout(2.0)

        # Read only the headers
        headers_buf = b""
        while b"\r\n\r\n" not in headers_buf:
            try:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                headers_buf += chunk
            except socket.timeout:
                break
        conn.close()

        headers_text = headers_buf.decode("utf-8", errors="replace")
        content_type_ok = "text/event-stream" in headers_text.lower()
        # Extract status line
        first_line = headers_text.split("\r\n")[0] if headers_text else ""
        return content_type_ok, first_line

    except Exception as e:
        return False, str(e)


class SSEStreamSuite(Compat):
    SUITE_NAME = "SSE Stream"

    def run(self) -> None:
        # ── Capability check ──────────────────────────────────────────────────
        if not self.has_capability("streaming"):
            self.skip("SSE stream endpoint exists", "capabilities.streaming not declared")
            self.skip("Content-Type is text/event-stream", "capabilities.streaming not declared")
            self.skip("SSE events have 'event:' type line", "capabilities.streaming not declared")
            self.skip("SSE data field is valid JSON", "capabilities.streaming not declared")
            self.skip("Event type is known ACP type", "capabilities.streaming not declared")
            self.skip("/stream?since= parameter accepted", "capabilities.streaming not declared")
            return

        stream_path = "/stream"

        # ── Content-Type check ────────────────────────────────────────────────
        ct_ok, status_line = _check_content_type(self.base_url, stream_path)
        self.check(
            "GET /stream returns text/event-stream Content-Type",
            ct_ok,
            "MUST",
            f"status line: {status_line!r}"
        )

        # ── Send a message to trigger at least one SSE event ──────────────────
        import time as _time
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        trigger = {
            "type": "acp.message",
            "message_id": msg_id,
            "ts": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "from": "compat-runner",
            "role": "user",
            "parts": [{"type": "text", "content": "SSE compat test ping"}],
        }
        self.post("/message:send", trigger)

        # ── Read SSE events for 2 seconds ─────────────────────────────────────
        events = _read_sse_events(self.base_url, stream_path, timeout=2.0)

        self.check(
            "At least one SSE event received within 2s of connect",
            len(events) > 0,
            "SHOULD",
            f"received {len(events)} event(s)"
        )

        if not events:
            # No events — skip remaining event-content tests
            self.skip("SSE events have 'event:' type line", "no events received")
            self.skip("SSE data field is valid JSON", "no events received")
            self.skip("Event type is known ACP type", "no events received")
        else:
            # ── event: line present ───────────────────────────────────────────
            events_with_type = [e for e in events if "event" in e]
            self.check(
                "SSE events have 'event:' type line",
                len(events_with_type) > 0,
                "MUST",
                f"{len(events_with_type)}/{len(events)} events have 'event:' field"
            )

            # ── data: is valid JSON ───────────────────────────────────────────
            events_with_json = [
                e for e in events
                if isinstance(e.get("data"), dict)
            ]
            self.check(
                "SSE 'data:' field is valid JSON object",
                len(events_with_json) > 0,
                "MUST",
                f"{len(events_with_json)}/{len(events)} events have valid JSON data"
            )

            # ── Event type values ─────────────────────────────────────────────
            KNOWN_TYPES = {"acp.message", "acp.status", "acp.artifact", "acp.error",
                           "acp.peer", "acp.ping", "acp.ready"}
            event_types = {e.get("event") for e in events if "event" in e}
            known_found = event_types & KNOWN_TYPES
            self.check(
                "Event 'event:' type is a known ACP event type",
                len(known_found) > 0,
                "SHOULD",
                f"found types: {event_types!r}; known ACP types: {KNOWN_TYPES!r}"
            )

            # ── JSON data has 'type' field matching event: line ───────────────
            mismatch = 0
            for e in events:
                if isinstance(e.get("data"), dict) and "event" in e:
                    data_type = e["data"].get("type", "")
                    event_line = e["event"]
                    # data.type should equal event: line (or be prefixed by it)
                    if data_type and event_line and not data_type.startswith(event_line.split(".")[0]):
                        mismatch += 1
            self.check(
                "SSE data.type consistent with event: line",
                mismatch == 0,
                "SHOULD",
                f"{mismatch} event(s) had data.type inconsistent with event: line"
            )

        # ── ?since= parameter ─────────────────────────────────────────────────
        if self.has_capability("server_seq"):
            since_events = _read_sse_events(
                self.base_url, f"{stream_path}?since=0", timeout=1.5
            )
            # We can't assert content, but endpoint should not return 400/404
            # (we check it doesn't immediately close with error)
            # Re-check content-type with ?since=0
            ct_since, _ = _check_content_type(self.base_url, f"{stream_path}?since=0")
            self.check(
                "/stream?since=<seq> accepted (returns event-stream, not error)",
                ct_since,
                "SHOULD",
                "server_seq capability declared; should support ?since= replay"
            )
        else:
            self.skip("/stream?since= parameter accepted", "server_seq not declared — replay not required")
