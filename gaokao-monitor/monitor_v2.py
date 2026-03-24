#!/usr/bin/env python3
"""
北京211+高校计算机考研复试信息监控脚本 v2
本地运行版本 - 直连高校官网，无需代理

用法：
  python3 monitor_v2.py              # 运行一次检查
  python3 monitor_v2.py --loop 1200  # 每1200秒(20分钟)循环运行

依赖：pip install requests beautifulsoup4
"""

import json
import os
import sys
import time
import hashlib
import datetime
import re
import argparse
import subprocess
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("安装依赖: pip install requests beautifulsoup4")
    sys.exit(1)

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
RESULTS_FILE = BASE_DIR / "reexam-monitor.md"
UNIS_FILE = BASE_DIR / "universities.json"

# 小红书 cookie 文件（由 save_xhs_cookies.py 生成）
XHS_COOKIE_FILE = BASE_DIR / "xhs_cookies.json"

# 大象 misId
DAXIANG_MIS_ID = "liuyuran02"

# 复试相关关键词
REEXAM_KEYWORDS = [
    "复试", "复试线", "复试分数线", "复试名单", "复试通知",
    "进入复试", "复试资格", "差额复试", "复试比例",
    "拟录取", "2026年复试", "26届复试", "2026复试",
    "国家线", "自划线", "院线", "复试方案", "复试细则",
]

CS_KEYWORDS = [
    "计算机", "软件工程", "人工智能", "信息工程", "网络空间安全",
    "数据科学", "电子信息", "083", "085", "计科", "软件",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"seen_hashes": {}, "findings": [], "xhs_seen": set()}


def save_state(state):
    # set 转 list 方便序列化
    s = dict(state)
    s["xhs_seen"] = list(state.get("xhs_seen", set()))
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def load_unis():
    return json.loads(UNIS_FILE.read_text(encoding="utf-8"))["universities"]


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:16]


def fetch_page(url: str, session: requests.Session, timeout=15) -> str:
    try:
        r = session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"    fetch error {url}: {e}")
        return ""


def is_reexam_relevant(text: str) -> bool:
    return any(kw in text for kw in REEXAM_KEYWORDS)


def extract_notice_list(html: str, base_url: str) -> list[dict]:
    """从研究生院通知列表页提取公告条目"""
    soup = BeautifulSoup(html, "html.parser")
    notices = []

    # 常见通知列表结构：li > a 或 td > a
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if len(title) < 6:
            continue
        if is_reexam_relevant(title):
            href = a["href"]
            if not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(base_url, href)
            notices.append({"title": title, "url": href})

    return notices


def extract_page_snippets(html: str) -> list[str]:
    """从页面正文提取含复试关键词的文本片段"""
    soup = BeautifulSoup(html, "html.parser")
    # 去掉 script/style
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="。", strip=True)
    text = re.sub(r"\s+", " ", text)

    snippets = []
    for sent in re.split(r"[。！\n]", text):
        sent = sent.strip()
        if len(sent) < 10:
            continue
        if is_reexam_relevant(sent):
            snippets.append(sent[:200])
    return snippets[:5]


def check_university(uni: dict, state: dict, session: requests.Session) -> list[dict]:
    new_findings = []
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 构建要检查的 URL 列表（通知公告页）
    urls = [uni["reexam_url"]]
    extra = {
        "北京邮电大学": ["https://yz.bupt.edu.cn/tzgg.htm", "https://cs.bupt.edu.cn/info/1010/1.htm"],
        "北京航空航天大学": ["https://gs.buaa.edu.cn/tzgg.htm"],
        "北京理工大学": ["https://gs.bit.edu.cn/tzgg/index.htm"],
        "中国人民大学": ["http://gs.ruc.edu.cn/tzgg/index.htm"],
        "北京交通大学": ["https://gs.bjtu.edu.cn/cms/category/6.html"],
        "北京科技大学": ["https://yjsy.ustb.edu.cn/tzgg/index.htm"],
        "北京师范大学": ["https://yjsy.bnu.edu.cn/tzgg/index.htm"],
        "清华大学": ["https://yz.tsinghua.edu.cn/info/1052/1.htm"],
        "北京大学": ["https://admission.pku.edu.cn/yjszs/tzgg/index.htm"],
    }
    if uni["name"] in extra:
        urls += extra[uni["name"]]

    urls = list(dict.fromkeys(urls))  # 去重

    for url in urls:
        html = fetch_page(url, session)
        if not html:
            continue

        h = content_hash(html)
        state_key = f"{uni['name']}|{url}"

        if state["seen_hashes"].get(state_key) == h:
            continue  # 页面内容未变化

        state["seen_hashes"][state_key] = h

        # 提取通知列表
        notices = extract_notice_list(html, url)
        for n in notices:
            fid = content_hash(n["title"] + n["url"])
            if fid not in state["seen_hashes"]:
                state["seen_hashes"][fid] = "1"
                new_findings.append({
                    "university": uni["name"],
                    "source": n["url"],
                    "type": "官网通知",
                    "content": n["title"],
                    "time": now_str,
                })

        # 提取正文片段（用于没有列表结构的页面）
        snippets = extract_page_snippets(html)
        for s in snippets:
            fid = content_hash(s)
            if fid not in state["seen_hashes"]:
                state["seen_hashes"][fid] = "1"
                new_findings.append({
                    "university": uni["name"],
                    "source": url,
                    "type": "官网正文",
                    "content": s,
                    "time": now_str,
                })

        time.sleep(0.8)

    return new_findings


