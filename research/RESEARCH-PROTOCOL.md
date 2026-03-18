# ACP 持续研究协议

## 信息源（每周扫描）

### 主要协议仓库
- https://github.com/a2aproject/A2A — Google A2A（发布最活跃）
- https://github.com/agent-network-protocol/AgentNetworkProtocol — ANP
- https://github.com/i-am-bee/ACP — IBM BeeAgent ACP
- https://github.com/modelcontextprotocol/specification — MCP

### 论文追踪
- arXiv cs.MA (Multi-Agent Systems)
- arXiv cs.AI 关键词: agent communication, agent protocol, multi-agent interoperability

### 社区
- GitHub Trending: "agent protocol", "multi-agent"
- HackerNews: agent communication
- Reddit r/MachineLearning, r/LocalLLaMA

## 研究节奏

| 频率 | 内容 |
|------|------|
| 每周 | 扫描上述仓库的新 commit/release/issue |
| 双周 | 搜索新论文 |
| 月度 | 完整差距分析更新，产出一个优化版本 |

## 研究报告命名规范

```
research/YYYY-MM-DD-<主题>.md
```

## 优化方向路线图

### v0.2（✅ 已完成 2026-03-18）
- AgentCard 能力声明（参考 A2A）
- 断线自动重连
- 消息持久化
- SSE 流式端点

### v0.3（下一步）
- Task 生命周期（submitted/working/completed，参考 A2A）
- 多会话支持（一个 Agent 同时与多个 Agent 通信）
- 能力查询 API（发消息前先问"你能做什么"）
- 参考来源：A2A Task model, IBM ACP Session

### v0.4
- 多模态消息 Part（文本/文件引用/结构化数据，参考 IBM ACP）
- NAT 穿透探索（STUN，参考 WebRTC）

### v1.0
- DID 身份认证（参考 ANP）
- 能力发现网络（无中心注册表）
