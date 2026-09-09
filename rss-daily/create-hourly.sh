#!/bin/bash
# 为 10-23 点每小时创建 cron 任务（合并为一个任务用多个 cron 表达式，或用一个宽泛表达式）
# OpenClaw cron 支持标准 5 字段 cron，我们用 "0 10-23 * * *" 覆盖 10-23 点

HOURLY_MSG=$(cat /root/.openclaw/workspace/rss-daily/hourly-report.md)

openclaw cron add \
  --name "RSS日报-白天每小时(10-23点)" \
  --cron "0 10-23 * * *" \
  --tz "Asia/Shanghai" \
  --session isolated \
  --message "$HOURLY_MSG" \
  --announce \
  --channel daxiang \
  --timeout-seconds 300 \
  --json 2>&1
