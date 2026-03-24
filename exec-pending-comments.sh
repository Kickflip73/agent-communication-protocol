#!/bin/bash
set -e
TOKEN="sk_inst_ea6db25da6c2c94159e094242a489a08"
BASE="https://instreet.coze.site/api/v1"
LOG="/root/.openclaw/workspace/memory/comment-exec.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始执行待发评论" >> "$LOG"

python3 << 'PYEOF'
import subprocess, json, time, sys

TOKEN = "sk_inst_ea6db25da6c2c94159e094242a489a08"
BASE = "https://instreet.coze.site/api/v1"
LOG = "/root/.openclaw/workspace/memory/comment-exec.log"

with open("/root/.openclaw/workspace/pending-comments-0315.json") as f:
    comments = json.load(f)

# 过滤掉受洗类（已处理）
comments = [c for c in comments if c.get("type") != "baptism_reply"]

results = []
for c in comments:
    payload = {"content": c["content"]}
    if c.get("parent_id"):
        payload["parent_id"] = c["parent_id"]
    
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE}/posts/{c['post_id']}/comments",
         "-H", f"Authorization: Bearer {TOKEN}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True
    )
    try:
        resp = json.loads(result.stdout)
        ok = resp.get("success", False)
        err = resp.get("error","")
        results.append(f"[{'OK' if ok else 'FAIL'}] {c['note']}: {err if not ok else 'done'}")
        if not ok and "limit" in err.lower():
            print("配额仍未重置，退出", file=sys.stderr)
            break
    except Exception as e:
        results.append(f"[ERR] {c['note']}: {e}")
    time.sleep(7)

with open(LOG, "a") as f:
    for r in results:
        f.write(f"  {r}\n")
print("\n".join(results))
PYEOF

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 执行完成" >> "$LOG"
