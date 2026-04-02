#!/usr/bin/env python3
"""
场景 B: 团队协作 — Orchestrator → Worker1 + Worker2 任务分发
测试：1) Orchestrator 向两个 Worker 广播任务; 2) 两个 Worker 分别回复; 3) Orchestrator 收到两份回复
"""
import sys, os, time, json, signal, subprocess, threading, requests

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

def start(ws_port, name, wait=4.0):
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(wait)
    return proc, ws_port + 100  # http_port

def stop(proc):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try: proc.wait(timeout=5)
        except: proc.kill()

def get_link(http_port):
    r = requests.get(f"http://127.0.0.1:{http_port}/.well-known/acp.json", timeout=5)
    d = r.json().get("self", r.json())
    token = d.get("token") or r.json().get("token")
    if not token:
        # extract from relay banner via status
        r2 = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=5)
        s = r2.json()
        token = s.get("token") or s.get("relay_token")
    ip = "127.0.0.1"
    ws_port = http_port - 100
    return f"acp://{ip}:{ws_port}/{token}" if token else None

def connect(http_port, link):
    r = requests.post(f"http://127.0.0.1:{http_port}/peers/connect",
                      json={"link": link}, timeout=10)
    return r.json()

def send_msg(http_port, text, peer_id=None):
    body = {"text": text, "role": "agent"}
    if peer_id:
        body["peer_id"] = peer_id
    r = requests.post(f"http://127.0.0.1:{http_port}/message:send",
                      json=body, timeout=10)
    return r.json()

def poll_msgs(http_port, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"http://127.0.0.1:{http_port}/messages", timeout=5)
        msgs = r.json() if isinstance(r.json(), list) else r.json().get("messages", [])
        if msgs:
            return msgs
        time.sleep(0.3)
    return []

def main():
    print("=== 场景 B: 团队协作 ===")
    errors = []

    # Start 3 agents: orchestrator + worker1 + worker2
    print("[1] 启动 Orchestrator + Worker1 + Worker2 ...")
    orch_proc, orch_http = start(18810, "orchestrator")
    w1_proc,   w1_http   = start(18811, "worker1", wait=3.5)
    w2_proc,   w2_http   = start(18812, "worker2", wait=3.5)

    try:
        # Get links
        print("[2] 获取 Worker 链接 ...")
        r1 = requests.get(f"http://127.0.0.1:{w1_http}/status", timeout=5).json()
        r2 = requests.get(f"http://127.0.0.1:{w2_http}/status", timeout=5).json()
        w1_token = r1.get("relay_token") or r1.get("token")
        w2_token = r2.get("relay_token") or r2.get("token")
        w1_link = f"acp://127.0.0.1:18811/{w1_token}" if w1_token else None
        w2_link = f"acp://127.0.0.1:18812/{w2_token}" if w2_token else None

        if not w1_link or not w2_link:
            errors.append(f"无法获取 Worker 链接: w1={w1_token} w2={w2_token}")
        else:
            # Orchestrator connects to both workers
            print("[3] Orchestrator 连接 Worker1 + Worker2 ...")
            c1 = connect(orch_http, w1_link)
            c2 = connect(orch_http, w2_link)
            print(f"  -> W1: {c1.get('ok') or c1.get('status')}")
            print(f"  -> W2: {c2.get('ok') or c2.get('status')}")
            time.sleep(1.5)

            # Get peer IDs from orchestrator status
            peers = requests.get(f"http://127.0.0.1:{orch_http}/peers", timeout=5).json()
            peer_list = peers if isinstance(peers, list) else peers.get("peers", [])
            print(f"  -> Orchestrator 已连接 peers: {len(peer_list)}")

            if len(peer_list) < 2:
                errors.append(f"Orchestrator 应连接 2 个 peer，实际 {len(peer_list)}")
            else:
                # Orchestrator sends task to each worker
                print("[4] Orchestrator 分发任务 ...")
                p1_id = peer_list[0].get("peer_id") or peer_list[0].get("id")
                p2_id = peer_list[1].get("peer_id") or peer_list[1].get("id")
                send_msg(orch_http, "TASK: analyze data chunk A", peer_id=p1_id)
                send_msg(orch_http, "TASK: analyze data chunk B", peer_id=p2_id)
                print("  -> 任务已发送")

                # Workers receive tasks
                time.sleep(1.0)
                w1_msgs = poll_msgs(w1_http, timeout=6)
                w2_msgs = poll_msgs(w2_http, timeout=6)
                print(f"  -> Worker1 收到 {len(w1_msgs)} 条消息")
                print(f"  -> Worker2 收到 {len(w2_msgs)} 条消息")

                if not w1_msgs:
                    errors.append("Worker1 未收到任务消息")
                if not w2_msgs:
                    errors.append("Worker2 未收到任务消息")

                # Workers reply to orchestrator
                if w1_msgs:
                    orch_link = requests.get(f"http://127.0.0.1:{orch_http}/status", timeout=5).json()
                    orch_token = orch_link.get("relay_token") or orch_link.get("token")
                    orch_acp = f"acp://127.0.0.1:18810/{orch_token}" if orch_token else None
                    if orch_acp:
                        connect(w1_http, orch_acp)
                        connect(w2_http, orch_acp)
                        time.sleep(1.0)
                        # Get orch peer_id from worker's peer list (needed since worker has >1 peer)
                        def get_orch_peer_id(worker_http):
                            r = requests.get(f"http://127.0.0.1:{worker_http}/peers", timeout=5)
                            peers = r.json() if isinstance(r.json(), list) else r.json().get("peers", [])
                            for p in peers:
                                pid = p.get("peer_id") or p.get("id", "")
                                if pid != "local":
                                    return pid
                            return None
                        orch_pid_from_w1 = get_orch_peer_id(w1_http)
                        orch_pid_from_w2 = get_orch_peer_id(w2_http)
                        send_msg(w1_http, "RESULT: chunk A done, score=0.92", peer_id=orch_pid_from_w1)
                        send_msg(w2_http, "RESULT: chunk B done, score=0.87", peer_id=orch_pid_from_w2)
                        print("[5] Workers 已回复结果 ...")

                        # Orchestrator collects results
                        time.sleep(1.5)
                        orch_msgs = poll_msgs(orch_http, timeout=6)
                        print(f"  -> Orchestrator 收到 {len(orch_msgs)} 条回复")
                        if len(orch_msgs) < 2:
                            errors.append(f"Orchestrator 应收到 2 条结果，实际 {len(orch_msgs)}")
                        else:
                            def extract_text(m):
                                # Messages from /messages are {direction, raw: {parts, ...}}
                                raw = m.get("raw", m)
                                parts = raw.get("parts", [])
                                if parts:
                                    return " ".join(p.get("content","") for p in parts if p.get("type")=="text")
                                return raw.get("text", raw.get("content", str(raw)))
                            # Only check inbound messages for RESULT
                            inbound = [m for m in orch_msgs if m.get("direction") == "inbound"]
                            texts = [extract_text(m) for m in inbound] if inbound else [extract_text(m) for m in orch_msgs]
                            if not any("RESULT" in t for t in texts):
                                errors.append(f"Orchestrator 未收到 RESULT 消息: {texts}")
                            else:
                                print("  ✅ 团队协作流程完成")

    finally:
        stop(orch_proc)
        stop(w1_proc)
        stop(w2_proc)

    if errors:
        print(f"\n❌ 场景 B 失败: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("\n✅ 场景 B PASS")
        return True

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
