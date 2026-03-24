#!/usr/bin/env python3
"""
北京211+高校计算机考研复试信息监控脚本
监控内容：复试线、复试名单、复试安排
数据来源：各校官网研究生院 + 小红书
"""

import json
import os
import sys
import time
import hashlib
import datetime
import subprocess
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
RESULTS_FILE = BASE_DIR / "results.md"
UNIS_FILE = BASE_DIR / "universities.json"

PROXY = f"http://{os.environ.get('UPSTREAM_PROXY_HOST', '')}:{os.environ.get('UPSTREAM_PROXY_PORT', '')}"

DAXIANG_MIS_ID = "liuyuran02"

# 复试相关关键词
REEXAM_KEYWORDS = [
    "复试", "复试线", "复试分数线", "复试名单", "复试通知",
    "进入复试", "复试资格", "差额复试", "复试比例",
    "拟录取", "2026年复试", "26届复试",
    "国家线", "自划线", "院线",
]

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen_hashes": {}, "last_check": {}, "findings": []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def load_unis():
    return json.loads(UNIS_FILE.read_text())["universities"]

def content_hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]

def fetch_url(url, timeout=20):
    """通过 curl + proxy 抓取页面文本"""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout),
             "--proxy", PROXY,
             "-L", "--compressed",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             "-H", "Accept: text/html,application/xhtml+xml",
             url],
            capture_output=True, text=True, timeout=timeout + 5
        )
        return result.stdout
    except Exception as e:
        return ""

def extract_relevant_snippets(html, university_name):
    """从HTML中提取含复试关键词的文本片段"""
    # 去除HTML标签
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    
    findings = []
    lines = text.split('。')
    for line in lines:
        line = line.strip()
        if len(line) < 10:
            continue
        if any(kw in line for kw in REEXAM_KEYWORDS):
            # 确认跟计算机相关
            cs_keywords = ["计算机", "软件", "人工智能", "信息", "网络", "数据", "AI", "CS"]
            # 若包含复试关键词，即使没有CS词也记录（因为已经在CS院系页面）
            snippet = line[:200]
            findings.append(snippet)
    
    return findings[:5]  # 最多返回5条

def search_xiaohongshu(keywords, cookie_file=None):
    """
    小红书搜索 - 需要登录态
    cookie_file: 存储登录cookie的文件路径
    """
    results = []
    
    cookie_path = BASE_DIR / "xhs_cookies.json"
    if not cookie_path.exists():
        return results, False  # 未登录
    
    try:
        cookies = json.loads(cookie_path.read_text())
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        for kw in keywords[:3]:  # 每次最多搜3个关键词
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={kw}&source=web_search_result_notes&type=51"
            result = subprocess.run(
                ["curl", "-s", "--max-time", "15",
                 "--proxy", PROXY,
                 "-H", f"Cookie: {cookie_str}",
                 "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                 "-H", "Referer: https://www.xiaohongshu.com/",
                 search_url],
                capture_output=True, text=True, timeout=20
            )
            html = result.stdout
            # 提取笔记标题和摘要
            titles = re.findall(r'"title":"([^"]{5,100})"', html)
            descs = re.findall(r'"desc":"([^"]{10,200})"', html)
            
            for title in titles[:5]:
                if any(kw2 in title for kw2 in REEXAM_KEYWORDS):
                    results.append(f"[小红书] {title}")
            
            time.sleep(2)
    
    except Exception as e:
        pass
    
    return results, True

def send_daxiang(message):
    """通过 OpenClaw message tool 发大象消息（写到临时文件让外部调用）"""
    msg_file = BASE_DIR / "pending_message.txt"
    msg_file.write_text(message)

def check_university(uni, state):
    """检查单所高校的复试信息"""
    new_findings = []
    
    # 检查研究生院公告页
    urls_to_check = [uni["reexam_url"]]
    
    # 一些学校有专门的通知公告页
    extra_urls = {
        "北京邮电大学": "https://yz.bupt.edu.cn/tzgg.htm",
        "北京航空航天大学": "https://gs.buaa.edu.cn/tzgg.htm", 
        "北京理工大学": "https://gs.bit.edu.cn/tzgg/index.htm",
        "北京邮电大学": "https://yz.bupt.edu.cn/tzgg.htm",
        "中国人民大学": "http://gs.ruc.edu.cn/tzgg/index.htm",
    }
    if uni["name"] in extra_urls:
        urls_to_check.append(extra_urls[uni["name"]])
    
    for url in urls_to_check:
        html = fetch_url(url)
        if not html:
            continue
        
        h = content_hash(html)
        state_key = f"{uni['name']}_{url}"
        
        if state["seen_hashes"].get(state_key) == h:
            continue  # 内容没变化
        
        # 内容有变化，提取相关片段
        snippets = extract_relevant_snippets(html, uni["name"])
        
        if snippets:
            new_findings.extend([{
                "university": uni["name"],
                "source": url,
                "type": "官网",
                "content": s,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            } for s in snippets])
        
        # 更新hash（不管有没有找到，都记录新hash避免重复处理）
        state["seen_hashes"][state_key] = h
        time.sleep(1)
    
    return new_findings

