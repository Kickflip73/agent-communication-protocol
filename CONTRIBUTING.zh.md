# 贡献指南

**语言**：[English](CONTRIBUTING.md) · **中文**

欢迎！ACP 由社区驱动，所有形式的贡献都受欢迎。

---

## 贡献方式

- 📝 **规范反馈** — 开 Issue 提出对规范的修改建议
- 🐛 **Bug 报告** — SDK Bug、规范歧义、文档错误
- 💡 **新消息类型** — 通过 RFC 流程提案（见下文）
- 🔌 **传输绑定** — 实现新的传输层适配器（WebSocket、MQTT 等）
- 🌐 **翻译** — 规范和文档的多语言翻译
- 💻 **SDK 实现** — 新语言的 SDK（Go、Rust、Java 等）

---

## 快速开始

```bash
git clone https://github.com/Kickflip73/agent-communication-protocol.git
cd agent-communication-protocol

# 运行 P2P Demo
cd p2p/examples
pip install aiohttp
python demo_lifecycle.py   # 生命周期演示
python demo_group.py       # 群聊演示
```

---

## RFC 流程（新特性提案）

1. **在 Issues 中开讨论** — 标题格式：`[RFC] 你的提案标题`
2. **社区讨论** — 收集反馈，至少 7 天讨论期
3. **提交 PR** — 在 `spec/rfcs/` 目录下添加 `rfc-NNNN-标题.md`
4. **代码实现** — 规范合并后，提交 SDK 参考实现
5. **文档更新** — 同步更新中英文文档

---

## 代码规范

### Python SDK

- 兼容 Python 3.10+
- 类型注解（`from __future__ import annotations`）
- 异步优先（`async/await`）
- 尽量减少外部依赖

### 文档

- 每个英文文档需提供对应中文版（`.zh.md` 后缀）
- README 顶部保持语言切换 tab：`[English](#...) · [中文](#...)`
- 代码示例必须可直接运行

---

## 提交 PR

1. Fork 仓库
2. 创建特性分支：`git checkout -b feat/my-feature`
3. 提交：`git commit -m "feat: 描述你的改动"`
4. Push：`git push origin feat/my-feature`
5. 开 Pull Request，填写改动说明

### Commit 格式

```
feat:     新特性
fix:      Bug 修复
spec:     规范文档变更
docs:     文档更新
refactor: 重构（无功能变化）
test:     测试相关
```

---

## 行为准则

- 友善、包容、尊重
- 聚焦技术，避免人身攻击
- 欢迎新人，解答问题

---

## 联系

- GitHub Issues：https://github.com/Kickflip73/agent-communication-protocol/issues
- 规范讨论：在对应的规范文件下开 Issue

感谢你的贡献！🙏
