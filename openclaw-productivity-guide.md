# 用 OpenClaw 给开发工作提效：一份写给程序员的实用指南

> 作者：Tony Stark 的日常实践整理  
> 环境：后端开发（Java / Spring Boot），公司 PaaS 部署  
> 写作时间：2026 年 3 月

---

这份文档不谈概念，只谈怎么用。

OpenClaw 是一个自托管的 AI 网关，把 AI 助手接入你常用的消息工具（微信/大象/Telegram/Discord 等），让你随时随地发消息就能用上 AI。作为一线程序员，我把它用了一段时间，下面是实际有用的场景，按使用频率排列。

---

## 一、随时随地的代码助手

**场景**：上班路上想到一个方案，或者在会议室临时被问到某个实现细节。

OpenClaw 接入 Telegram/大象后，手机发消息就能得到代码级回答，不需要打开电脑，不需要等加载网页。

常见用法：

```
帮我写一个 Spring Boot 的 Redis 分布式锁工具类，要支持自动续期
```

```
这段 SQL 有什么性能问题？
SELECT * FROM orders WHERE create_time > '2024-01-01' AND status = 1
```

```
给我解释一下 ConcurrentHashMap 的 segment 锁和 Java 8 之后的 CAS 区别
```

**实际效果**：不需要切换到浏览器搜索，不需要打开 ChatGPT 网页。消息发出去，几秒内有答案。对于「快速确认某个知识点」类型的问题，效率提升非常明显。

---

## 二、定时任务：让 AI 替你做例行工作

OpenClaw 内置了 cron 调度器，可以让 AI 在固定时间自动执行任务并推送结果给你。

### 例子 1：每日技术热点报告

```bash
openclaw cron add \
  --name "每日技术报告" \
  --cron "0 8 * * *" \
  --tz "Asia/Shanghai" \
  --session isolated \
  --message "搜索今日 AI、后端、Java 生态的技术热点，整理成简报推送给我" \
  --announce \
  --channel telegram \
  --to "@my_channel"
```

每天早上 8 点自动生成，不用你手动触发。结果直接推到 Telegram 频道或大象消息。

### 例子 2：20 分钟后提醒

开会前快速设置：

```
openclaw cron add --name "站会提醒" --at "20m" --session main --system-event "站会还有 5 分钟" --wake now --delete-after-run
```

或者直接发消息给 AI：「20 分钟后提醒我去开站会」，它会自动创建这个 cron。

### cron vs heartbeat：怎么选

| 需求 | 用什么 |
|------|--------|
| 精确时间执行（早上 9 点整） | cron |
| 多项例行检查打包在一起（邮件 + 日历 + 通知） | heartbeat |
| 一次性提醒 | cron + `--at` |
| 不需要精确时间的后台监控 | heartbeat |

---

## 三、背景任务：让 AI 帮你盯着事情

**场景**：你在专注写代码，同时让 AI 帮你监控某件事，有变化再通知你。

### 例子：监控 GitHub CI 状态

在 `HEARTBEAT.md` 里加一行：

```markdown
# HEARTBEAT.md
- 检查 github.com/my-org/my-repo 最近的 PR CI 状态，有失败的通知我
```

每 30 分钟心跳一次，有问题才发消息，没问题就静默。

### 例子：关注线上报警

```markdown
# HEARTBEAT.md
- 检查 Raptor 告警平台，有新的 ERROR 级别告警发我
```

这样你不需要一直盯着监控面板，AI 帮你守着，有情况再打扰你。

---

## 四、记忆系统：跨会话的上下文

OpenClaw 的 AI 每次对话都是全新的，但它有文件系统级别的记忆机制。

工作原理：
- `MEMORY.md`：长期记忆，写进去的东西下次对话还在
- `memory/YYYY-MM-DD.md`：每日日志，自动读今天和昨天的

你可以说：「记住我们组的 on-call 轮换表是周一换人」，它会写进文件，下次直接用。

**实用场景**：
- 记录项目架构决定（「xxx 模块用了 CQRS，原因是...」）
- 记录踩过的坑（「Redis key 过期时间不要用整数小时，会造成惊群」）
- 记录个人偏好（「代码 Review 重点关注事务边界和 NPE 风险」）

---

## 五、代码 Review 自动化

**场景**：PR 太多，想先让 AI 过一遍，自己只看重点。

### 方式 1：直接贴代码

把代码段发给 AI，指定关注点：

```
帮我 Review 这段代码，重点看：
1. 有没有 NPE 风险
2. 事务边界是否正确
3. 有没有 SQL 注入风险

[贴代码]
```

### 方式 2：结合 gh CLI，批量处理 PR

OpenClaw 集成了 `gh` CLI，可以配置自动拉取 PR 内容并生成 Review 意见：

