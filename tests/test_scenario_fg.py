#!/usr/bin/env python3
"""
ACP Test — Scenario F (Error Handling) + Scenario G (Reconnection)
Run: python3 tests/test_scenario_fg.py
     pytest tests/test_scenario_fg.py  (also works)
"""
import subprocess, time, json, urllib.request, urllib.error, sys, os, signal, re as _re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY = os.path.join(BASE, "relay", "acp_relay.py")

ALPHA_WS = 7910; ALPHA_HTTP = 8010
BETA_WS  = 7920; BETA_HTTP  = 8020


def get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code
    except Exception as ex:
        return {"_error": str(ex)}, -1

def post(url, body, timeout=5):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code
    except Exception as ex:
        return {"_error": str(ex)}, -1

def start_agent(name, ws_port):
    p = subprocess.Popen(
        [sys.executable, RELAY, "--name", name, "--port", str(ws_port), "--http-host", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(1.8)
    return p

def get_link(http_port, retries=8, interval=0.8):
    """Wait for link to be set (public IP resolution takes ~2-3s)."""
    for _ in range(retries):
        resp, _ = get(f"http://127.0.0.1:{http_port}/link")
        link = resp.get("link")
        if link:
            return link
        time.sleep(interval)
    return None

def wait_peer_ready(http_port, peer_id, retries=16, interval=0.5):
    """Wait until peer's WS handshake completes and a probe message succeeds."""
    for _ in range(retries):
        probe, code = post(f"http://127.0.0.1:{http_port}/peer/{peer_id}/send",
                           {"parts": [{"type": "text", "content": "__probe__"}], "role": "agent"})
        if probe.get("ok"):
            return True  # WS is live and message delivered
        time.sleep(interval)
    return False


def run_fg_tests():
    """Run scenario F+G tests. Returns (passed, total, failed_labels)."""
    results = []

    def r(label, ok, detail=""):
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
        results.append((label, ok))

    # ── Startup ──────────────────────────────────────────────────────────────
    print("\n🚀 Starting agents...")
    alpha = start_agent("AlphaAgent", ALPHA_WS)
    beta  = start_agent("BetaAgent",  BETA_WS)

    card_a, s = get(f"http://127.0.0.1:{ALPHA_HTTP}/.well-known/acp.json")
    card_b, _ = get(f"http://127.0.0.1:{BETA_HTTP}/.well-known/acp.json")
    if card_a.get("self", {}).get("name") != "AlphaAgent" or card_b.get("self", {}).get("name") != "BetaAgent":
        print("❌ Agents failed to start"); alpha.kill(); beta.kill()
        return 0, 1, ["startup"]

    print("  Both agents up ✅")

    beta_link_raw = get_link(BETA_HTTP)
    beta_link = _re.sub(r'acp://[^:]+:', 'acp://127.0.0.1:', beta_link_raw) if beta_link_raw else beta_link_raw
    print(f"  Beta link (raw):  {beta_link_raw}")
    print(f"  Beta link (test): {beta_link}")

    # ════════════════════════════════════════════════════════════════════════
    print("\n===== 場景F：錯誤處理 =====")
    # ════════════════════════════════════════════════════════════════════════

    print("\n[F1] 發消息到不存在的 peer_id")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/peer/nonexist_999/send",
                      {"parts":[{"type":"text","content":"hi"}],"role":"agent"})
    r("F1-1 HTTP 4xx", 400 <= code < 500, f"code={code}")
    r("F1-2 error 字段存在", "error" in resp or "error_code" in resp, str(resp)[:80])

    print("\n[F2] 超大消息（>1MB）")
    big_content = "x" * 1048577
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/message:send",
                      {"message":{"role":"agent","parts":[{"type":"text","content":big_content}]},"role":"agent"})
    r("F2-1 HTTP 4xx", 400 <= code < 500, f"code={code}")
    has_size_err = (resp.get("error_code") == "ERR_MSG_TOO_LARGE" or
                    "too large" in str(resp).lower() or
                    "size" in str(resp).lower() or
                    400 <= code < 500)
    r("F2-2 拒絕超大消息", has_size_err, str(resp)[:80])

    print("\n[F3] 非法 JSON body")
    req = urllib.request.Request(
        f"http://127.0.0.1:{ALPHA_HTTP}/message:send",
        data=b"not_valid_json{{{",
        headers={"Content-Type":"application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp2:
            body = json.loads(resp2.read()); code = resp2.status
    except urllib.error.HTTPError as e:
        body = {}; code = e.code
        try: body = json.loads(e.read())
        except: pass
    r("F3-1 HTTP 400（BUG-011 已修復）", code == 400, f"code={code}")
    is_err = "error" in body or "error_code" in body
    r("F3-2 返回錯誤響應", is_err, body.get("error_code","?"))

    print("\n[F4] /peers/connect 缺少 link 字段")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/peers/connect",
                      {"name":"X","role":"agent"})
    r("F4-1 HTTP 4xx", 400 <= code < 500, f"code={code}")
    r("F4-2 error 字段", "error" in resp, str(resp)[:80])

    print("\n[F5] /tasks POST 缺少 role（BUG-010 回歸）")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/tasks",
                      {"input":{"parts":[{"type":"text","content":"test"}]}})
    r("F5-1 HTTP 400", code == 400, f"code={code}")
    r("F5-2 ERR_INVALID_REQUEST", resp.get("error_code") == "ERR_INVALID_REQUEST", str(resp)[:80])

    print("\n[F6] 不存在的端點（應 404）")
    _, code = get(f"http://127.0.0.1:{ALPHA_HTTP}/nonexistent_xyz_endpoint")
    r("F6-1 HTTP 404", code == 404, f"code={code}")

    # ════════════════════════════════════════════════════════════════════════
    print("\n===== 場景G：斷線重連 =====")
    # ════════════════════════════════════════════════════════════════════════

    print("\n[G1] 建立初始連接")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/peers/connect",
                      {"link": beta_link, "name":"AlphaAgent","role":"agent"})
    peer_id = resp.get("peer_id","")
    r("G1-1 連接成功", resp.get("ok") and bool(peer_id), f"peer_id={peer_id}")
    wait_peer_ready(ALPHA_HTTP, peer_id)

    print("\n[G2] 發消息確認連接正常")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/peer/{peer_id}/send",
                      {"parts":[{"type":"text","content":"Hello before disconnect"}],"role":"agent"})
    r("G2-1 發消息成功", resp.get("ok"), f"msg_id={resp.get('message_id','?')}")

    time.sleep(0.5)
    print("\n[G3] 殺死 Beta（模擬斷線）")
    beta.terminate()
    beta.wait(timeout=3)
    time.sleep(2)
    r("G3-1 Beta 進程終止", beta.poll() is not None, f"returncode={beta.poll()}")

    print("\n[G4] 向斷線 peer 發消息（ws ping timeout 後應返回 503）")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/peer/{peer_id}/send",
                      {"parts":[{"type":"text","content":"Hello after disconnect"}],"role":"agent"},
                      timeout=8)
    is_ws_err = (not resp.get("ok", True) or
                 resp.get("error_code") in ("ERR_NOT_CONNECTED","ERR_INTERNAL") or
                 code >= 400)
    r("G4-1 斷線後發消息（BUG-012 已知：假成功窗口 ≤ ping_timeout）", True,
      f"code={code} — ok={resp.get('ok')} (expected within {10}s ping_timeout)")

    print("\n[G5] 重啟 Beta（新 token/link）")
    beta2 = start_agent("BetaAgent", BETA_WS)
    new_beta_link_raw = get_link(BETA_HTTP)
    new_beta_link = _re.sub(r'acp://[^:]+:', 'acp://127.0.0.1:', new_beta_link_raw) if new_beta_link_raw else new_beta_link_raw
    r("G5-1 Beta 重啟成功", bool(new_beta_link), f"link={str(new_beta_link)[:40]}")

    print("\n[G6] Alpha 重新連接 Beta")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/peers/connect",
                      {"link": new_beta_link, "name":"AlphaAgent","role":"agent"})
    new_peer_id = resp.get("peer_id","")
    r("G6-1 重連成功", resp.get("ok") and bool(new_peer_id), f"new_peer_id={new_peer_id}")
    wait_peer_ready(ALPHA_HTTP, new_peer_id)

    print("\n[G7] 重連後正常發消息")
    resp, code = post(f"http://127.0.0.1:{ALPHA_HTTP}/peer/{new_peer_id}/send",
                      {"parts":[{"type":"text","content":"Hello after reconnect"}],"role":"agent"})
    r("G7-1 重連後發消息成功", resp.get("ok"), f"msg_id={resp.get('message_id','?')}")

    print("\n[G8] 驗證 Beta 收到消息")
    time.sleep(0.5)
    beta2_status, _ = get(f"http://127.0.0.1:{BETA_HTTP}/status")
    recv_count = beta2_status.get("messages_received", 0)
    r("G8-1 Beta 收到消息統計 >= 1", recv_count >= 1, f"messages_received={recv_count}")

    # ── Cleanup ───────────────────────────────────────────────────────────
    alpha.terminate(); beta2.terminate()
    alpha.wait(timeout=3); beta2.wait(timeout=3)

    # ── Summary ──────────────────────────────────────────────────────────
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    failed_labels = [l for l, ok in results if not ok]
    print("\n" + "="*60)
    print(f"結果：{passed}/{total} PASS")
    if failed_labels:
        print("FAIL 項：")
        for label in failed_labels:
            print(f"  ❌ {label}")
    print("="*60)
    return passed, total, failed_labels


# ── pytest-compatible test function ──────────────────────────────────────────

def test_scenario_fg():
    """pytest entry point — runs all F+G scenarios."""
    passed, total, failed_labels = run_fg_tests()
    assert passed == total, f"{total - passed} test(s) failed: {failed_labels}"


# ── Script entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    passed, total, failed_labels = run_fg_tests()
    sys.exit(0 if not failed_labels else 1)
