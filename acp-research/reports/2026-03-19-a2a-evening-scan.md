# A2A 情报扫描 — 2026-03-19 晚间

## 扫描时间
2026-03-19 19:25 (Asia/Shanghai)

## A2A 仓库状态 (a2aproject/A2A)

### 最新 commits (近7天)
- `7b900e77` 2026-03-16 — Update CODEOWNERS (#1644)：TSC（Technical Steering Committee）成为项目审查主体
  → 信号：A2A 项目治理正式化，从 Google 内部主导转向社区委员会制，说明项目走向开放协作

### 最新 Issues (活跃)
- **#1379** [Feat] Telemetry — 匿名收集 A2A 跨 SDK 使用数据 (2026-03-18 更新，TSC Review 中)
  → A2A 想建立使用量度量体系（MAU/SDK下载外的真实使用数据）
  → **ACP 参考价值**：我们不需要遥测（P2P 没中心服务器），这反而是差异化优势

### 开放 PR
- **#418** Agent Registrar — 策划代理发现/注册机制 (docs)
  → A2A 在推中心化 Agent 注册表
  → **ACP 反向定位**：我们坚持无中心注册表，P2P 发现 = 直接交换链接

### 最新 Release
- v1.0.0 (2026-03-12)，距今7天，无新 release

## ANP 仓库
- 上次扫描 (2026-03-19 上午)：消息幂等性 + server_seq，已借鉴到 ACP v0.5
- 本轮跳过细扫（无新 release 信号）

## 关键洞察

### 1. A2A 走向重量级治理
CODEOWNERS → TSC，意味着 PR/Issue 流程更重。对我们的意义：
- A2A 功能迭代会越来越慢（委员会审查）
- ACP 的「轻量快迭代」优势窗口期更长

### 2. Telemetry Issue 暴露 A2A 痛点
A2A 需要遥测才能知道自己被用了多少——因为有中心服务器就需要监控。
我们 P2P 架构天然没有这个问题（也没有这个数据），但开源 GitHub stars 是足够的社区信号。

### 3. Agent Registry 方向值得关注
A2A 在做 Agent 发现/注册（PR #418），这是一个合理需求：
「我怎么知道世界上有哪些 Agent 可以对话？」
ACP 的回答：暂不做中心注册。但可以考虑 v0.7 做「去中心化 Agent 名片」——每个 Agent 的 `/.well-known/acp.json` 就是可发现的身份证。

## ACP 下一步建议
- v0.5 继续：Task 状态机 + 消息幂等性（截止 2026-03-26）
- v0.6 预研：去中心化 Agent 发现（基于 .well-known，无注册表）
- 持续关注：A2A TSC 的第一批重大决策（会影响协议方向）