def update_results_doc(all_findings):
    """更新结果文档"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 按学校分组
    by_uni = {}
    for f in all_findings:
        uni = f["university"]
        if uni not in by_uni:
            by_uni[uni] = []
        by_uni[uni].append(f)
    
    lines = [
        "# 2026年北京211高校计算机考研复试信息汇总",
        "",
        f"> 最后更新：{now}  ",
        f"> 监控学校：20所北京211及以上高校  ",
        f"> 数据来源：各校官网研究生院 + 小红书  ",
        "",
        "---",
        "",
    ]
    
    if not all_findings:
        lines += [
            "## 暂无复试信息",
            "",
            "监控正在进行中，一旦有复试线、复试名单、复试安排等信息发布，将立即更新此文档并推送通知。",
            "",
            "## 监控学校列表",
            "",
        ]
        unis = load_unis()
        for uni in unis:
            lines.append(f"- {uni['name']}（{uni['cs_dept']}）")
    else:
        lines += ["## 已发现复试信息", ""]
        for uni_name, findings in sorted(by_uni.items()):
            lines += [f"### {uni_name}", ""]
            for f in findings:
                lines += [
                    f"**{f['time']}** 来源：{f['type']}",
                    f"> {f['content']}",
                    f"",
                    f"[原始链接]({f['source']})",
                    "",
                ]
    
    lines += [
        "---",
        "",
        "## 监控说明",
        "",
        "- 每 20 分钟自动检查一次",
        "- 信息来源：各校研究生院官网 + 小红书",
        "- 重点关注：复试线（国家线/院线）、复试名单、复试安排",
        "- 有新消息时自动推送大象通知",
        "",
        f"*由 J.A.R.V.I.S. 自动维护*",
    ]
    
    RESULTS_FILE.write_text("\n".join(lines), encoding="utf-8")

def format_alert_message(new_findings):
    """格式化大象推送消息"""
    lines = [f"🎓 【考研复试监控】发现 {len(new_findings)} 条新信息\n"]
    
    for f in new_findings[:5]:  # 最多推送5条
        lines.append(f"📌 {f['university']} [{f['type']}]")
        lines.append(f"   {f['content'][:100]}")
        lines.append(f"   🕐 {f['time']}")
        lines.append("")
    
    if len(new_findings) > 5:
        lines.append(f"...还有 {len(new_findings)-5} 条，详见 GitHub 文档")
    
    lines.append("📄 完整信息：https://github.com/Kickflip73/tech-daily/blob/main/kaoyan-2026/reexam-monitor.md")
    
    return "\n".join(lines)

def main():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 开始检查...")
    
    state = load_state()
    unis = load_unis()
    all_new_findings = []
    
    # 检查各校官网
    for uni in unis:
        try:
            findings = check_university(uni, state)
            if findings:
                print(f"  ✓ {uni['name']}: 发现 {len(findings)} 条新信息")
                all_new_findings.extend(findings)
                state["findings"].extend(findings)
            else:
                print(f"  - {uni['name']}: 无新内容")
        except Exception as e:
            print(f"  ✗ {uni['name']}: 错误 - {e}")
        time.sleep(0.5)
    
    # 检查小红书（如果有登录态）
    xhs_keywords = ["计算机考研复试2026", "北京高校复试线2026", "计算机研究生复试"]
    xhs_results, xhs_logged_in = search_xiaohongshu(xhs_keywords)
    if xhs_results:
        for r in xhs_results:
            finding = {
                "university": "小红书汇总",
                "source": "https://www.xiaohongshu.com",
                "type": "小红书",
                "content": r,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            all_new_findings.append(finding)
            state["findings"].append(finding)
    
    # 更新文档
    update_results_doc(state["findings"])
    print(f"  ✓ 结果文档已更新")
    
    # 如果有新发现，写入待发送消息
    if all_new_findings:
        msg = format_alert_message(all_new_findings)
        send_daxiang(msg)
        print(f"  ✓ 已写入推送消息（{len(all_new_findings)}条新信息）")
    
    state["last_check"]["time"] = datetime.datetime.now().isoformat()
    save_state(state)
    
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 检查完成，新发现 {len(all_new_findings)} 条")
    
    # 输出结果供上层调用
    if all_new_findings:
        print("FINDINGS:" + json.dumps(all_new_findings[:3], ensure_ascii=False))
    
    return len(all_new_findings)

if __name__ == "__main__":
    count = main()
    sys.exit(0)
