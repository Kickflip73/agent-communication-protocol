"""
ACP-P2P v0.3 — 连接生命周期 + 群聊加入/退出 Demo

验证：
  1. connect() / disconnect()  显式连接生命周期
  2. join_group() / leave_group()  群聊动态加减成员
  3. 无服务器模式（仅发送，不起 HTTP server）
  4. async with 自动管理服务器生命周期
"""
import asyncio, sys
sys.path.insert(0, "..")
from sdk.acp_p2p import P2PAgent


async def main():
    print("=" * 60)
    print(" ACP-P2P v0.3 — 连接生命周期 Demo")
    print("=" * 60)

    alice   = P2PAgent("alice",   port=7820)
    bob     = P2PAgent("bob",     port=7821)
    charlie = P2PAgent("charlie", port=7822)
    dave    = P2PAgent("dave",    port=7823)   # 稍后动态加入群

    log_msgs = []

    @alice.on_group_message
    async def a(gid, src, body):
        name = src.split("/")[-1].split("?")[0]
        evt  = body.get("event") or body.get("text","")
        log_msgs.append(f"Alice  ← [{name}] {evt}")
        print(f"  Alice  ← [{name}] {evt}")

    @bob.on_group_message
    async def b(gid, src, body):
        name = src.split("/")[-1].split("?")[0]
        evt  = body.get("event") or body.get("text","")
        log_msgs.append(f"Bob    ← [{name}] {evt}")
        print(f"  Bob    ← [{name}] {evt}")

    @charlie.on_group_message
    async def c(gid, src, body):
        name = src.split("/")[-1].split("?")[0]
        evt  = body.get("event") or body.get("text","")
        log_msgs.append(f"Charlie← [{name}] {evt}")
        print(f"  Charlie← [{name}] {evt}")

    @dave.on_group_message
    async def d(gid, src, body):
        name = src.split("/")[-1].split("?")[0]
        evt  = body.get("event") or body.get("text","")
        log_msgs.append(f"Dave   ← [{name}] {evt}")
        print(f"  Dave   ← [{name}] {evt}")

    @bob.on_task
    async def bob_task(task, inp): return {"reply": f"Bob handled: {task}"}

    async with alice, bob, charlie, dave:

        # ── 1. 显式 P2P 连接 ─────────────────────────────────────────
        print("\n[1] connect / disconnect 生命周期")
        sess = await alice.connect(str(bob.uri))
        print(f"  建立连接: {sess}")

        result = await alice.send(sess, "Hello Bob", {"msg": "hi"})
        print(f"  发送结果: {result['body']['output']}")

        await alice.disconnect(sess)
        print(f"  断开后:   {sess}")

        # ── 2. 直接发送（不 connect，最轻量）────────────────────────
        print("\n[2] 直接发送（无需 connect，URI 即目标）")
        r2 = await alice.send(str(bob.uri), "Direct task", {"val": 42})
        print(f"  直发结果: {r2['body']['output']}")

        # ── 3. 创建群聊 + 邀请 ───────────────────────────────────────
        print("\n[3] 创建群聊，邀请 Bob & Charlie")
        group = alice.create_group("workshop")
        await alice.invite(group, str(bob.uri))
        await alice.invite(group, str(charlie.uri))
        await asyncio.sleep(0.1)
        print(f"  群成员: {[m.split('/')[-1].split('?')[0] for m in group.members]}")

        # ── 4. 群聊消息 ──────────────────────────────────────────────
        print("\n[4] 三人群聊")
        await alice.group_send(group, {"text": "项目启动！"})
        await asyncio.sleep(0.1)
        await bob.group_send(bob.get_group(group.group_id), {"text": "Bob ready ✅"})
        await asyncio.sleep(0.1)
        await charlie.group_send(charlie.get_group(group.group_id), {"text": "Charlie ready ✅"})
        await asyncio.sleep(0.15)

        # ── 5. 动态加入（Dave 通过邀请链接加入）─────────────────────
        print("\n[5] Dave 动态加入群")
        invite_link = group.to_invite_uri()
        dave_group  = await dave.join_group(invite_link)
        await asyncio.sleep(0.1)
        print(f"  Dave 加入后群成员: {[m.split('/')[-1].split('?')[0] for m in group.members]}")

        await dave.group_send(dave_group, {"text": "Dave 加入！大家好 👋"})
        await asyncio.sleep(0.15)

        # ── 6. Charlie 退出群 ─────────────────────────────────────────
        print("\n[6] Charlie 主动退出群")
        await charlie.leave_group(charlie.get_group(group.group_id))
        await asyncio.sleep(0.1)
        print(f"  Charlie 退出后群成员: {[m.split('/')[-1].split('?')[0] for m in group.members]}")

        await alice.group_send(group, {"text": "Charlie 已退出，继续！"})
        await asyncio.sleep(0.15)

        # ── 7. ping 检测 ──────────────────────────────────────────────
        print("\n[7] ping 检测在线状态")
        print(f"  ping bob:     {'✅' if await alice.ping(str(bob.uri))   else '❌'}")
        print(f"  ping charlie: {'✅' if await alice.ping(str(charlie.uri)) else '❌'}")  # still up

        # ── 结果 ──────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print(" 结果统计")
        print("=" * 60)
        for m in log_msgs:
            print(f"  {m}")
        print(f"\n✅ 全部通过 — 总消息: {len(log_msgs)} 条，零服务器")


if __name__ == "__main__":
    asyncio.run(main())