```bash
# 配置 gh-issues skill 后，AI 可以自动抓取 PR 列表并分析
```

---

## 六、浏览器自动化：爬取 + 信息整理

**场景**：需要从内部系统批量拿数据，或者把某个网页的内容整理成文档。

OpenClaw 内置了 `agent-browser` 工具，AI 可以直接操控浏览器：

```
打开 https://jira.company.com/issues?filter=mine，把所有 P0/P1 的 issue 整理成一个列表
```

```
打开我们的 API 文档网站，把所有接口名称和描述提取出来，整理成 Markdown 表格
```

内部系统如果需要 SSO 登录，可以先在浏览器里手动登录，然后让 AI 接管已登录的会话继续操作。

---

## 七、文档生成

**场景**：写技术方案文档、接口文档是重复劳动，可以让 AI 起草。

常用的几种：

**接口文档**：
```
根据这段 Controller 代码，生成对应的 API 文档，包含接口描述、请求参数、返回值、错误码

[贴 Controller 代码]
```

**技术方案**：
```
我需要写一个分布式限流方案的技术文档，背景是：QPS 1000/s，多实例部署，需要用 Redis。
帮我列出大纲，然后逐节展开写
```

**故障复盘**：
```
帮我写一份故障复盘文档，背景如下：
- 故障时间：2026-03-15 14:30-15:45
- 影响：下单接口超时，影响约 3000 笔订单
- 根因：MySQL 慢查询导致连接池耗尽
- 修复：加索引，扩连接池上限
```

---

## 八、多平台接入：真正的随时随地

OpenClaw 支持同时接入多个消息平台，用同一个 AI 实例。

常见配置：

- **Telegram**：个人使用，功能最完整，推荐首选
- **Discord**：团队频道，可以建专属频道让 AI 帮整个团队
- **大象（美团内网）**：公司内使用
- **iMessage**：Mac 用户，跟 iOS 无缝衔接

配置完成后，你在手机 Telegram 问的问题，AI 会记住，下次在 Mac 大象继续问同一件事，上下文还在。

---

## 九、子 Agent 并行任务

**场景**：有个比较大的任务，可以拆成几个子任务并行跑。

OpenClaw 支持 spawn 子 Agent，主 Agent 派发任务后继续干别的，子 Agent 完成后自动汇报。

比如：

```
帮我同时做三件事：
1. 分析 service-a 模块的代码，找出潜在的性能问题
2. 搜索最新的 Spring Boot 3.x 升级指南
3. 检查 GitHub 上有没有新开的 P0 issue
完成后汇总给我
```

AI 会拆成三个子 Agent 并行跑，不用你等一件事做完再做下一件。

---

## 十、Skills：按需扩展能力

OpenClaw 支持 Skill 插件，每个 Skill 是一段专项能力的说明文件，AI 读完就知道怎么用。

实用的内置 Skill：

| Skill | 用途 |
|-------|------|
| `github` | 操作 GitHub：查 PR、Issue、CI 状态 |
| `code-git` | Git 操作和 SSH 配置 |
| `xlsx` | 读写 Excel，做数据分析 |
| `pdf` | 处理 PDF，提取内容、填表 |
| `calendar-manager` | 管理日历，查空闲时间 |
| `room-booking-helper` | 预订会议室 |

安装 Skill 后，直接用自然语言调用，不需要记命令。

---

## 配置起步

最简单的配置，只需要一个 API Key：

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
openclaw channels login   # 扫码接入 Telegram/微信等
openclaw gateway start
```

之后访问 `http://127.0.0.1:18789` 打开控制台，就能用了。

更细的配置文件在 `~/.openclaw/openclaw.json`，常用的几个设置：

```json5
{
  // 限制只有你自己能用
  channels: {
    telegram: {
      allowFrom: ["your_telegram_id"]
    }
  },
  // 心跳间隔（默认 30 分钟）
  agents: {
    defaults: {
      heartbeat: {
        every: "30m",
        activeHours: { start: "08:00", end: "22:00" }
      }
    }
  }
}
```

---

## 几个真实体验

**提效最明显的**：定时报告 + 随时发消息问问题。不需要切换上下文，思路不断。

**出乎意料好用的**：记忆系统。把项目里的「为什么这么做」记下来，过几个月回头看仍然有上下文。

**需要花时间配置的**：Skill 体系和浏览器自动化，上手有点学习成本，但配好之后很稳定。

**目前的局限**：复杂的多步骤自动化任务，AI 有时候会迷路，需要人工介入。这是大模型本身的限制，不是 OpenClaw 的问题。

---

## 相关链接

- 官方文档：https://docs.openclaw.ai
- GitHub：https://github.com/openclaw/openclaw
- 社区 Discord：https://discord.com/invite/clawd
- Skills 广场：https://clawhub.com
