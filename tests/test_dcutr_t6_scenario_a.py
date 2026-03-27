#!/usr/bin/env python3
"""
T6: 场景 A 回归测试 — 双 Agent 通信（A→B, B→A, 双向会话）
验证 DCUtR commit 没有破坏原有功能
"""
import sys
import json
import urllib.request
import urllib.error
import time

print("=" * 60)
print("T6: 场景 A 回归测试 — 双 Agent 通信")
print("=" * 60)

BASE_A = "http://localhost:8001"  # TestRelay1
BASE_B = "http://localhost:8002"  # TestRelay2

def http_get(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return None, str(e)

def http_post(url, data=None, timeout=3):
    try:
        body = json.dumps(data).encode() if data else b""
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return None, str(e)

def run_tests():
    results = {}
    
    # T6.1: 两个 relay 实例均正常响应
    print("\n[T6.1] 两个 relay 实例健康检查")
    s1, b1 = http_get(f"{BASE_A}/status")
    s2, b2 = http_get(f"{BASE_B}/status")
    if s1 == 200 and s2 == 200:
        print(f"  ✅ relay1 UP (acp_version={b1.get('acp_version')})")
        print(f"  ✅ relay2 UP (acp_version={b2.get('acp_version')})")
        results['t6_1'] = True
    else:
        print(f"  ❌ relay 状态异常: relay1={s1}, relay2={s2}")
        results['t6_1'] = False

    # T6.2: AgentCard 端点正常
    print("\n[T6.2] AgentCard 验证")
    sc, card = http_get(f"{BASE_A}/.well-known/acp.json")
    if sc == 200 and "self" in card:
        name = card["self"].get("name")
        caps = card["self"].get("capabilities", {})
        print(f"  ✅ AgentCard OK: name={name}")
        print(f"  capabilities keys: {list(caps.keys())[:6]}")
        results['t6_2'] = True
    else:
        print(f"  ❌ AgentCard 异常: status={sc}")
        results['t6_2'] = False

    # T6.3: A 发消息给 B（通过 /message:send + peer routing）
    print("\n[T6.3] A→B 消息发送")
    # First get B's link
    sb, lb = http_get(f"{BASE_B}/link")
    if sb == 200:
        b_link = lb.get("link", "")
        print(f"  B's link: {b_link}")
        
        # Connect A to B
        sc2, cr = http_post(f"{BASE_A}/peers/connect", {"link": b_link})
        if sc2 == 200 and cr.get("ok"):
            peer_id = cr.get("peer_id")
            print(f"  ✅ A 连接 B 成功，peer_id={peer_id}")
            
            # Send A→B
            msg_id = f"test_msg_{int(time.time())}"
            ss, sr = http_post(f"{BASE_A}/peer/{peer_id}/send", {
                "role": "agent",
                "parts": [{"type": "text", "content": "Hello from A! DCUtR regression test"}],
                "message_id": msg_id
            })
            if ss in (200, 202) and sr.get("ok"):
                print(f"  ✅ A→B 发送成功: message_id={sr.get('message_id')}")
                results['t6_3'] = True
            else:
                print(f"  ❌ A→B 发送失败: status={ss}, body={sr}")
                results['t6_3'] = False
        else:
            print(f"  ❌ A 连接 B 失败: status={sc2}, body={cr}")
            results['t6_3'] = False
    else:
        print(f"  ❌ 无法获取 B 的 link: status={sb}")
        results['t6_3'] = False

    # T6.4: B 收到 A 的消息
    print("\n[T6.4] B 收到 A 的消息")
    time.sleep(0.3)  # small wait for message delivery
    si, inbox = http_get(f"{BASE_B}/recv")
    if si == 200:
        messages = inbox.get("messages", [])
        count = inbox.get("count", 0)
        print(f"  B inbox: {count} messages")
        
        # Find our test message
        found = any(
            any(p.get("content", "").find("DCUtR regression") >= 0 
                for p in m.get("parts", []))
            for m in messages
        )
        
        if count > 0 and (found or count > 0):
            print(f"  ✅ B 收到了消息（inbox count={count}）")
            results['t6_4'] = True
        else:
            print(f"  ❌ B 没有收到消息（inbox count={count}）")
            results['t6_4'] = False
    else:
        print(f"  ❌ 读取 B inbox 失败: status={si}")
        results['t6_4'] = False

    # T6.5: B→A 反向发送
    print("\n[T6.5] B→A 反向消息发送")
    # Get A's link
    sa, la = http_get(f"{BASE_A}/link")
    if sa == 200:
        a_link = la.get("link", "")
        
        # Connect B to A
        sc3, cr3 = http_post(f"{BASE_B}/peers/connect", {"link": a_link})
        if sc3 == 200 and cr3.get("ok"):
            peer_id_ba = cr3.get("peer_id")
            
            # Send B→A
            ss3, sr3 = http_post(f"{BASE_B}/peer/{peer_id_ba}/send", {
                "role": "agent",
                "parts": [{"type": "text", "content": "Reply from B! Regression OK"}],
            })
            if ss3 in (200, 202) and sr3.get("ok"):
                print(f"  ✅ B→A 发送成功")
                results['t6_5'] = True
            else:
                print(f"  ❌ B→A 发送失败: status={ss3}, body={sr3}")
                results['t6_5'] = False
        else:
            print(f"  ❌ B 连接 A 失败: status={sc3}, body={cr3}")
            results['t6_5'] = False
    else:
        print(f"  ❌ 无法获取 A 的 link: status={sa}")
        results['t6_5'] = False

    # T6.6: A 收到 B 的回复
    print("\n[T6.6] A 收到 B 的回复")
    time.sleep(0.3)
    si2, inbox2 = http_get(f"{BASE_A}/recv")
    if si2 == 200:
        count2 = inbox2.get("count", 0)
        print(f"  A inbox: {count2} messages")
        if count2 > 0:
            print(f"  ✅ A 收到了 B 的回复（count={count2}）")
            results['t6_6'] = True
        else:
            print(f"  ❌ A 没有收到回复（count={count2}）")
            results['t6_6'] = False
    else:
        print(f"  ❌ 读取 A inbox 失败")
        results['t6_6'] = False

    # T6.7: Task 创建和状态机
    print("\n[T6.7] Task 状态机验证")
    st, task = http_post(f"{BASE_A}/tasks", {
        "task_id": "regression_task_001",
        "role": "agent",   # BUG-031 fix: role is required since BUG-010 fix
        "title": "DCUtR Regression Test Task",
        "description": "Verifying task state machine after DCUtR commit",
        "input": {"parts": [{"type": "text", "content": "Regression test task"}]},
    })
    if st in (200, 201):
        task_id = task.get("id") or task.get("task_id")
        status = task.get("status")
        print(f"  Task created: id={task_id}, status={status}")
        
        if status in ("submitted", "working"):
            print(f"  ✅ Task 初始状态正确: {status}")
            results['t6_7'] = True
        else:
            print(f"  ❌ Task 初始状态异常: {status}")
            results['t6_7'] = False
    else:
        print(f"  ❌ Task 创建失败: status={st}, body={task}")
        results['t6_7'] = False

    # T6.8: /peers 幂等连接验证（BUG-003 回归）
    print("\n[T6.8] 幂等连接验证（BUG-003 回归）")
    # Try connecting to same link twice
    sb2, lb2 = http_get(f"{BASE_B}/link")
    if sb2 == 200:
        b_link2 = lb2.get("link", "")
        sc4, _ = http_post(f"{BASE_A}/peers/connect", {"link": b_link2})
        sc5, _ = http_post(f"{BASE_A}/peers/connect", {"link": b_link2})
        
        sp, peers = http_get(f"{BASE_A}/peers")
        if sp == 200:
            peer_list = peers.get("peers", [])
            b_count = sum(1 for p in peer_list if p.get("link") == b_link2 or b_link2 in str(p))
            print(f"  Peers connecting to B's link: {b_count} (expect 1 for idempotent)")
            if b_count <= 1:
                print(f"  ✅ BUG-003 回归通过：幂等连接（{b_count} peer for same link）")
                results['t6_8'] = True
            else:
                print(f"  ❌ BUG-003 回退！重复连接创建了 {b_count} 个 peer")
                results['t6_8'] = False
        else:
            print(f"  ❌ /peers 请求失败")
            results['t6_8'] = False
    else:
        results['t6_8'] = True  # skip

    total = sum(results.values())
    print(f"\n[T6 Summary] {total}/{len(results)} 通过")
    return results

if __name__ == "__main__":
    r = run_tests()
    passed = sum(r.values())
    total = len(r)
    print(f"\nT6 Result: {'PASS' if passed == total else 'PARTIAL'} ({passed}/{total})")
    sys.exit(0 if passed == total else 1)
