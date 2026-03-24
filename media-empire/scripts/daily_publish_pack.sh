#!/usr/bin/env bash
set -euo pipefail

DATE=$(date +%F)
BASE=/root/.openclaw/workspace

echo "[1/4] 检查 tech-daily 今日报告..."
if [ ! -f "$BASE/tech-daily/reports/${DATE}.md" ]; then
  echo "❌ 今日报告不存在: $BASE/tech-daily/reports/${DATE}.md"
  exit 1
fi

echo "[2/4] 拷贝到自媒体目录（待改写）..."
mkdir -p "$BASE/media-empire/wechat" "$BASE/media-empire/xiaohongshu"
cp "$BASE/tech-daily/reports/${DATE}.md" "$BASE/media-empire/wechat/${DATE}.raw.md"
cp "$BASE/tech-daily/reports/${DATE}.md" "$BASE/media-empire/xiaohongshu/${DATE}.raw.md"

echo "[3/4] 状态提示"
echo "请让贾维斯生成："
echo "- wechat/${DATE}.md"
echo "- xiaohongshu/${DATE}.md"

echo "[4/4] 完成"
