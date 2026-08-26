# ACP DID 身份设计研究（did:acp:）

**日期**：2026-03-22  
**背景**：v1.3 规划项；ANP 基于 DID 的身份方案调研 + ACP 现有 Ed25519 方案升级路径

---

## 当前状态（v0.8 Ed25519）

```json
"identity": {
  "scheme":     "ed25519",
  "public_key": "<base64url-encoded 32-byte pubkey>"
}
```

问题：
- 公钥字符串不是自描述的（看不出协议/方法）
- 无法与 ANP、W3C DID 生态互操作
- 无法通过 DID URL 查询 AgentCard

---

## 目标格式：did:acp:

```
did:acp:<multibase-encoded-pubkey>
```

示例：
```
did:acp:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK
```

- `z` 前缀 = base58btc 编码（multibase 标准）
- 后续内容 = Ed25519 32-byte 公钥的 base58btc 编码

---

## 设计方案

### 方案 A：纯本地 DID（推荐，无需外部基础设施）

```
did:acp:<base58btc(pubkey_bytes)>
```

- 不需要链、不需要注册中心
- 和 `did:key` 方法（W3C）逻辑一致：DID = 公钥本身
- ACP AgentCard 即是 DID Document

#### DID Document（等价于 AgentCard）

```json
{
  "@context": ["https://www.w3.org/ns/did/v1"],
  "id": "did:acp:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "verificationMethod": [{
    "id": "did:acp:z6Mk...#key-1",
    "type": "Ed25519VerificationKey2020",
    "controller": "did:acp:z6Mk...",
    "publicKeyMultibase": "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
  }],
  "authentication": ["did:acp:z6Mk...#key-1"],
  "service": [{
    "id": "did:acp:z6Mk...#acp",
    "type": "ACPRelay",
    "serviceEndpoint": "acp://relay.acp.dev/<session_id>"
  }]
}
```

### 方案 B：DID + 外部注册（暂不做）
- 需要链或注册服务 → 违反 ACP 零基础设施原则
- 归入 v2.0 联邦化再考虑

---

## 实现要点

### 1. 生成 did:acp: 标识符

```python
import base58  # pip install base58

def pubkey_to_did_acp(pubkey_bytes: bytes) -> str:
    """Convert 32-byte Ed25519 public key to did:acp: identifier."""
    encoded = base58.b58encode(pubkey_bytes).decode()
    return f"did:acp:z{encoded}"  # 'z' = base58btc multibase prefix
```

### 2. AgentCard 变更（向后兼容）

当前（v0.8）：
```json
"identity": { "scheme": "ed25519", "public_key": "<base64url>" }
```

v1.3 扩展（新增 `did` 字段，原有字段保留）：
```json
"identity": {
  "scheme":     "ed25519",
  "public_key": "<base64url>",
  "did":        "did:acp:z6Mk..."
}
```

- 完全向后兼容：没有 `cryptography` 库的客户端忽略 `did` 字段
- `did` 字段 = 稳定的 Agent 标识符（跨 session 不变）

### 3. 消息签名中附带 DID

```json
{
  "role": "agent",
  "text": "hello",
  "identity": {
    "scheme":     "ed25519",
    "public_key": "<base64url>",
    "did":        "did:acp:z6Mk...",
    "sig":        "<base64url>"
  }
}
```

### 4. DID Document endpoint（可选）

```
GET /.well-known/did.json
```

返回 W3C DID Document（等价于 AgentCard 的 identity 视图），使外部系统可通过 DID URL 解析 ACP Relay。

---

## 依赖分析

| 方案 | 依赖 | 已有 |
|------|------|------|
| did:acp: 生成 | `base58` 库 | ❌ 需安装 |
| Ed25519 keypair | `cryptography` 库 | ✅ 已有（可选） |
| DID Document endpoint | 无额外依赖 | ✅ |

**问题**：`base58` 是额外依赖。替代方案：直接用 base64url（不符合 multibase 标准但零依赖）。

**推荐**：如果要严格对齐 W3C did:key，使用 base58；如果优先零依赖，用 `did:acp:<base64url(pubkey)>` 自定义格式。

---

## ANP 对比

| 维度 | ANP | ACP v1.3 计划 |
|------|-----|----------------|
| 标识符格式 | `did:wba:<domain>` (Web-based DID) | `did:acp:<pubkey>` (key-based DID) |
| 解析方式 | 需要 DNS + HTTP well-known | 纯本地，无外部依赖 |
| 注册 | 需要域名 | 零注册 |
| 适用场景 | 机构/企业 Agent | 个人/无服务器 Agent |

---

## 实现优先级建议

1. **v1.3（近期）**：在 AgentCard `identity` 中新增 `did` 字段（零依赖版本，用 base64url 或 base58）
2. **v1.3（后续）**：`GET /.well-known/did.json` DID Document endpoint
3. **v2.0**：完整 W3C DID Resolution（带 DID URL 查询）

---

## 关联情报

- A2A #1653：用户询问自定义 HTTP headers 归属（Extension Data vs Profile）→ ACP 的 Extension `params` 更简洁，不需要分类
- ANP 2026-03-05 更新：消息幂等性 + server_seq（ACP 已实现）
