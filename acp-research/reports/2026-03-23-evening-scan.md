# ACP Research Scan — 2026-03-23 Evening

## A2A 生態動態

**最新 commit**: `7b900e7` (2026-03-16) — 無新代碼變更，本週無更新

**今日重要 Issue（2026-03-23）**:

### Issue #1667：Heartbeat 型 Agent 的可用性元數據與離線優先 Task 處理

**背景**: A2A 社群提出，spec 假設 agent 是持久運行的服務，但現實中大量 agent 是心跳/cron 型（定時喚醒，睡眠期間無服務端）。提問者提出需要：
- Agent 在 Card 中聲明「我是心跳型，下次喚醒時間是...」
- Client 可以知道 agent 是否在線，或何時可用
- Offline-first Task 緩衝機制

**ACP 狀態**: **ACP v1.2 已實現 `availability` 元數據（2026-03-23 之前）**，包含：
- `schedule.type`: `heartbeat | continuous | on_demand`
- `schedule.interval_seconds`: 喚醒週期
- `schedule.next_wake_utc`: 預計下次喚醒時間
- `status.online`: 當前是否在線
- `status.accepts_tasks`: 是否接受新任務

**戰略意義**: A2A 還在討論這個問題，ACP 已有實現。這是 ACP 的先發優勢。
**行動**: 在 ACP README 中突出 `availability` 特性，可作為差異化賣點。

---

### Issue #1672：Agent Card 身份驗證提案

**背景**: A2A 目前的 Agent Card 沒有密碼學身份驗證，依賴傳輸層 HTTPS/OAuth。提案提出在協議層加入 Agent 身份驗證（Ed25519 / DID）。

**ACP 狀態**: **ACP v0.8 已實現 Ed25519 身份驗證，v1.3 已實現 did:acp: DID 標識符**，包含：
- `--identity` 啟動選項，生成 Ed25519 keypair
- AgentCard 包含 `identity.public_key`（base64url）
- `did:acp:<base58btc_pubkey>` 穩定 DID 標識符
- `/.well-known/did.json` W3C DID Document

**戰略意義**: 同上，ACP 已在 A2A 尚未解決的問題上有實現。
**行動**: 在 ACP README 加「vs A2A」對比表，突出 ACP 已實現而 A2A 仍在討論的特性。

---

## ANP 動態

無新 commit（最後更新 2026-03-05）。

---

## 競品對比快照（截至 2026-03-23）

| 特性 | A2A | ANP | ACP |
|------|-----|-----|-----|
| Heartbeat Agent 可用性元數據 | ❌（Issue #1667，討論中）| ❌ | ✅ v1.2 |
| Agent 身份驗證（Ed25519）| ❌（Issue #1672，提案中）| 部分（E2EE）| ✅ v0.8 |
| DID 標識符 | ❌ | ❌ | ✅ v1.3 |
| P2P 無中心服務器 | ❌（中心化 registry）| ❌ | ✅ 核心設計 |
| 消息幂等性（client_msg_id）| ✅ | ✅ | ✅ v0.5 |
| SSE 流式事件 | ✅ | ❌ | ✅ |
| NAT 穿透 / Relay 降級 | ❌ | ❌ | ✅ v1.0 |

---

## 行動項

1. **README 更新**（下次文档轮）：加「ACP vs A2A」對比表，突出 availability 和 identity 已實現
2. **關注 Issue #1667 #1672**：若 A2A 設計出方案，評估是否需要同步到 ACP spec
3. **可考慮在 A2A Issues 留言**：介紹 ACP 的實現方案（增加曝光度）

*J.A.R.V.I.S. — 2026-03-23 19:xx*
