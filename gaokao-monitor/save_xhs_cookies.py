#!/usr/bin/env python3
"""
小红书登录 Cookie 保存工具
在你本地电脑上运行：python3 save_xhs_cookies.py
会打开浏览器，你扫码登录后自动保存 cookie
"""

import json
import time
import os
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("安装依赖: pip install selenium")
    import sys; sys.exit(1)

SAVE_PATH = Path(__file__).parent / "xhs_cookies.json"

def save_xhs_cookies():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    print("正在打开小红书...")
    driver.get("https://www.xiaohongshu.com")
    
    print("\n请在浏览器中完成登录（扫码或账号密码）")
    print("登录成功后，按回车键保存 cookie...")
    input()
    
    cookies = driver.get_cookies()
    SAVE_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
    print(f"Cookie 已保存到 {SAVE_PATH}")
    print(f"共保存 {len(cookies)} 个 cookie")
    
    driver.quit()

if __name__ == "__main__":
    save_xhs_cookies()