def search_xiaohongshu(session: requests.Session, state: dict) -> list[dict]:
    """搜索小红书（需要登录 cookie）"""
    results = []
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if not XHS_COOKIE_FILE.exists():
        return results

    try:
        cookies_data = json.loads(XHS_COOKIE_FILE.read_text(encoding="utf-8"))
        cookies = {c["name"]: c["value"] for c in cookies_data}
    except Exception:
        return results

    keywords = [
        "2026计算机考研复试线",
        "北京高校计算机复试",
        "计算机研究生复试2026",
        "北邮北航北理复试",
    ]

    xhs_seen = set(state.get("xhs_seen", []))

    for kw in keywords:
        try:
            url = "https://www.xiaohongshu.com/api/sns/web/v1/search/notes"
            params = {
                "keyword": kw,
                "page": 1,
                "page_size": 20,
                "search_id": "",
                "sort": "general",
                "note_type": 0,
            }
            headers = {**HEADERS, "Referer": "https://www.xiaohongshu.com/"}
            r = session.get(url, params=params, cookies=cookies,
                            headers=headers, timeout=15)
            data = r.json()

            items = data.get("data", {}).get("items", [])
            for item in items:
                note = item.get("note_card", {})
                note_id = item.get("id", "")
                title = note.get("display_title", "")
                desc = note.get("desc", "")
                text = title + " " + desc

                if note_id in xhs_seen:
                    continue

                if is_reexam_relevant(text):
                    xhs_seen.add(note_id)
                    results.append({
                        "university": "小红书",
                        "source": f"https://www.xiaohongshu.com/explore/{note_id}",
                        "type": "小红书",
                        "content": f"【{title}】{desc[:100]}",
                        "time": now_str,
                    })

            state["xhs_seen"] = xhs_seen
            time.sleep(2)

        except Exception as e:
            print(f"    小红书搜索失败 [{kw}]: {e}")

    return results


