# 竞品研究报告 — 2026-03-21（研究轮）

扫描时间：2026-03-21 10:43 CST
来源：github.com/google-a2a/a2a-python（issues #868–#883）

---

## 摘要

本轮无新 commit（A2A 最后活动：2026-03-18），但近期 Issues 暴露了三个高价值信号，
均指向 A2A SDK 在企业复杂度下的工程负债。对 ACP 的启示正面。

---

## 发现 1 — 隐式 SQLAlchemy 依赖（#883，2026-03-20）

### 现象
A2A v1.0.0-alpha.0：`from a2a.server.request_handlers import RequestHandler`
会悄悄引入 `sqlalchemy`，即使用户根本没用 SQL 功能。
原因：`request_handler` → `response_helpers` → `a2a.compat.v0_3.conversions` → `a2a.server.models` → `sqlalchemy`。

### 影响
用户必须安装 `a2a-sdk[http-server,sql]`（含 DB 驱动），
否则在任何地方 import 基础请求处理都会抛 `ModuleNotFoundError`。

### ACP 启示 ✅ 对我们有利
ACP 从设计上严格遵循「零外部依赖」原则——本轮刚完成的 AsyncRelayClient 重写
（去掉 aiohttp）正是同一原则的体现。这个 issue 是我们「stdlib-only」差异化的
活生生反证：企业级 SDK 的模块耦合会让依赖悄悄扩散，开发者无从控制。

**行动项**：在 `docs/cli-reference.md` 或 README 中加一段
「Zero-dependency promise」，明确声明 `acp_relay.py` 及 Python SDK 的运行时
只依赖 stdlib，并列出可选 extras（`websockets`、`cryptography`）。

---

## 发现 2 — 必填字段未校验（#876，2026-03-19）

### 现象
A2A `SendMessage` 端点：`messageId`、`role`、`parts` 均为 proto REQUIRED，
但实际 SDK 对缺失这三个字段的请求一律放行，不返回 4xx，悄悄接受无效消息。

### ACP 现状对比
我们在 `_http_post` 和 `/message:send` 处理器中也缺乏对 `message_id` / `role`
的严格校验——目前只在 Python SDK 的 `send()` 方法层做了 ValueError，
但 HTTP 层（任何 curl 调用）可以绕过。

**行动项**（v0.9 P1）：
在 `acp_relay.py` 的 `/message:send` 处理器中加入服务端校验：
- `role` 缺失或非 `user`/`agent` → `{"ok": false, "error_code": "ERR_INVALID_REQUEST", "error": "missing required field: role"}`
- `text` 和 `parts` 同时缺失 → 同上
- 加入 `tests/compat/` 测试用例

---

## 发现 3 — RetryTransport / 并发架构重构（#871 + #869，2026-03-19）

### 现象
- #871：A2A 的 transport 层对瞬态故障（超时、429、503）立即抛异常，
  无内置重试，每个调用方自行实现退避逻辑，高度重复且容易出错。
  提案：`RetryTransport` 包装器，内置指数退避 + `Retry-After` header 解析。
- #869：AgentExecutor 内部存在并发隐患（`cancel()` 无法等待 `execute()` 完成），
  计划渐进式重构并发模型。

### ACP 启示 🔮 中期机会
目前 ACP 客户端对网络抖动的处理依赖使用者自己 try/except。
考虑在 Python SDK 的 `_http_get` / `_http_post` helpers 中加入可选的
内置重试（`max_retries=3, backoff=0.5`），但**默认关闭**，保持零配置体验。

**行动项**（v0.9 P2，可选）：
```python
# RelayClient 构造器
RelayClient(base_url, timeout=10.0, max_retries=0, retry_backoff=0.5)
```
当 `max_retries > 0` 且响应为 429/502/503 时自动重试。不影响默认路径。

---

## 本轮无新内容（跳过）
- A2A 最新 commit（4ebbb2eb，2026-03-18）：README 加 Vertex task store 条目，纯文档，无协议变化
- ANP：2026-03-05 以来无新 commits

---

## 行动项汇总

| 优先级 | 内容 | 目标版本 |
|--------|------|---------|
| P1 | README「Zero-dependency promise」章节 | v0.9 |
| P1 | `/message:send` 服务端必填字段校验 + compat 测试 | v0.9 |
| P2 | `RelayClient` 可选内置重试（默认 off） | v0.9 |
