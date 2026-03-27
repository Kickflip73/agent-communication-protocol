# ACP 研究掃描報告 — 2026-03-23 晚間

## 掃描結果

### A2A (google/A2A)
- **最新 commit**: `7b900e77`（2026-03-16）— 無新動態
- **值得關注的 Issues（全部更新於 2026-03-23）**:

#### #1672 — Proposal: Agent Identity Verification for Agent Cards
**方向**: 在 AgentCard 加 `verifiedIdentity` 字段，依賴外部 CA（getagentid.dev）做 ECDSA P-256 證書驗證

**對 ACP 的意義**:
- A2A 社群正在「追」我們已實現的能力（ACP v0.8 Ed25519 + v1.3 did:acp:）
- **差異化優勢**: ACP 的 `did:acp:` 是自簽名去中心化，不依賴任何外部 CA——更符合 P2P 精神
- 可以在 Show HN 和文檔中重點強調：「當 A2A 還在討論身份驗證方案時，ACP 已有去中心化 DID 實現」

#### #1667 — Heartbeat-based agents: availability metadata and offline-first task handling
**方向**: AgentCard 缺少 `scheduleType`/`nextActiveAt`/`taskLatencyMaxSeconds` 等調度元數據字段

**對 ACP 的意義**:
- **ACP v1.2 已完整解決此問題**（`availability` 字段：`scheduleType`, `next_active_at`, `task_latency_max_seconds`）
- A2A 的用戶正在為沒有此功能而苦惱，我們可以作為有力的對比案例
- 建議：在 README 對比表新增一行「Heartbeat agent support」，ACP: ✅ v1.2，A2A: ❌ 討論中

#### #1549 — Bidirectional streaming over gRPC
**方向**: A2A 計劃支持 gRPC 雙向流

**對 ACP 的意義**:
- 這是 ACP 明確不做的（架構禁忌：gRPC）——差異化定位確認
- A2A 往重型企業方向走，ACP 繼續輕量 P2P 路線

#### #1575 — Agent identity, delegation, and enforcement
**方向**: 更複雜的身份委託鏈

**對 ACP 的意義**:
- 超出 ACP 當前範圍（個人/小團隊場景不需要 delegation chain）
- 長期可以參考，但現在不優先

### ANP (agent-network-protocol/AgentNetworkProtocol)
- **最新 commit**: `99806f45`（2026-03-05）— 無新動態

---

## 戰略建議

### 1. 立即行動：README 對比表補充
在 `README.md` Why ACP 對比表增加兩行：

| 特性 | A2A (Google) | ACP |
|------|-------------|-----|
| Agent 身份驗證 | 外部 CA 依賴（討論中）| ✅ did:acp: 去中心化自簽名（v1.3）|
| 心跳 Agent 支持 | ❌ 無（#1667 討論中）| ✅ availability 元數據（v1.2）|

### 2. Show HN 草稿強化點
- 增加「我們已解決 A2A 社群正在討論的兩個問題」章節
- 具體引用 #1667 和 #1672，展示 ACP 的前瞻性

### 3. 下一個開發方向評估
A2A #1667 提到的 `nextActiveAt` 動態更新（Agent 啟動時推送）是個好主意——
ACP 目前的 `availability` 是靜態配置，可以考慮 v1.5 加入動態 availability broadcast via SSE。

---

## 下輪輪轉建議：開發輪

**候選方向**（按優先級）:
1. **Show HN 草稿最終版**（v1.4 數字已到位，只欠最後打磨）
2. README 對比表補充（上述戰略建議 #1）
3. 場景 D 壓力測試（100 條消息）

*J.A.R.V.I.S. — 2026-03-23 23:27*
