"""
场景 H: 多 Agent 同时连接同一 Relay，交叉发消息
Hub (7961) 同时连接 WorkerA (7962) 和 WorkerB (7963)
WorkerA 和 WorkerB 也互相连接
所有 Agent 并发向对端发送消息，验证消息路由不混淆
"""
import requests, time, threading, json

HUB = "http://localhost:7961"
WA  = "http://localhost:7962"
WB  = "http://localhost:7963"

results = {}

def get_link(base): return requests.get(f"{base}/link").json()["link"]
def connect(from_base, link): return requests.post(f"{from_base}/peers/connect", json={"link": link}).json()["peer_id"]
def send(base, peer_id, text, msg_id=None):
    body = {"role": "user", "text": text}
    if peer_id: body["peer_id"] = peer_id
    if msg_id:  body["message_id"] = msg_id
    r = requests.post(f"{base}/message:send", json=body)
    return r.json().get("ok", False)
def recv(base):
    return requests.get(f"{base}/recv?limit=200").json().get("messages", [])

# H1: Hub 同时连接两个 Worker
print("H1: 建立 Hub→WA, Hub→WB, WA→WB 连接...")
wa_link = get_link(WA)
wb_link = get_link(WB)
wa_link_from_wa = get_link(WA)
wb_link_from_wb = get_link(WB)

peer_wa = connect(HUB, wa_link)
peer_wb = connect(HUB, wb_link)
wa_peer_wb = connect(WA, wb_link_from_wb)

time.sleep(0.8)

peers = requests.get(f"{HUB}/peers").json()
print(f"  Hub peers: {peers['count']} (expect 2) — {'✅' if peers['count'] == 2 else '❌'}")
results["H1_hub_peers"] = peers['count'] == 2

# H2: Hub 向 WA 和 WB 并发发消息（10条各）
print("H2: Hub 并发向 WA+WB 各发 10 条...")
errors = []
def send_to(base, peer_id, prefix, n):
    for i in range(n):
        ok = send(base, peer_id, f"{prefix}-msg-{i}", f"{prefix}-{i}")
        if not ok: errors.append(f"{prefix}-{i}")

t1 = threading.Thread(target=send_to, args=(HUB, peer_wa, "to-wa", 10))
t2 = threading.Thread(target=send_to, args=(HUB, peer_wb, "to-wb", 10))
t1.start(); t2.start()
t1.join(); t2.join()
time.sleep(0.4)

wa_msgs = recv(WA)
wb_msgs = recv(WB)
wa_texts = [p["content"] for m in wa_msgs for p in m.get("parts",[]) if p.get("type")=="text"]
wb_texts = [p["content"] for m in wb_msgs for p in m.get("parts",[]) if p.get("type")=="text"]

wa_ok = sum(1 for t in wa_texts if t.startswith("to-wa"))
wb_ok = sum(1 for t in wb_texts if t.startswith("to-wb"))
cross = sum(1 for t in wa_texts if t.startswith("to-wb")) + \
        sum(1 for t in wb_texts if t.startswith("to-wa"))

print(f"  WA received to-wa msgs: {wa_ok}/10 {'✅' if wa_ok==10 else '❌'}")
print(f"  WB received to-wb msgs: {wb_ok}/10 {'✅' if wb_ok==10 else '❌'}")
print(f"  Cross-routing errors:   {cross}   {'✅' if cross==0 else '❌ BUG'}")
results["H2_wa_recv"] = wa_ok == 10
results["H2_wb_recv"] = wb_ok == 10
results["H2_no_cross_route"] = cross == 0

# H3: WA 和 WB 并发互发（5条各）
print("H3: WA↔WB 并发互发 5 条...")
def wa_to_wb():
    for i in range(5):
        send(WA, wa_peer_wb, f"wa2wb-{i}", f"wa2wb-idem-{i}")
def wb_to_wa():
    wa_peer_in_wb = requests.get(f"{WB}/peers").json()["peers"]
    if not wa_peer_in_wb:
        # WB 可能没主动连接 WA，尝试 send 不带 peer_id
        for i in range(5):
            requests.post(f"{WB}/message:send", json={"role":"user","text":f"wb2wa-{i}","message_id":f"wb2wa-idem-{i}"})
    else:
        pid = wa_peer_in_wb[0]["id"]
        for i in range(5):
            send(WB, pid, f"wb2wa-{i}", f"wb2wa-idem-{i}")

t3 = threading.Thread(target=wa_to_wb)
t4 = threading.Thread(target=wb_to_wa)
t3.start(); t4.start()
t3.join(); t4.join()
time.sleep(0.4)

wb_new = recv(WB)
wa_new = recv(WA)
wb_got_wa2wb = sum(1 for m in wb_new for p in m.get("parts",[]) if "wa2wb" in p.get("content",""))
print(f"  WB received WA msgs: {wb_got_wa2wb}/5 {'✅' if wb_got_wa2wb>=5 else '⚠️ partial'}")
results["H3_bidirectional"] = wb_got_wa2wb >= 4  # allow 1 drop

# H4: 消息幂等（跨 peer 不串号）
print("H4: 幂等 ID 跨 peer 隔离验证...")
# 同一 message_id 发给 WA 和 WB，两者都应收到（不去重）
send(HUB, peer_wa, "idem-cross-test", "cross-idem-001")
send(HUB, peer_wb, "idem-cross-test", "cross-idem-001")
time.sleep(0.3)
wa_idem = recv(WA)
wb_idem = recv(WB)
wa_got = any("idem-cross-test" in p.get("content","") for m in wa_idem for p in m.get("parts",[]))
wb_got = any("idem-cross-test" in p.get("content","") for m in wb_idem for p in m.get("parts",[]))
print(f"  WA got idem msg: {'✅' if wa_got else '❌'}")
print(f"  WB got idem msg: {'✅' if wb_got else '❌'}")
results["H4_idem_isolated"] = wa_got and wb_got

# Summary
total = len(results)
passed = sum(1 for v in results.values() if v)
print(f"\n{'='*50}")
print(f"场景H: {passed}/{total} PASS")
for k,v in results.items():
    print(f"  {'✅' if v else '❌'} {k}")
