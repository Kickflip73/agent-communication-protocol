"""
Messages Stream Tests — v3.17 feature verification

Tests POST /messages:stream — WebSocket streaming message inlet.

Completes the reliable-messaging trio:
  batch (v3.15) + ACK (v3.16) + stream (v3.17)

Test matrix:
  test_ms_01  capabilities.messages_stream=true declared in AgentCard and /status
  test_ms_02  WS connect to /messages:stream, send one msg → {ok:true} confirm frame
  test_ms_03  send 5 consecutive msgs → each gets confirm frame; server_seq increments
  test_ms_04  peer_id not found → {ok:false, error:"ERR_PEER_NOT_FOUND"}
  test_ms_05  invalid JSON frame → error response without crash
  test_ms_06  two connected relays: stream-send on alpha → recv on beta
"""
import pytest
import requests
import subprocess
import time
import signal
import sys
import os
import json
import socket
import struct
import hashlib
import base64
import threading
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_PORT = 54200  # use a distinct base to avoid port collisions with other test suites


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _free_port_pair():
    """Return a free (ws_port, http_port) pair."""
    for _ in range(100):
        ws_port = BASE_PORT + random.randint(0, 700)
        http_port = ws_port + 100
        try:
            s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s1.bind(("127.0.0.1", ws_port))
            s1.close()
            s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s2.bind(("127.0.0.1", http_port))
            s2.close()
            return ws_port, http_port
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


def _relay_env():
    env = os.environ.copy()
    for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
        env.pop(v, None)
    return env


def _start_relay(ws_port, http_port, name="MSTest", join_link=None):
    """Start a relay subprocess and wait until HTTP /status is ready."""
    cmd = [
        "python3", "-u", "relay/acp_relay.py",
        "--port", str(ws_port),
        "--http-host", "127.0.0.1",
        "--name", name,
        "--local-only",
    ]
    if join_link:
        cmd.extend(["--join", join_link])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_relay_env(),
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"Relay '{name}' exited early.\nstdout: {out}\nstderr: {err}")
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=0.5)
            if r.status_code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)

    proc.terminate()
    raise RuntimeError(f"Relay '{name}' did not start within 30s")


def _stop_relay(proc):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _alpha_link(http_port):
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=1)
            lnk = r.json().get("link")
            if lnk:
                return lnk
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError("Alpha link not available")


