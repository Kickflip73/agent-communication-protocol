"""
ACP-P2P 群聊 Demo：3个 Agent 无服务器群聊

拓扑：
    Alice（群主）创建群 → 邀请 Bob → 邀请 Charlie
    三人都能互发消息，没有任何中心服务器

运行: python demo_group.py
"""
import asyncio, sys
sys.path.insert(0, "..")
from sdk.acp_p2p import P2PAgent


async def main():
    print("=" * 55)
    print(" ACP-P2P 群聊 Demo — 3 个 Agent，零服务器")
    print("=" * 55)

    received_msgs = {"alice": [], "bob": [], "charlie": []}

    # ── 创建三个 Agent ──────────────────────────────────────────
    alice   = P2PAgent("alice",   port=7810, capabilities=["chat"])
    bob     = P2PAgent("bob",     port=7811, capabilities=["chat"])
    charlie = P2PAgent("charlie", port=7812, capabilities=["chat"])

    # ── 注册群消息处理函数 ─────────────────────────────────────
    @alice.on_group_message
    async def alice_chat(group_id, from_uri, body):
        sender = from_uri.split("/")[-1] if "/" in from_uri else from_uri
        print(f"  [Alice 收到] [{group_id.split(':')[0]}] {sender}: {body.get('text','')}")
        received_msgs["alice"].append(body.get("text",""))

    @bob.on_group_message
    async def bob_chat(group_id, from_uri, body):
        sender = from_uri.split("/")[-1] if "/" in from_uri else from_uri
        print(f"  [Bob   收到] [{group_id.split(':')[0]}] {sender}: {body.get('text','')}")
        received_msgs["bob"].append(body.get("text",""))

    @charlie.on_group_message
    async def charlie_chat(group_id, from_uri, body):
        sender = from_uri.split("/")[-1] if "/" in from_uri else from_uri
        print(f"  [Charlie收到][{group_id.split(':')[0]}] {sender}: {body.get('text','')}")
        received_msgs["charlie"].append(body.get("text",""))

    # ── 启动三个 Agent 服务器 ──────────────────────────────────
    async with alice, bob, charlie:
        print(f"\nAlice   URI: {alice.uri}")
        print(f"Bob     URI: {bob.uri}")
        print(f"Charlie URI: {charlie.uri}")

        # ── Step 1: Alice 创建群 ───────────────────────────────
        print("\n--- Step 1: Alice 创建群 'dev-team' ---")
        group = alice.create_group("dev-team")
        print(f"Group created: {group.group_id[:40]}...")
        print(f"邀请链接: {group.to_join_uri()[:80]}...")

        # ── Step 2: Alice 邀请 Bob ─────────────────────────────
        print("\n--- Step 2: Alice 邀请 Bob ---")
        ok = await alice.invite(group, str(bob.uri))
        print(f"Bob 加入: {'✅' if ok else '❌'}")

        # ── Step 3: Alice 邀请 Charlie ─────────────────────────
        print("\n--- Step 3: Alice 邀请 Charlie ---")
        ok2 = await alice.invite(group, str(charlie.uri))
        print(f"Charlie 加入: {'✅' if ok2 else '❌'}")

        await asyncio.sleep(0.2)

        print(f"\n当前群成员（Alice 视角）: {len(group.members)} 人")
        for m in group.members:
            print(f"  · {m.split('/')[-1]}")

        # ── Step 4: 群聊测试 ──────────────────────────────────
        print("\n--- Step 4: 开始群聊 ---\n")
        await asyncio.sleep(0.1)

        # Alice 发消息
        await alice.group_send(group, {"text": "大家好！我是 Alice，欢迎来到 dev-team 群！"})
        await asyncio.sleep(0.2)

        # Bob 发消息
        bob_group = bob.get_group(group.group_id)
        await bob.group_send(bob_group, {"text": "Hello! Bob 在线，准备好协作了 💪"})
        await asyncio.sleep(0.2)

        # Charlie 发消息
        charlie_group = charlie.get_group(group.group_id)
        await charlie.group_send(charlie_group, {"text": "Charlie 报到！今天有什么任务？"})
        await asyncio.sleep(0.2)

        # Alice 回复
        await alice.group_send(group, {"text": "任务：一起构建 ACP-P2P 协议文档 📝"})
        await asyncio.sleep(0.3)

        # ── Step 5: 点对点仍然可用 ────────────────────────────
        print("\n--- Step 5: 群聊期间点对点仍然正常 ---\n")

        @bob.on_task
        async def bob_task(task, input_data):
            return {"reply": f"Bob 收到私信: '{task}'"}

        result = await alice.send(str(bob.uri), "私信给 Bob", {"message": "下午开个小会？"})
        print(f"  Alice→Bob 私信结果: {result['body']['output']}")

        await asyncio.sleep(0.1)

        # ── 结果统计 ──────────────────────────────────────────
        print("\n" + "=" * 55)
        print(" 测试结果")
        print("=" * 55)
        print(f"  Alice   收到群消息: {len(received_msgs['alice'])} 条")
        print(f"  Bob     收到群消息: {len(received_msgs['bob'])} 条")
        print(f"  Charlie 收到群消息: {len(received_msgs['charlie'])} 条")
        total = sum(len(v) for v in received_msgs.values())
        print(f"  总消息分发: {total} 条")
        print(f"\n✅ 零服务器，3 个 Agent 完成群聊通信！")


if __name__ == "__main__":
    asyncio.run(main())
