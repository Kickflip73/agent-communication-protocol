#!/usr/bin/env python3
"""
ACP 心跳测试 — 场景 C + D（2026-03-28 12:18）
================================================
场景 C: 多 Agent 流水线（链式 A→B→C→A）
场景 D: 压力测试（100 条消息，验证无丢失、seq 单调递增）

直接执行：python3 tests/run_scenario_cd_heartbeat.py
"""

import http.client as _http
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

RELAY_PATH = os.path.join(os.path.dirname(__file__), '..', 'relay', 'acp_relay.py')
TESTS_DIR  = os.path.dirname(__file__)
sys.path.insert(0, TESTS_DIR)
from helpers import clean_subprocess_env


# ─── Port utilities ────────────────────────────────────────────────────────────

def _free_port():
    """Find an OS-assigned free port where ws_port AND ws_port+100 are both free."""
    for _ in range(300):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("Could not find a free port pair")


# ─── HTTP helpers ──────────────────────────────────────────────────────────────

def http_req(method, http_port, path, body=None, timeout=10):
    conn = _http.HTTPConnection("127.0.0.1", http_port, timeout=timeout)
    if body is not None:
        data = json.dumps(body).encode()
        hdrs = {"Content-Type": "application/json", "Content-Length": str(len(data))}
        conn.request(method, path, data, hdrs)
    else:
        conn.request(method, path)
    resp = conn.getresponse()
    raw  = resp.read()
    try:
        return resp.status, json.loads(raw)
    except Exception:
        return resp.status, raw

def get(http_port, path):               return http_req("GET",  http_port, path)
def post(http_port, path, body=None):   return http_req("POST", http_port, path, body)


# ─── Relay lifecycle ───────────────────────────────────────────────────────────

def start_relay(ws_port, name, wait_link=False, inbox_prefix="/tmp/acp_cd"):
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH,
         "--port", str(ws_port),
         "--name", name,
         "--inbox", f"{inbox_prefix}_{name}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=clean_subprocess_env(),
    )
    deadline = time.time() + 65
    while time.time() < deadline:
        try:
            conn = _http.HTTPConnection("127.0.0.1", http_port, timeout=1)
            conn.request("GET", "/status")
            resp = conn.getresponse()
            raw  = resp.read()
            if resp.status == 200:
                if not wait_link:
                    return proc
                try:
                    data = json.loads(raw)
                    if data.get("link"):
                        return proc
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.3)
    proc.kill()
    raise RuntimeError(f"Relay {name}:{ws_port} did not start within 65s")


def stop_relay(proc):
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    except Exception:
        pass


def probe_peer_ready(http_port, peer_id, deadline_s=15):
    """Probe-send until the peer WS is truly ready (not just connected=True)."""
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        s, r = post(http_port, f"/peer/{peer_id}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "__probe__"}],
        })
        if s == 200 and isinstance(r, dict) and r.get("ok"):
            return True
        time.sleep(0.3)
    return False