def update_results_doc(all_findings: list[dict]):
    """维护 GitHub 文档"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 按学校分组 + 时间倒序
    by_uni: dict[str, list] = {}
    for f in sorted(all_findings, key=lambda x: x["time"], reverse=True):
        uni = f["university"]
        if uni not in by_uni:
            by_uni[uni] = []
        by_uni[uni].append(f)

    lines = [
        "# 2026年北京211高校计算机考研复试信息汇总",
        "",
        f"最后更新：{now}",
        "",
        "监控学校：20所北京211及以上高校",
        "数据来源：各校研究生院官网 + 小红书",
        "更新频率：每20分钟自动检查一次",
        "",
        "---",
        "",
    ]

    if not all_findings:
        lines += [
            "## 暂无复试信息",
            "",
            "监控运行中，尚未检测到复试相关公告。",
            "一旦有复试线、复试名单、复试安排发布，将立即更新并推送通知。",
            "",
            "## 监控学校列表",
            "",
        ]
        unis = load_unis()
        for u in unis:
            lines.append(f"- **{u['name']}**（{u['cs_dept']}）")
    else:
        lines += [f"## 已发现 {len(all_findings)} 条复试信息", ""]
        for uni_name, findings in sorted(by_uni.items()):
            lines += [f"### {uni_name}", ""]
            for f in findings[:10]:  # 每校最多展示10条
                lines += [
                    f"**{f['time']}** · {f['type']}",
                    f"",
                    f"> {f['content']}",
                    f"",
                    f"来源：{f['source']}",
                    "",
                ]

    lines += [
        "---",
        "",
        "## 监控说明",
        "",
        "本文档由 J.A.R.V.I.S. 自动维护，每20分钟更新一次。",
        "",
        "重点关注内容：",
        "- 国家复试线（教育部划定）",
        "- 学校自划线（高于国家线）",
        "- 各学院/专业复试分数线",
        "- 进入复试名单公示",
        "- 复试时间、地点、形式安排",
        "",
        "如有遗漏或信息有误，请及时反馈。",
    ]

    RESULTS_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"    文档已更新：{RESULTS_FILE}")


def git_push():
    """提交并推送到 GitHub"""
    try:
        repo_dir = BASE_DIR.parent  # tech-daily/
        dest = repo_dir / "kaoyan-2026" / "reexam-monitor.md"
        dest.parent.mkdir(exist_ok=True)

        import shutil
        shutil.copy(RESULTS_FILE, dest)

        subprocess.run(
            ["git", "add", "kaoyan-2026/reexam-monitor.md"],
            cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m",
             f"chore: update kaoyan reexam monitor {datetime.datetime.now().strftime('%m-%d %H:%M')}"],
            cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "push"],
            cwd=repo_dir, check=True, capture_output=True,
            env={**os.environ, "GIT_SSH_COMMAND": "ssh -i ~/.ssh/id_ed25519_github -o StrictHostKeyChecking=no"}
        )
        print("    已推送到 GitHub")
    except subprocess.CalledProcessError as e:
        if b"nothing to commit" in e.stderr or b"nothing to commit" in e.stdout:
            print("    GitHub：无变化，跳过推送")
        else:
            print(f"    GitHub 推送失败：{e}")


def send_daxiang_via_openclaw(message: str):
    """
    调用 openclaw message CLI 发送大象消息
    在 OpenClaw 沙箱外运行时使用
    """
    try:
        subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "daxiang",
             "--to", DAXIANG_MIS_ID,
             "--message", message],
            check=True, timeout=30
        )
        print(f"    大象消息已发送")
    except Exception as e:
        print(f"    大象消息发送失败：{e}")
        # fallback：写到文件，下次 cron/heartbeat 捡起来
        pending = BASE_DIR / "pending_daxiang.txt"
        pending.write_text(message, encoding="utf-8")
        print(f"    已写入 {pending}，等待下次发送")


def format_alert(new_findings: list[dict]) -> str:
    lines = [f"🎓 考研复试监控 · 发现 {len(new_findings)} 条新信息\n"]
    for f in new_findings[:8]:
        lines.append(f"📌 {f['university']} [{f['type']}]")
        lines.append(f"   {f['content'][:120]}")
        lines.append(f"   🕐 {f['time']}")
        lines.append("")
    if len(new_findings) > 8:
        lines.append(f"（还有 {len(new_findings)-8} 条，详见 GitHub）")
    lines.append("📄 https://github.com/Kickflip73/tech-daily/blob/main/kaoyan-2026/reexam-monitor.md")
    return "\n".join(lines)


def run_once():
    print(f"\n{'='*50}")
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始检查")

    state = load_state()
    if isinstance(state.get("xhs_seen"), list):
        state["xhs_seen"] = set(state["xhs_seen"])

    unis = load_unis()
    all_new = []

    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. 检查各校官网
    print(f"\n[官网检查] 共 {len(unis)} 所学校")
    for uni in unis:
        try:
            findings = check_university(uni, state, session)
            if findings:
                print(f"  ✓ {uni['name']}: {len(findings)} 条新内容")
                all_new.extend(findings)
                state["findings"].extend(findings)
            else:
                print(f"  - {uni['name']}: 无变化")
        except Exception as e:
            print(f"  ✗ {uni['name']}: {e}")

    # 2. 检查小红书
    print(f"\n[小红书检查]")
    if XHS_COOKIE_FILE.exists():
        xhs_results = search_xiaohongshu(session, state)
        if xhs_results:
            print(f"  ✓ 小红书: {len(xhs_results)} 条新内容")
            all_new.extend(xhs_results)
            state["findings"].extend(xhs_results)
        else:
            print(f"  - 小红书: 无新相关内容")
    else:
        print(f"  ⚠ 未找到小红书登录 cookie，跳过")
        print(f"    运行 python3 save_xhs_cookies.py 完成登录")

    # 3. 更新文档
    print(f"\n[更新文档]")
    update_results_doc(state["findings"])

    # 4. 推送 GitHub
    git_push()

    # 5. 发大象通知
    if all_new:
        msg = format_alert(all_new)
        print(f"\n[大象通知] 发现新信息，推送中...")
        send_daxiang_via_openclaw(msg)

    save_state(state)
    print(f"\n完成，新发现 {len(all_new)} 条")
    return len(all_new)


def main():
    parser = argparse.ArgumentParser(description="考研复试监控")
    parser.add_argument("--loop", type=int, default=0,
                        help="循环间隔秒数（0=只运行一次）")
    args = parser.parse_args()

    if args.loop > 0:
        print(f"循环模式：每 {args.loop} 秒检查一次")
        while True:
            run_once()
            print(f"等待 {args.loop} 秒...")
            time.sleep(args.loop)
    else:
        run_once()


if __name__ == "__main__":
    main()
