# ACP 竞品情报扫描 — 2026-03-20 Morning

扫描时间：2026-03-20 09:45 CST  
贾维斯自动生成

---

## A2A 动态

**最新 commit**：`7b900e77`（2026-03-16，CODEOWNERS → TSC，项目治理正式化）

无新代码变更。活跃 issues 关键更新：

### PR #1619 — 自定义协议绑定文档（与 ACP 高度相关）
- 状态：open，最新更新 2026-03-18
- 内容：新增 `docs/topics/custom-protocol-bindings.md` + `extension-and-binding-governance.md`
- 关键区分（A2A 的术语）：
  - **Protocol Binding**：完整替换底层传输（HTTP→gRPC/MQTT/...），需声明数据类型映射、认证方案等
  - **Extension**：在现有协议上扩展字段，不替换传输层
  - SDK SHOULD 实现官方 Protocol Binding，MAY 实现 Extension
- **ACP 启示**：我们的 spec/transports.md 重组也应明确这个区分，把 P2P WS 和 HTTP Relay 定义为两种 Protocol Binding，message_id/server_seq 等定义为 Extension-compatible 字段

### Issue #1575 — Agent 身份、委托、权限执行
- 状态：open，社区讨论阶段
- 与 ACP 无关（企业级身份框架，我们不做）

### Issue #1379 — 遥测/匿名使用统计
- 状态：TSC Review 中
- 与 ACP 无关（P2P 架构，无需遥测，这是差异化优势）

**战略判断**：A2A 继续向企业级演进（TSC 治理、DID 身份、遥测）。我们快迭代窗口期不变。

---

## ANP 动态

**最新 commit**：`761087d5`（2026-03-05，`handle feature`）

### WNS — WBA Name Space（Handle 命名空间）⭐ 新特性
- ANP 新增 Handle 规范：`alice.example.com` 格式的人类可读 Agent 标识符
- 解析流程：Handle → did:wba DID → DID Document → Agent 服务端点
- 设计目标：可读性（vs DID 字符串）+ 域名无关 + 双向绑定 + 最小化设计
- 协议状态：草案

**ACP 启示（v0.7 候选）**：
- ANP 的 Handle 解决了"如何找到对方 Agent"的问题
- ACP 目前靠 acp:// 链接传递，需要人工复制粘贴，不优雅
- v0.7 能力发现中可以考虑类似方案：`@jarvis.stark.dev` → 解析为 acp://IP:PORT/TOKEN
- 不需要实现完整 DID，可以简化为 DNS TXT 记录：`_acp.stark.dev TXT "acp://..."`

---

## 核心结论

| 项目 | 本周动态 | ACP 行动项 |
|------|---------|-----------|
| A2A | 无代码更新，治理重构中 | #1619 Protocol Binding 区分 → 指导 spec/transports.md 重组 |
| ANP | Handle/WNS 命名空间草案 | v0.7 候选：DNS TXT-based Agent 发现（轻量 Handle 替代方案） |

---

## v0.6 剩余任务状态

| 任务 | 状态 |
|------|------|
| 最小接入协议规范 (spec/v0.6-minimal-agent.md) | ✅ 完成 |
| 多 session peer registry | ✅ 完成 |
| 标准化错误码 + failed_message_id | ✅ 完成 |
| spec/error-codes.md | ✅ 完成 |
| spec/transports.md 重组（Protocol Binding vs Extension）| ⏳ 本次研究提供了 A2A #1619 的输入 |
| Python mini-SDK (pip install acp-relay) | ⏳ 待开发 |

