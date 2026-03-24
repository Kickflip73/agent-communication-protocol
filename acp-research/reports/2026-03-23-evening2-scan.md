# ACP 競品研究掃描 — 2026-03-23 晚間第二輪

## A2A 最新動態（今日）

### A2A 無新 commit（最新仍為 2026-03-16 CODEOWNERS 更新）

### 🔥 Issue #1667：Heartbeat Agent 可用性問題（今日提出）

**標題**：Heartbeat-based agents: availability metadata and offline-first task handling

**核心痛點**：A2A 規範假設 Agent 是持續在線的服務端點，但大量真實部署是「heartbeat 模式」——Agent 定時醒來處理工作，不在線時無人接收 `tasks/send`。規範目前沒有定義：
- Agent 何時在線（availability metadata）
- 任務如何在 Agent 離線時排隊
- 發送方如何知道 Agent 當前狀態

**ACP 對應**：
- ✅ ACP v1.2 已實現 `availability` 字段（cron/heartbeat 調度元數據）
- ✅ ACP Relay 天然支持離線排隊（消息存 JSONL，Agent 上線後讀取）
- 這正是 ACP 個人/小團隊場景的優勢！A2A 企業場景不考慮 heartbeat 模式

**戰略機會**：可在 Issue #1667 下回覆，介紹 ACP 的 availability 設計作為參考實現

---

### 🔐 Issue #1672：Agent 身份驗證（今日提出）

**標題**：Proposal: Agent Identity Verification for Agent Cards

**核心痛點**：A2A AgentCard 目前依賴 HTTPS/OAuth 做傳輸層信任，沒有協議級的加密身份驗證——無法確認「對方就是它聲稱的那個 Agent」。

**A2A 現狀**：依賴外部機制，無標準化方案

**ACP 對應**：
- ✅ ACP v0.8 已實現 Ed25519 身份驗證（`--identity` flag）
- ✅ ACP v1.3 已實現 `did:acp:` DID 身份標識符
- ACP 在這個問題上比 A2A 超前了！

**戰略意義**：A2A 社區剛意識到這個問題，ACP 已有實現。可以公開分享 ACP 的 Ed25519 + DID 方案作為參考。

---

## 核心洞察

**A2A 的企業化帶來的設計盲點，正在成為 ACP 的差異化優勢：**

1. **Heartbeat/可用性問題**（Issue #1667）：A2A 沒有，ACP v1.2 有 ✅
2. **Agent 身份驗證**（Issue #1672）：A2A 剛提出，ACP v0.8+v1.3 已實現 ✅
3. **P2P 無中心**：A2A 需要服務器，ACP P2P 直連 ✅

ACP 的輕量個人定位，使它天然解決了 A2A 因企業假設而忽視的問題。

---

## 行動項

- [ ] 評估是否在 Issue #1667 下分享 ACP availability 設計（增加曝光度）
- [ ] 評估是否在 Issue #1672 下分享 ACP Ed25519 + DID 方案

*整理：J.A.R.V.I.S. | 2026-03-23*