def _wait_peer(http_port, retries=40):
    """Wait for at least one connected peer; return first peer_id or None."""
    for _ in range(retries):
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/peers", timeout=1)
            for p in r.json().get("peers", []):
                if p.get("connected"):
                    return p["id"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Minimal RFC 6455 WebSocket client (no external library dependency)
# ──────────────────────────────────────────────────────────────────────────────

class _WsClient:
    """
    A minimal synchronous WebSocket client for testing /messages:stream.
    Implements RFC 6455 framing: masked client→server frames, unmasked server→client.
    """

    def __init__(self, host: str, port: int, path: str = "/messages:stream"):
        self._sock = socket.create_connection((host, port), timeout=10)
        self._path = path
        self._do_handshake(host)

    def _do_handshake(self, host: str):
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"POST {self._path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self._sock.sendall(request.encode())

        # Read until \r\n\r\n
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self._sock.recv(1024)
            if not chunk:
                raise ConnectionError("Server closed connection during WS handshake")
            buf += chunk

        status_line = buf.split(b"\r\n")[0].decode()
        if "101" not in status_line:
            raise ConnectionError(f"WS handshake failed: {status_line!r}")

        # Verify Sec-WebSocket-Accept
        magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        expected = base64.b64encode(
            hashlib.sha1((key + magic).encode()).digest()
        ).decode()
        if expected not in buf.decode(errors="replace"):
            raise ConnectionError("Sec-WebSocket-Accept mismatch")

    def send_json(self, obj: dict):
        """Send a JSON text frame (masked, as required for client→server)."""
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        mask_key = os.urandom(4)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        length = len(masked)
        header = bytearray()
        header.append(0x81)  # FIN + opcode text
        if length < 126:
            header.append(0x80 | length)  # MASK bit set
        elif length < 65536:
            header.append(0x80 | 126)
            header += length.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += length.to_bytes(8, "big")
        header += mask_key
        self._sock.sendall(bytes(header) + masked)

    def recv_json(self, timeout: float = 5.0) -> dict:
        """Receive one WebSocket frame and parse as JSON."""
        self._sock.settimeout(timeout)
        header = b""
        while len(header) < 2:
            chunk = self._sock.recv(2 - len(header))
            if not chunk:
                raise ConnectionResetError("Connection closed during recv")
            header += chunk

        opcode = header[0] & 0x0F
        masked = (header[1] & 0x80) != 0
        length = header[1] & 0x7F

        if length == 126:
            lb = b""
            while len(lb) < 2:
                lb += self._sock.recv(2 - len(lb))
            length = int.from_bytes(lb, "big")
        elif length == 127:
            lb = b""
            while len(lb) < 8:
                lb += self._sock.recv(8 - len(lb))
            length = int.from_bytes(lb, "big")

        mask_key = b""
        if masked:
            while len(mask_key) < 4:
                mask_key += self._sock.recv(4 - len(mask_key))

        payload = b""
        while len(payload) < length:
            chunk = self._sock.recv(length - len(payload))
            if not chunk:
                raise ConnectionResetError("Connection closed during payload")
            payload += chunk

        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        if opcode == 0x8:
            raise ConnectionResetError("Server sent close frame")
        if opcode not in (0x1, 0x2):
            # control frame (ping/pong) — skip and read next
            return self.recv_json(timeout=timeout)

        return json.loads(payload.decode("utf-8"))

    def close(self):
        try:
            # Send close frame
            close_frame = bytes([0x88, 0x80]) + os.urandom(4)
            self._sock.sendall(close_frame)
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def single_relay():
    """A standalone relay with no connected peer."""
    ws, http = _free_port_pair()
    proc = _start_relay(ws, http, "MSSolo")
    yield {"http": http, "ws": ws, "proc": proc, "host": "127.0.0.1"}
    _stop_relay(proc)


@pytest.fixture(scope="module")
def relay_pair():
    """Two connected relays (alpha + beta)."""
    a_ws, a_http = _free_port_pair()
    b_ws, b_http = _free_port_pair()

    alpha = _start_relay(a_ws, a_http, "MSAlpha")
    link = _alpha_link(a_http)
    beta = _start_relay(b_ws, b_http, "MSBeta", join_link=link)

    peer_id = _wait_peer(a_http, retries=40)
    if not peer_id:
        _stop_relay(beta)
        _stop_relay(alpha)
        pytest.fail("relay_pair: peer connection not established within 20s")

    yield {
        "alpha": {"http": a_http, "ws": a_ws, "proc": alpha,
                  "peer_id": peer_id, "host": "127.0.0.1"},
        "beta":  {"http": b_http, "ws": b_ws, "proc": beta, "host": "127.0.0.1"},
    }
    _stop_relay(beta)
    _stop_relay(alpha)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMessagesStream:

    # ── test_ms_01 ───────────────────────────────────────────────────────────
    def test_ms_01_capability_declared(self, single_relay):
        """MS-01: capabilities.messages_stream=true in AgentCard and /status."""
        # Check AgentCard
        r = requests.get(
            f"http://127.0.0.1:{single_relay['http']}/.well-known/acp.json", timeout=5
        )
        assert r.status_code == 200
        data = r.json()
        caps = data["self"]["capabilities"]
        assert caps.get("messages_stream") is True, (
            f"AgentCard capabilities.messages_stream not true — got: {caps.get('messages_stream')}"
        )

        # Check /status
        r2 = requests.get(
            f"http://127.0.0.1:{single_relay['http']}/status", timeout=5
        )
        assert r2.status_code == 200
        status_data = r2.json()
        # capabilities may be at top-level or nested under agent_card
        status_caps = (
            status_data.get("capabilities")
            or status_data.get("agent_card", {}).get("capabilities", {})
        )
        assert status_caps.get("messages_stream") is True, (
            f"/status capabilities.messages_stream not true — got: {status_caps.get('messages_stream')}"
        )

    # ── test_ms_02 ───────────────────────────────────────────────────────────
    def test_ms_02_single_message_confirm_frame(self, relay_pair):
        """MS-02: Connect to /messages:stream, send one message, receive {ok:true} confirm frame."""
        alpha = relay_pair["alpha"]
        peer_id = alpha["peer_id"]

        ws = _WsClient(alpha["host"], alpha["http"], "/messages:stream")
        try:
            ws.send_json({
                "peer_id":    peer_id,
                "content":    "hello from stream",
                "message_id": "test-ms-02-msg",
            })
            resp = ws.recv_json(timeout=8)
        finally:
            ws.close()

        assert resp.get("ok") is True, (
            f"Expected ok:true confirm frame, got: {resp}"
        )
        assert resp.get("message_id") == "test-ms-02-msg", (
            f"message_id echo mismatch: {resp}"
        )
        assert "server_seq" in resp, (
            f"server_seq missing from confirm frame: {resp}"
        )
        assert isinstance(resp["server_seq"], int), (
            f"server_seq should be an int, got: {resp['server_seq']!r}"
        )

    # ── test_ms_03 ───────────────────────────────────────────────────────────
    def test_ms_03_multi_message_seq_increments(self, relay_pair):
        """MS-03: Send 5 messages; each gets a confirm frame; server_seq strictly increases."""
        alpha = relay_pair["alpha"]
        peer_id = alpha["peer_id"]

        ws = _WsClient(alpha["host"], alpha["http"], "/messages:stream")
        confirms = []
        try:
            for i in range(5):
                ws.send_json({
                    "peer_id":    peer_id,
                    "content":    f"stream msg {i}",
                    "message_id": f"test-ms-03-msg-{i}",
                })
            # Collect all 5 confirmations
            for _ in range(5):
                confirms.append(ws.recv_json(timeout=8))
        finally:
            ws.close()

        assert len(confirms) == 5, f"Expected 5 confirm frames, got {len(confirms)}"

        for idx, c in enumerate(confirms):
            assert c.get("ok") is True, f"Confirm {idx} ok!=true: {c}"
            assert "server_seq" in c, f"Confirm {idx} missing server_seq: {c}"

        seqs = [c["server_seq"] for c in confirms]
        assert seqs == sorted(seqs), (
            f"server_seq not monotonically increasing: {seqs}"
        )
        assert len(set(seqs)) == 5, (
            f"server_seq values not unique: {seqs}"
        )

    # ── test_ms_04 ───────────────────────────────────────────────────────────
    def test_ms_04_unknown_peer_returns_error(self, single_relay):
        """MS-04: Sending to a nonexistent peer_id returns {ok:false, error:'ERR_PEER_NOT_FOUND'}."""
        ws = _WsClient(single_relay["host"], single_relay["http"], "/messages:stream")
        try:
            ws.send_json({
                "peer_id":    "peer_nonexistent_xyz_12345",
                "content":    "should fail",
                "message_id": "test-ms-04-msg",
            })
            resp = ws.recv_json(timeout=8)
        finally:
            ws.close()

        assert resp.get("ok") is False, (
            f"Expected ok:false for unknown peer, got: {resp}"
        )
        assert resp.get("error") == "ERR_PEER_NOT_FOUND", (
            f"Expected ERR_PEER_NOT_FOUND, got: {resp.get('error')!r}"
        )
        assert resp.get("message_id") == "test-ms-04-msg", (
            f"message_id echo missing in error: {resp}"
        )

    # ── test_ms_05 ───────────────────────────────────────────────────────────
    def test_ms_05_invalid_json_frame_no_crash(self, single_relay):
        """MS-05: Sending an invalid JSON frame returns an error response; relay does not crash."""
        ws = _WsClient(single_relay["host"], single_relay["http"], "/messages:stream")
        try:
            # Send raw invalid JSON frame (not using send_json which serializes)
            bad_payload = b"{not valid json!!!"
            mask_key = os.urandom(4)
            masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(bad_payload))
            header = bytearray([0x81, 0x80 | len(masked)]) + bytearray(mask_key)
            ws._sock.sendall(bytes(header) + masked)

            resp = ws.recv_json(timeout=8)
        finally:
            ws.close()

        assert resp.get("ok") is False, (
            f"Expected ok:false for invalid JSON, got: {resp}"
        )
        assert "error" in resp, f"Expected 'error' key in response: {resp}"
        # ERR_INVALID_JSON is the expected error code
        assert "JSON" in resp.get("error", "").upper() or "INVALID" in resp.get("error", "").upper(), (
            f"Expected JSON/INVALID in error msg, got: {resp.get('error')!r}"
        )

        # Relay must still be up
        r = requests.get(
            f"http://127.0.0.1:{single_relay['http']}/status", timeout=5
        )
        assert r.status_code == 200, "Relay crashed after receiving invalid JSON WS frame"

    # ── test_ms_06 ───────────────────────────────────────────────────────────
    def test_ms_06_cross_relay_message_delivery(self, relay_pair):
        """MS-06: Stream message from alpha → peer; beta can read it via /recv."""
        alpha = relay_pair["alpha"]
        beta  = relay_pair["beta"]
        peer_id = alpha["peer_id"]

        # Drain beta's recv queue first
        requests.get(f"http://127.0.0.1:{beta['http']}/recv", timeout=5)

        unique_content = f"stream-cross-relay-{random.randint(100000, 999999)}"

        ws = _WsClient(alpha["host"], alpha["http"], "/messages:stream")
        try:
            ws.send_json({
                "peer_id":    peer_id,
                "content":    unique_content,
                "message_id": "test-ms-06-msg",
            })
            resp = ws.recv_json(timeout=8)
        finally:
            ws.close()

        assert resp.get("ok") is True, (
            f"Stream send should succeed for connected peer, got: {resp}"
        )

        # Give the relay a moment to deliver
        time.sleep(0.8)

        # Check beta's recv
        r = requests.get(f"http://127.0.0.1:{beta['http']}/recv", timeout=5)
        assert r.status_code == 200

        msgs = r.json().get("messages", [])
        found = False
        for m in msgs:
            raw = m.get("raw") or m
            parts = raw.get("parts", [])
            for part in parts:
                if unique_content in str(part.get("text", "")):
                    found = True
                    break
            if not found:
                # Also check content field directly
                if unique_content in str(raw):
                    found = True
            if found:
                break

        assert found, (
            f"Message with content={unique_content!r} not found in beta's /recv.\n"
            f"Messages received: {msgs}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=60"])
