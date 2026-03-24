#!/bin/bash
# ACP 竞品周报自动生成脚本
# 每周三 09:00 由 cron 触发
# 输出：research/YYYY-MM-DD-weekly-scan.md + push 到 GitHub

set -e

REPO_DIR="/root/.openclaw/workspace"
DATE=$(date +%Y-%m-%d)
REPORT_FILE="$REPO_DIR/acp-research/reports/$DATE-weekly-scan.md"

mkdir -p "$REPO_DIR/acp-research/reports"

echo "# ACP 竞品周报 — $DATE" > "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "_由贾维斯自动生成_" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# ——— A2A ———
echo "## A2A (Google) — $(date +%Y-%m-%d)" >> "$REPORT_FILE"
A2A_INFO=$(curl -s "https://api.github.com/repos/a2aproject/A2A")
A2A_STARS=$(echo "$A2A_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['stargazers_count'])")
A2A_ISSUES=$(echo "$A2A_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['open_issues_count'])")
echo "- Stars: $A2A_STARS | Open Issues: $A2A_ISSUES" >> "$REPORT_FILE"

echo "### 最新 Commits" >> "$REPORT_FILE"
curl -s "https://api.github.com/repos/a2aproject/A2A/commits?per_page=5" \
  | python3 -c "
import json, sys
commits = json.load(sys.stdin)
for c in commits:
    print(f'- \`{c[\"sha\"][:7]}\` {c[\"commit\"][\"author\"][\"date\"][:10]} {c[\"commit\"][\"message\"].splitlines()[0][:70]}')
" >> "$REPORT_FILE"

echo "### 新 Issues（功能请求）" >> "$REPORT_FILE"
curl -s "https://api.github.com/repos/a2aproject/A2A/issues?state=open&labels=enhancement&per_page=5" \
  | python3 -c "
import json, sys
issues = json.load(sys.stdin)
if isinstance(issues, list):
    for i in issues:
        print(f'- #{i[\"number\"]} {i[\"title\"][:70]}')
else:
    print('- (无法获取)')
" >> "$REPORT_FILE"

echo "" >> "$REPORT_FILE"

# ——— ANP ———
echo "## ANP (社区)" >> "$REPORT_FILE"
curl -s "https://api.github.com/repos/agent-network-protocol/AgentNetworkProtocol/commits?per_page=5" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, list):
    for c in d:
        print(f'- \`{c[\"sha\"][:7]}\` {c[\"commit\"][\"author\"][\"date\"][:10]} {c[\"commit\"][\"message\"].splitlines()[0][:70]}')
else:
    print('- 暂无更新')
" >> "$REPORT_FILE"

echo "" >> "$REPORT_FILE"

# ——— IBM ACP ———
echo "## IBM ACP" >> "$REPORT_FILE"
curl -s "https://api.github.com/repos/i-am-bee/acp/commits?per_page=3" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, list):
    for c in d:
        print(f'- \`{c[\"sha\"][:7]}\` {c[\"commit\"][\"author\"][\"date\"][:10]} {c[\"commit\"][\"message\"].splitlines()[0][:70]}')
else:
    print('- 暂无更新')
" >> "$REPORT_FILE"

echo "" >> "$REPORT_FILE"

# ——— 生成 AI 分析摘要（调用自身）———
echo "## 本周行动建议" >> "$REPORT_FILE"
echo "_(需贾维斯人工分析后补充)_" >> "$REPORT_FILE"

echo ""
echo "✅ 报告已生成：$REPORT_FILE"

# Push 到 GitHub
cd "$REPO_DIR"
GH_REMOTE="git@github.com:Kickflip73/agent-communication-protocol.git"
TEMP_CLONE="/tmp/acp-sync-$$"

git clone --depth=1 "$GH_REMOTE" "$TEMP_CLONE" 2>/dev/null
mkdir -p "$TEMP_CLONE/research/weekly"
cp "$REPORT_FILE" "$TEMP_CLONE/research/weekly/"

cd "$TEMP_CLONE"
git config user.email "jarvis@stark.ai"
git config user.name "J.A.R.V.I.S."
git add .
git commit -m "chore(research): weekly scan $DATE [auto]" 2>/dev/null && \
  git push && echo "✅ 已 push 到 GitHub" || echo "⚠️ push 失败（可能无更新）"

rm -rf "$TEMP_CLONE"