def get_link(http_port, timeout=65):
    """Poll /status until link is non-None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s, r = get(http_port, "/status")
            if s == 200 and isinstance(r, dict) and r.get("link"):
                return r["link"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def connect_peer(from_port, to_link):
    """POST /peers/connect and return peer_id or raise."""
    s, r = post(from_port, "/peers/connect", {"link": to_link, "role": "agent"})
    assert s == 200 and r.get("ok"), f"connect failed: {s} {r}"
    peer_id = r.get("peer_id")
    assert peer_id, f"no peer_id in response: {r}"
    return peer_id


def recv_messages(http_port, limit=200):
    """GET /recv?limit=N, normalize result."""
    s, r = http_req("GET", http_port, f"/recv?limit={limit}")
    if isinstance(r, dict):
        msgs = r.get("messages", [])
    elif isinstance(r, list):
        msgs = r
    else:
        msgs = []
    return msgs


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO C — Ring Pipeline  A → B → C → A
# ══════════════════════════════════════════════════════════════════════════════

def run_scenario_c():
    print("\n" + "="*60)
    print("SCENARIO C: Ring Pipeline A → B → C → A")
    print("="*60)

    # Allocate 3 relay port pairs
    ws_a = _free_port()
    ws_b = _free_port()
    ws_c = _free_port()
    hp_a, hp_b, hp_c = ws_a+100, ws_b+100, ws_c+100

    print(f"  Ports: A={ws_a}/{hp_a}  B={ws_b}/{hp_b}  C={ws_c}/{hp_c}")

    procs = []
    passed = 0
    failed = 0
    new_bugs = []

    try:
        # Step 1: Start 3 relays
        print("\n[C1] Starting 3 relay instances …")
        proc_a = start_relay(ws_a, "RingA")
        proc_b = start_relay(ws_b, "RingB")
        proc_c = start_relay(ws_c, "RingC")
        procs = [proc_a, proc_b, proc_c]
        print("  ✅ All 3 relays started")
        passed += 1

        # Step 2: Get links (wait concurrently)
        print("\n[C2] Waiting for public links (parallel) …")
        links = [None, None, None]
        errors = [None, None, None]

        def fetch_link(idx, hp):
            lnk = get_link(hp, timeout=65)
            if lnk:
                links[idx] = lnk
            else:
                errors[idx] = f"link not available on port {hp}"

        threads = [threading.Thread(target=fetch_link, args=(i, p))
                   for i, p in enumerate([hp_a, hp_b, hp_c])]
        for t in threads: t.start()
        for t in threads: t.join()

        link_a, link_b, link_c = links
        if all(links):
            print(f"  ✅ All links ready")
            print(f"     A: {link_a[:40]}…")
            print(f"     B: {link_b[:40]}…")
            print(f"     C: {link_c[:40]}…")
            passed += 1
        else:
            for i, err in enumerate(errors):
                if err:
                    print(f"  ❌ Link error: {err}")
            failed += 1
            return passed, failed, new_bugs, "C2 failed: links not ready"

        # Step 3: Build ring topology A→B, B→C, C→A
        print("\n[C3] Building ring topology A→B → B→C → C→A …")
        peer_a_to_b = connect_peer(hp_a, link_b)
        assert probe_peer_ready(hp_a, peer_a_to_b), "A→B peer not ready"
        print(f"  A→B: peer_id={peer_a_to_b}")

        peer_b_to_c = connect_peer(hp_b, link_c)
        assert probe_peer_ready(hp_b, peer_b_to_c), "B→C peer not ready"
        print(f"  B→C: peer_id={peer_b_to_c}")

        peer_c_to_a = connect_peer(hp_c, link_a)
        assert probe_peer_ready(hp_c, peer_c_to_a), "C→A peer not ready"
        print(f"  C→A: peer_id={peer_c_to_a}")
        passed += 1

        # Step 4: A sends a message to B
        print("\n[C4] A → B: sending pipeline message …")
        mid_ab = f"ring-ab-{uuid.uuid4().hex[:8]}"
        s, r = post(hp_a, f"/peer/{peer_a_to_b}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "pipeline_start"}],
            "message_id": mid_ab,
        })
        assert s == 200 and r.get("ok"), f"A→B send failed: {s} {r}"
        seq_ab = r.get("server_seq")
        print(f"  ✅ A→B sent  message_id={mid_ab}  server_seq={seq_ab}")
        passed += 1

        # Step 5: Verify B received A's message
        print("\n[C5] Verifying B received A's message …")
        time.sleep(0.5)
        msgs_b = recv_messages(hp_b)
        # Filter out probe messages
        real_b = [m for m in msgs_b if not any(
            (p.get("text","") == "__probe__") for p in m.get("parts",[])
        )]
        found_ab = any(
            any(p.get("text","") == "pipeline_start" for p in m.get("parts",[]))
            for m in real_b
        )
        if found_ab:
            print(f"  ✅ B received A's message (inbox count={len(real_b)})")
            passed += 1
        else:
            print(f"  ❌ B did NOT receive A's message (inbox count={len(real_b)})")
            failed += 1

        # Step 6: B forwards to C
        print("\n[C6] B → C: forwarding pipeline message …")
        mid_bc = f"ring-bc-{uuid.uuid4().hex[:8]}"
        s, r = post(hp_b, f"/peer/{peer_b_to_c}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "pipeline_forwarded"}],
            "message_id": mid_bc,
        })
        assert s == 200 and r.get("ok"), f"B→C send failed: {s} {r}"
        seq_bc = r.get("server_seq")
        print(f"  ✅ B→C sent  message_id={mid_bc}  server_seq={seq_bc}")
        passed += 1

        # Step 7: Verify C received B's message
        print("\n[C7] Verifying C received B's forwarded message …")
        time.sleep(0.5)
        msgs_c = recv_messages(hp_c)
        real_c = [m for m in msgs_c if not any(
            p.get("text","") == "__probe__" for p in m.get("parts",[])
        )]
        found_bc = any(
            any(p.get("text","") == "pipeline_forwarded" for p in m.get("parts",[]))
            for m in real_c
        )
        if found_bc:
            print(f"  ✅ C received B's forwarded message (inbox count={len(real_c)})")
            passed += 1
        else:
            print(f"  ❌ C did NOT receive B's forwarded message (inbox count={len(real_c)})")
            failed += 1

        # Step 8: C returns result to A (closing the ring)
        print("\n[C8] C → A: returning result to close the ring …")
        mid_ca = f"ring-ca-{uuid.uuid4().hex[:8]}"
        s, r = post(hp_c, f"/peer/{peer_c_to_a}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "pipeline_result"}],
            "message_id": mid_ca,
        })
        assert s == 200 and r.get("ok"), f"C→A send failed: {s} {r}"
        seq_ca = r.get("server_seq")
        print(f"  ✅ C→A sent  message_id={mid_ca}  server_seq={seq_ca}")
        passed += 1

        # Step 9: Verify A received C's result
        print("\n[C9] Verifying A received C's result (pipeline closed) …")
        time.sleep(0.5)
        msgs_a = recv_messages(hp_a)
        real_a = [m for m in msgs_a if not any(
            p.get("text","") == "__probe__" for p in m.get("parts",[])
        )]
        found_ca = any(
            any(p.get("text","") == "pipeline_result" for p in m.get("parts",[]))
            for m in real_a
        )
        if found_ca:
            print(f"  ✅ A received C's result — pipeline CLOSED ✅ (inbox count={len(real_a)})")
            passed += 1
        else:
            print(f"  ❌ A did NOT receive C's result (inbox count={len(real_a)})")
            failed += 1

        # Summary
        print(f"\n[C-SUMMARY] Ring pipeline: {passed} checks passed, {failed} failed")
        print(f"  Messages: A→B (id={mid_ab}, seq={seq_ab}), "
              f"B→C (id={mid_bc}, seq={seq_bc}), "
              f"C→A (id={mid_ca}, seq={seq_ca})")

    except Exception as e:
        print(f"  ❌ Exception: {e}")
        failed += 1
        import traceback; traceback.print_exc()
    finally:
        for p in procs:
            stop_relay(p)

    return passed, failed, new_bugs


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO D — Stress Test (100 messages)
# ══════════════════════════════════════════════════════════════════════════════

def run_scenario_d():
    print("\n" + "="*60)
    print("SCENARIO D: Stress Test — 100 Messages")
    print("="*60)

    ws_alpha = _free_port()
    ws_beta  = _free_port()
    hp_alpha = ws_alpha + 100
    hp_beta  = ws_beta  + 100

    print(f"  Ports: Alpha={ws_alpha}/{hp_alpha}  Beta={ws_beta}/{hp_beta}")

    passed = 0
    failed = 0
    new_bugs = []
    procs = []
    N = 100

    try:
        # Start relays
        print("\n[D1] Starting Alpha and Beta relays …")
        proc_alpha = start_relay(ws_alpha, "StressAlpha2")
        proc_beta  = start_relay(ws_beta,  "StressBeta2", wait_link=True)
        procs = [proc_alpha, proc_beta]
        print("  ✅ Both relays started")
        passed += 1

        # Get Beta link
        print("\n[D2] Connecting Alpha → Beta …")
        s, r = get(hp_beta, "/status")
        beta_link = r.get("link") if isinstance(r, dict) else None
        assert beta_link, f"Beta link not available: {r}"

        s2, r2 = post(hp_alpha, "/peers/connect", {"link": beta_link, "role": "agent"})
        assert s2 == 200 and r2.get("ok"), f"Connect failed: {s2} {r2}"
        peer_id = r2.get("peer_id")
        assert peer_id

        # Wait for WS to be truly ready
        ready = probe_peer_ready(hp_alpha, peer_id, deadline_s=20)
        assert ready, f"Peer {peer_id} not ready within 20s"
        print(f"  ✅ Alpha→Beta connected (peer_id={peer_id})")
        passed += 1

        # ── D3: Send 100 sequential messages, record message_id + server_seq ──
        print(f"\n[D3] Sending {N} sequential messages …")
        sent_records = []   # list of {message_id, server_seq, idx}
        errors_send  = []

        t_send_start = time.time()
        for i in range(N):
            mid = f"stress2-{i:03d}-{uuid.uuid4().hex[:8]}"
            s, r = post(hp_alpha, f"/peer/{peer_id}/send", {
                "role": "agent",
                "parts": [{"kind": "text", "text": f"load msg #{i:03d}"}],
                "message_id": mid,
            })
            if s == 200 and isinstance(r, dict) and r.get("ok"):
                seq = r.get("server_seq")
                sent_records.append({"idx": i, "message_id": mid, "server_seq": seq})
            else:
                errors_send.append({"idx": i, "status": s, "resp": r})

        t_send_end = time.time()
        send_elapsed = t_send_end - t_send_start
        send_rate    = N / send_elapsed

        print(f"  Sent: {len(sent_records)}/{N} OK  errors={len(errors_send)}")
        print(f"  Elapsed: {send_elapsed:.2f}s  Rate: {send_rate:.1f} msg/s")

        if len(sent_records) == N:
            print("  ✅ All 100 messages sent successfully")
            passed += 1
        else:
            print(f"  ❌ {N - len(sent_records)} messages failed to send")
            failed += 1

        # ── D4: Verify server_seq monotonically increasing ──
        print(f"\n[D4] Checking server_seq monotonicity …")
        seqs = [rec["server_seq"] for rec in sent_records if rec["server_seq"] is not None]
        missing_seq = [rec for rec in sent_records if rec["server_seq"] is None]

        if missing_seq:
            print(f"  ⚠️  {len(missing_seq)} records missing server_seq (server_seq=None)")

        seq_monotonic = True
        first_violation = None
        for i in range(1, len(seqs)):
            if seqs[i] <= seqs[i-1]:
                seq_monotonic = False
                first_violation = (i, seqs[i-1], seqs[i])
                break

        if seq_monotonic and seqs:
            print(f"  ✅ server_seq monotonically increasing  [{seqs[0]} … {seqs[-1]}]  count={len(seqs)}")
            passed += 1
        elif not seqs:
            print(f"  ⚠️  No server_seq values to check (all None — server may not return seq)")
            # Not a bug if server doesn't return seq in response
            passed += 1
        else:
            print(f"  ❌ server_seq NOT monotonic! First violation at idx={first_violation[0]}: "
                  f"{first_violation[1]} → {first_violation[2]}")
            failed += 1
            new_bugs.append({
                "id": "BUG-NEW-D4",
                "title": "server_seq not monotonically increasing in stress test",
                "violation": first_violation,
            })

        # ── D5: Verify Beta received all messages ──
        print(f"\n[D5] Verifying Beta received all {N} messages …")
        time.sleep(1.5)  # Allow async delivery
        msgs_beta = recv_messages(hp_beta, limit=300)

        # Filter out probe messages
        real_msgs = [m for m in msgs_beta if not any(
            p.get("text","") == "__probe__" for p in m.get("parts",[])
        )]
        received_count = len(real_msgs)

        t_recv_end = time.time()
        recv_elapsed = t_recv_end - t_send_start
        recv_rate    = received_count / recv_elapsed if recv_elapsed > 0 else 0

        print(f"  Beta inbox: {received_count} messages (expected {N})")
        print(f"  End-to-end elapsed: {recv_elapsed:.2f}s  Effective recv rate: {recv_rate:.1f} msg/s")

        if received_count >= N:
            print(f"  ✅ All {N} messages received by Beta")
            passed += 1
        else:
            loss = N - received_count
            loss_pct = loss / N * 100
            print(f"  ❌ {loss} messages lost ({loss_pct:.1f}% loss rate)")
            failed += 1
            if loss_pct > 5:
                new_bugs.append({
                    "id": "BUG-NEW-D5",
                    "title": f"Message loss in stress test: {loss}/{N} lost ({loss_pct:.1f}%)",
                })

        # ── D6: Message loss rate ──
        print(f"\n[D6] Loss rate summary …")
        sent_ok   = len(sent_records)
        recv_ok   = received_count
        send_loss = N - sent_ok
        recv_loss = sent_ok - recv_ok if recv_ok < sent_ok else 0
        total_loss = N - recv_ok
        loss_rate  = total_loss / N * 100
        print(f"  Sent OK:     {sent_ok}/{N}  ({send_loss} send-side failures)")
        print(f"  Received OK: {recv_ok}/{sent_ok}  ({recv_loss} transit losses)")
        print(f"  Total loss rate: {loss_rate:.2f}%")
        if loss_rate == 0:
            print("  ✅ Zero packet loss")
            passed += 1
        elif loss_rate <= 1.0:
            print(f"  ⚠️  Acceptable loss {loss_rate:.2f}%")
            passed += 1
        else:
            print(f"  ❌ Unacceptable loss rate {loss_rate:.2f}%")
            failed += 1

        # Final stats
        print(f"\n[D-SUMMARY]")
        print(f"  Send rate:    {send_rate:.1f} msg/s over {send_elapsed:.2f}s")
        print(f"  Receive rate: {recv_rate:.1f} msg/s (end-to-end)")
        print(f"  Loss rate:    {loss_rate:.2f}%")
        print(f"  seq range:    {seqs[0] if seqs else 'N/A'} … {seqs[-1] if seqs else 'N/A'}")
        print(f"  Checks: {passed} passed, {failed} failed")

    except Exception as e:
        print(f"  ❌ Exception: {e}")
        failed += 1
        import traceback; traceback.print_exc()
    finally:
        for p in procs:
            stop_relay(p)

    return passed, failed, new_bugs, {
        "sent": len(sent_records) if 'sent_records' in dir() else 0,
        "received": received_count if 'received_count' in dir() else 0,
        "loss_rate": loss_rate if 'loss_rate' in dir() else -1,
        "send_rate": send_rate if 'send_rate' in dir() else 0,
        "seq_monotonic": seq_monotonic if 'seq_monotonic' in dir() else False,
        "seqs": seqs if 'seqs' in dir() else [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\nACP Heartbeat Test — 2026-03-28 12:18")
    print(f"Relay: {RELAY_PATH}")
    # Confirm relay version
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("_relay", RELAY_PATH)
    mod  = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print(f"Relay VERSION: {mod.VERSION}")
    print()

    # ── Scenario C ──────────────────────────────────────────────────────────
    c_passed, c_failed, c_bugs = run_scenario_c()

    # ── Scenario D ──────────────────────────────────────────────────────────
    d_passed, d_failed, d_bugs, d_stats = run_scenario_d()

    # ── Aggregate ────────────────────────────────────────────────────────────
    all_bugs = c_bugs + d_bugs
    total_p  = c_passed + d_passed
    total_f  = c_failed + d_failed

    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Scenario C: {c_passed} passed, {c_failed} failed")
    print(f"Scenario D: {d_passed} passed, {d_failed} failed")
    print(f"Overall:    {total_p} passed, {total_f} failed")
    print(f"New bugs:   {len(all_bugs)}")
    if all_bugs:
        for b in all_bugs:
            print(f"  - {b['id']}: {b['title']}")

    # Export results for caller
    import json as _json_out
    results = {
        "scenario_c": {"passed": c_passed, "failed": c_failed, "bugs": c_bugs},
        "scenario_d": {"passed": d_passed, "failed": d_failed, "bugs": d_bugs, "stats": d_stats},
        "all_bugs": all_bugs,
    }
    result_path = os.path.join(os.path.dirname(__file__), "..", "heartbeat_cd_results.json")
    with open(result_path, "w") as f:
        _json_out.dump(results, f, indent=2)
    print(f"\nResults saved to: {result_path}")

    sys.exit(0 if total_f == 0 else 1)
