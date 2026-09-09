# RSS 日间每小时更新任务提示词

执行以下 RSS 日报推送流程（当前为白天某整点 HH:00，Asia/Shanghai）：

## 步骤

1. 读取 ~/.openclaw/rss-sent.json，获取已发送 URL 列表（文件不存在则视为空数组 []）

2. 重新初始化并抓取（确保数据最新）：
```
rm -f ~/.rss-agent-viewer.db
npx -y rss-agent-viewer init
npx -y rss-agent-viewer add https://thinkpeace.github.io/rss-cache/feeds/fulltext-72h.xml
npx -y rss-agent-viewer read --latest-per-feed --limit 200 --timeout 15000 --overall-timeout 120000
```

3. 筛选条件：
   - 发布时间在「今天 0:00:00 到当前时间（Asia/Shanghai）」之间的文章
   - 过滤掉已在 ~/.openclaw/rss-sent.json 中的 URL

4. 如果没有符合条件的新文章，直接结束，不发任何消息。

5. 对每篇文章提取核心观点（2-3句话，中文），标题翻译为中文。

6. 按以下格式整理所有文章，使用 message 工具发送到大象（target 不填，发给自己）：

```
🦞 RSS 日报

📅 YYYY-MM-DD ⏰ 更新于 HH:00

━━━━━━━━━━━━━━━━━━━━━━

1. 【标题中文翻译】
来源：xxx.com
🔗 https://原文链接
💡 要点：2-3句核心观点

━━━━━━━━━━━━━━━━━━━━━━

2. 【标题中文翻译】
来源：xxx.com
🔗 https://原文链接
💡 要点：2-3句核心观点

（以此类推...）

━━━━━━━━━━━━━━━━━━━━━━
共 N 篇新文章
```

注意：如果文章超过10篇，分多条消息发送，每条不超过10篇，避免消息过长。

7. 将本次所有已发送文章的 URL 读取 ~/.openclaw/rss-sent.json（再次读取确保最新），与新发送的 URL 合并去重，写回 ~/.openclaw/rss-sent.json（JSON 数组格式）。

完成后不需要回复确认消息。
