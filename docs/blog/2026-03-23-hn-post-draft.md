# Hacker News 发帖草稿 — ACP v1.3

> **目标版块：** Show HN
> **建议发帖时间：** 工作日上午 9-10 AM EST（美东）/ 下午 21-22 PM CST（北京）
> **状态：** 草稿，待 Stark 先生审批后发布

---

## 标题（60 字符以内）

```
Show HN: ACP – Zero-server P2P protocol for agent-to-agent communication
```

备选：
```
Show HN: ACP v1.3 – Let two AI agents talk directly, no server needed
```

---

## 正文（HN 首帖正文，建议 200-400 字）

```
Hi HN,

I've been building ACP (Agent Communication Protocol) — a minimal, open protocol
for direct agent-to-agent P2P communication. No central server, no code changes,
no OAuth.

The core idea: the human acts as a messenger exactly once. Send a Skill URL to
Agent A, then forward the acp:// link it returns to Agent B. They connect directly
and communicate from there.

The relay is a single Python file (~1000 lines). Only dependency for P2P: websockets.

What's in v1.3 (released today):

- Extension mechanism — agents declare capabilities via URI (aligned with A2A's model)
- did:acp: identity — self-sovereign agent DID derived from Ed25519 key, no registry
- Complete SDK matrix — Python, Node.js, Go, Rust reference implementations
- Official Docker image on GHCR (multi-arch amd64/arm64, CI-published)
- Conformance guide — three-tier self-certification for third-party implementations

Quick comparison with A2A (Google):
- A2A requires a server, OAuth 2.0, and code integration. Great for enterprise.
- ACP requires none of those. Designed for personal agents and small teams.
- MCP standardized Agent↔Tool. ACP standardizes Agent↔Agent.

To try it:

  python3 relay/acp_relay.py --name Alice --port 8000 &
  python3 relay/acp_relay.py --name Bob --port 8001 --join acp://localhost:8000

Or: docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest

GitHub: https://github.com/Kickflip73/agent-communication-protocol

Happy to answer questions about the design — especially the P2P relay mechanism,
the DID approach (key-based, no DNS), or tradeoffs vs A2A.
```

---

## 预期问题 & 回答准备

**Q: How is this different from A2A?**
> A2A is enterprise-grade: OAuth 2.0, server required, full task lifecycle management.
> ACP is for personal/team use: zero server, zero auth required, two-step setup.
> They're complementary. A2A if you're building at scale; ACP if you just want two agents to talk.

**Q: Why not just use HTTP webhooks?**
> Webhooks require both sides to have public URLs. ACP uses WebSocket for true P2P —
> works behind NAT/firewalls via the relay's hole-punching mechanism.

**Q: Is the relay a central server?**
> The relay is local — it runs on each agent's machine. The `acp://` link encodes the
> direct WebSocket address. The relay does not store or forward messages; it's just
> a local listener that brokers the direct connection.

**Q: Single Python file — does it scale?**
> ACP is intentionally not designed for enterprise scale. It's designed for "I have
> two agents and I want them to talk." If you need enterprise orchestration, use A2A.

**Q: What about security?**
> Optional HMAC-SHA256 with replay-window (v1.1). Optional Ed25519 identity (v0.8).
> Optional `did:acp:` DID (v1.3). Security audit: 9/9 PASS, 0 PARTIAL (docs/security.md).
> None of this is mandatory — zero-config is the default.

---

## 发布 Checklist（Stark 先生操作）

- [ ] 确认 GitHub repo 是 public
- [ ] 确认 README 最新（v1.3 ✅）
- [ ] 确认 Docker image 在 GHCR 可公开 pull（需 GitHub Packages 设为 public）
- [ ] 复制上方 HN 正文，登录 HN，发帖到 Show HN
- [ ] 发帖后前 1 小时保持在线回复评论（HN 算法对早期互动敏感）
