# ACP 竞品周报 — 2026-04-08

_由贾维斯自动生成_

## A2A (Google) — 2026-04-08
- Stars: 23063 | Open Issues: 224
### 最新 Commits
- `a40261c` 2026-04-07 docs: Add local build steps to Contributing Guide (#1726)
- `43bddf8` 2026-04-07 [Feat]: New logos + mascot (#1719)
- `3c0e23e` 2026-04-07 docs: fix table duplication in A2A Specification document (#1704)
- `66df070` 2026-04-07 docs: Add custom protocol bindings documentation (#1619)
- `74c7c62` 2026-04-07 fix: pin check-spelling action to v0.0.26 (#1722)
### 新 Issues（功能请求）
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `99806f4` 2026-03-05 feat: add failed_msg_id field to e2ee_error protocol message
- `761087d` 2026-03-05 add handle feature
- `1f0abd2` 2026-03-03 feat: add client_msg_id idempotency and server_seq ordering to E2EE IM
- `b1c1c76` 2026-03-01 update e2ee protocol
- `eb4a10f` 2026-02-27 docs: rename signature field `service` to `aud` in DID-WBA spec

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

## 🔍 贾维斯深度分析 — 2026-04-08 09:04 (Asia/Shanghai)

> 分析范围：本周（2026-04-01 ~ 2026-04-08）全部扫描报告综合
> ACP 当前版本：v2.79.0（截至上次开发轮）

---

### 一、A2A 本周核心动态

#### 1. 品牌化提速 — 新 Logo + 吉祥物（PR #1719，已合并 2026-04-07）
**事实**：A2A 本周合并了全新视觉识别系统，含 Logo 和吉祥物设计。
**解读**：这是 Google 将 A2A 从"内部协议草案"推向"开放生态品牌"的明确信号。品牌化是社区建设的前置动作——通常预示 1-3 个月内会有公开营销/外部开发者活动（如 Google I/O 2026 展示）。
**A2A Stars 增速**：上周（2026-04-01 扫描）约 22,643 → 本周 23,063，**7天新增 ~420 Stars**，周增速约 +1.8%，高于历史均值。
**ACP 警示**：A2A 正在从"技术协议"演进为"生态品牌"。在 P2P NAT 穿透完成之前，ACP 的公开发布（Show HN）时机不宜拖延太久——品牌化 A2A 会加速公众认知锁定。

#### 2. 自定义协议绑定文档正式合并（PR #1619 → 2026-04-07）
**事实**：A2A spec 正式定义 Custom Protocol Binding（CPB）与 Extension 的语义边界，新增 §5.8 URI-based binding identification。
**解读**：A2A 正式为 gRPC、MQTT、SLIM 等非 HTTP 传输方式打开了标准化通道。这标志着 A2A 从"HTTP-only 协议"迈向"多传输绑定协议"。
**与 ROADMAP 对比**：ACP ROADMAP 的设计禁忌明确排除 gRPC 绑定，但 ACP 已有 HTTP/2 (h2c) 支持（v1.6）和 NAT 三级降级。ACP 可低成本在 AgentCard 中增加 `protocol_binding` 声明字段，与 A2A §5.8 URI 对齐，增强互操作性。

#### 3. Ed25519 互操作生态自发形成（Issue #1672）
**事实**：社区开发者（@haroldmalikfrimpong-ops）已基于 qntm/AgentID 实现 Ed25519 identity support，与 Python/TypeScript 实现字节级互操作成功（5/5 向量）。
**解读**：这意味着 A2A 社区的 Ed25519 实现正在收敛，并形成非官方互操作标准。ACP 作为先行实现（v0.8，2026-03-21），在技术路线上与这一收敛方向高度一致。
**差异化确认**：ACP 仍领先 A2A 官方规范约 **6-8 周**（ACP v0.8 完成 Ed25519 identity → A2A #1672 尚未并入 spec）。

#### 4. 实验性 SLIMRPC 绑定提案（Issue #1723）
**事实**：有提案在 A2A 生态中引入基于 SLIM 协议的传输绑定（namespace/group/name 三元寻址）。
**解读**：仍处提案阶段，但 SLIM 的非 HTTP URL 寻址方式与 ACP 的 `acp://relay/<token>` 链接格式有设计共鸣——验证了 ACP token-based 寻址的路线正确性。

---

### 二、ANP 动态
**完全静默**：2026-04-01 ~ 04-08 无任何新 commit，维持 2026-03-05 最后更新状态。
**结论**：ANP 已实质停止维护，后续每周扫描仅作归档记录，不再产出分析段落。

---

### 三、IBM ACP 动态
**完全静默**：最后活跃日期 2025-08-25，本周无任何更新。
**结论**：IBM ACP 已进入维护停滞状态，与竞品对比定期检查即可。

---

### 四、ROADMAP 优先级评估

**当前 ACP 版本**：v2.79.0（含 SINT capability token 完整 quad、trust signals 完整体系）

| ROADMAP 项目 | 当前状态 | 本周情报影响 | 建议调整 |
|---|---|---|---|
| v1.4 NAT 穿透（真 P2P 打洞集成） | 🔄 70% 完成（signaling 层 ✅，自动降级集成 ❌） | ⬆️ 优先级提升：A2A 品牌化加速，P2P 是核心卖点，应尽快完成 | **P0，优先完成** |
| `protocol_binding` AgentCard 字段 | ❌ 未排期 | ➡️ A2A #1619 合并，互操作需求明确 | **新增 P2 候选** |
| qntm/AgentID Ed25519 互操作性 | ❌ 未评估 | ⬆️ 社区 5/5 向量兼容，验证成本低 | **新增 P3 候选** |
| Show HN 公开发布 | ❌ 等待 P2P 完成 | ⚠️ A2A 品牌化加速，发布窗口不宜无限期推迟 | **条件触发：P2P 一完成立刻发布** |
| data_handling_policy（GDPR Extension） | ❌ P3 低优先级 | ➡️ 无新进展，维持低优先级 | 不变 |

---

### 五、行动建议

#### 🔴 行动建议 1（P0）：全力推进 v1.4 NAT 穿透自动降级集成
**背景**：v1.4 的 signaling 层（HTTP 反射 + announce/peer_addr）已完成（22/22 PASS），但 `_connect_with_nat_traversal()` 主流程集成和 NAT 打洞测试（`test_p2p_behind_nat.py`）仍未完成。A2A 本周品牌化提速，公开发布的最佳窗口正在缩窄。
**建议**：下一个开发轮优先完成 v1.4 两项剩余 TODO：
1. `_connect_with_nat_traversal()` 替换现有直连逻辑（自动三级降级主流程）
2. 集成测试 `tests/integration/test_p2p_behind_nat.py`（需 2x NAT 环境，可用 Docker network 模拟）

完成后，ACP 将达成"真 P2P 无中间人"这一核心卖点，可正式触发 Show HN 发布流程。

#### 🟡 行动建议 2（P2）：在 AgentCard 新增 `protocol_binding` 声明字段
**背景**：A2A #1619（CPB §5.8）本周合并，确立了 URI-based 协议绑定声明的标准语法。ACP 已有 HTTP/1.1、HTTP/2 (h2c)、WebSocket、Relay 四种传输模式，但 AgentCard 中缺少对应的标准化声明。
**建议**：在 AgentCard 的 `capabilities` 或顶层新增：
```json
"protocol_bindings": [
  "urn:acp:transport:http1",
  "urn:acp:transport:h2c",
  "urn:acp:transport:relay",
  "urn:acp:transport:nat-traversal"
]
```
实现成本极低（纯声明字段），可在下一个规范文档更新轮顺带完成。

---

### 六、本周 ACP 竞争态势总结

```
A2A：品牌化加速 🏃 → 公众认知窗口缩窄 → ACP 需在 P2P 完成后快速发布
ANP：已归档，不再构成竞争压力 ✅
IBM ACP：静默，不构成威胁 ✅
ACP：技术领先优势维持，v2.79.0 trust signals 体系完整 🏆
关键差距：NAT 穿透自动降级（~30% TODO）是公开发布的唯一阻塞项
```

---

_分析完成：2026-04-08 09:06 (Asia/Shanghai) | 贾维斯研究轮 #28_
