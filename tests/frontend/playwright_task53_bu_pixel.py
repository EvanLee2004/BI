#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书53：补 BU 页像素 f6_bu_light_1440.png / f6_bu_dark_375.png。

密码只从 数据/看板账号.json 读取，绝不打印/写文件。
用法：服务已起 :8018 后
  .venv/bin/python tests/frontend/playwright_task53_bu_pixel.py [SCRATCH]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-07787fdbcd54/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "docs" / "pixel" / "vue"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8018"
ACCT = "zhengrui"


def load_pw() -> str:
    acc_path = ROOT / "数据" / "看板账号.json"
    if not acc_path.is_file():
        raise SystemExit("missing 数据/看板账号.json")
    data = json.loads(acc_path.read_text(encoding="utf-8"))
    for a in data.get("accounts") or []:
        if a.get("账号") == ACCT and str(a.get("密码") or "").strip():
            return str(a["密码"])
    raise SystemExit(f"no password for {ACCT}")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        (SCRATCH / "playwright_env_fail.txt").write_text(f"import: {e}\n", encoding="utf-8")
        return 2

    pw = load_pw()
    log = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            (SCRATCH / "playwright_env_fail.txt").write_text(f"launch: {e}\n", encoding="utf-8")
            return 2
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
        page.fill("#account", ACCT)
        page.fill("#password", pw)
        page.click('button[type="submit"]')
        page.wait_for_timeout(3000)
        # BU 账号应进 /bu/...
        url = page.url
        log.append(f"landed {url}")
        if "/bu/" not in url:
            # 尝试从 session 找
            page.goto(f"{BASE}/", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)
            log.append(f"after / {page.url}")
        page.wait_for_timeout(2500)

        # light 1440
        page.set_viewport_size({"width": 1440, "height": 900})
        page.evaluate(
            """() => {
            document.documentElement.classList.add('theme-light');
            document.documentElement.classList.add('light');
            document.body && document.body.classList.add('light');
            try { localStorage.setItem('cockpit-theme', 'light'); } catch(e) {}
        }"""
        )
        page.wait_for_timeout(800)
        p1 = OUT / "f6_bu_light_1440.png"
        page.screenshot(path=str(p1), full_page=False)
        log.append(f"shot {p1} bytes={p1.stat().st_size}")

        # dark 375
        page.set_viewport_size({"width": 375, "height": 800})
        page.evaluate(
            """() => {
            document.documentElement.classList.remove('theme-light');
            document.documentElement.classList.remove('light');
            document.body && document.body.classList.remove('light');
            try { localStorage.setItem('cockpit-theme', 'dark'); } catch(e) {}
        }"""
        )
        page.wait_for_timeout(800)
        p2 = OUT / "f6_bu_dark_375.png"
        page.screenshot(path=str(p2), full_page=False)
        log.append(f"shot {p2} bytes={p2.stat().st_size}")

        browser.close()

    (SCRATCH / "playwright_task53.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    if not (OUT / "f6_bu_light_1440.png").is_file() or not (OUT / "f6_bu_dark_375.png").is_file():
        return 1
    if (OUT / "f6_bu_light_1440.png").stat().st_size < 5000:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
