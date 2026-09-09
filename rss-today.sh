#!/bin/bash
# 获取今天0点的时间戳（Asia/Shanghai）
TODAY_START=$(TZ=Asia/Shanghai date -d "$(TZ=Asia/Shanghai date +%Y-%m-%d) 00:00:00" +%s)
NOW=$(TZ=Asia/Shanghai date +%s)

echo "今天开始时间戳: $TODAY_START ($(TZ=Asia/Shanghai date -d @$TODAY_START '+%Y-%m-%d %H:%M:%S'))"
echo "当前时间戳: $NOW ($(TZ=Asia/Shanghai date -d @$NOW '+%Y-%m-%d %H:%M:%S'))"
