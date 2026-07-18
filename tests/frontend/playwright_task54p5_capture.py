#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.5 视口内截图。用法：服务已起 8018 + data_dir=_golden_data
  .venv/bin/python tests/frontend/playwright_task54p5_capture.py [screen_id] [SCRATCH]
screen_id: home_dark_1440 | home_375 | home_light_1440 | bu | detail_table |
           admin_console | admin_manual | admin_budget | admin_detail | admin_settings | all
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54p5"
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
SCRATCH = Path(
    sys.argv[2]
    if len(sys.argv) > 2
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-d3684c723f46/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
SCREEN = sys.argv[1] if len(sys.argv) > 1 else "all"


def load_accounts():
    for path in (ROOT / "_golden_data" / "看板账号.json", ROOT / "数据" / "看板账号.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")).get("accounts") or []
    return []


def pick(kind: str):
    rows = load_accounts()
    if kind == "admin":
        for a in rows:
            if a.get("权限") == "管理员" and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
        return "lushasha", "kanban2026"
    if kind == "bu":
        for a in rows:
            p = str(a.get("权限") or "")
            if p not in ("管理员", "整体", "") and a.get("密码"):
                bus = a.get("可见BU") or ([p] if p not in ("BU",) else [])
                return str(a["账号"]), str(a["密码"]), bus
        return "bu_only", "8888", ["示意BU甲"]
    for a in rows:
        if a.get("账号") in ("overall", "123") and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "overall", "8888"


def fill_login(page, acc, pw):
    if page.locator("input[type=password]").count():
        for i in range(page.locator("input").count()):
            el = page.locator("input").nth(i)
            t = (el.get_attribute("type") or "text").lower()
            if t != "password":
                try:
                    el.fill(acc)
                    break
                except Exception:
                    pass
        page.locator("input[type=password]").first.fill(pw)
    else:
        page.locator("input").first.fill(acc)
        page.locator("input").nth(1).fill(pw)


def click_login(page):
    for sel in (
        "button:has-text('进入')",
        "button:has-text('登录')",
        "button[type=submit]",
        ".el-button--primary",
    ):
        if page.locator(sel).count():
            page.locator(sel).first.click()
            return


def viewer_login(page, acc, pw):
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(400)
    fill_login(page, acc, pw)
    click_login(page)
    page.wait_for_load_state("networkidle", timeout=90000)
    page.wait_for_timeout(1000)


def admin_login(page, acc, pw):
    page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(400)
    fill_login(page, acc, pw)
    click_login(page)
    page.wait_for_load_state("networkidle", timeout=90000)
    page.wait_for_timeout(1000)


def shot(page, screen: str, name: str = "viewport.png"):
    d = OUT / screen
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    # 视口内，禁止 full_page 当主证据
    page.screenshot(path=str(p), full_page=False)
    return p


def capture(page, screen: str, name: str = "viewport.png") -> Path:
    page.wait_for_timeout(800)
    p = shot(page, screen, name)
    meta = {
        "url": page.url,
        "viewport": page.viewport_size,
        "file": str(p.relative_to(ROOT)),
        "bytes": p.stat().st_size,
    }
    (OUT / screen / "capture_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False))
    return p


def run_one(pw, screen: str):
    browser = pw.chromium.launch(headless=True)
    try:
        if screen == "home_dark_1440":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            acc, pw = pick("overall")
            viewer_login(page, acc, pw)
            page.wait_for_timeout(1200)
            capture(page, screen)
        elif screen == "home_375":
            page = browser.new_page(viewport={"width": 375, "height": 812})
            acc, pw = pick("overall")
            viewer_login(page, acc, pw)
            page.wait_for_timeout(1200)
            capture(page, screen)
        elif screen == "home_light_1440":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            acc, pw = pick("overall")
            viewer_login(page, acc, pw)
            page.wait_for_timeout(800)
            for sel in (
                "button:has-text('亮')",
                "button:has-text('亮/暗')",
                "[title*=亮]",
                ".tb-theme",
                "text=亮/暗",
            ):
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    page.wait_for_timeout(600)
                    break
            capture(page, screen)
        elif screen == "home_light_375":
            page = browser.new_page(viewport={"width": 375, "height": 812})
            acc, pw = pick("overall")
            viewer_login(page, acc, pw)
            for sel in ("button:has-text('亮')", ".tb-theme", "text=亮/暗"):
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    page.wait_for_timeout(600)
                    break
            capture(page, screen)
        elif screen == "bu":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            bacc, bpw, bus = pick("bu")
            viewer_login(page, bacc, bpw)
            bu = (bus or ["示意BU甲"])[0]
            page.goto(
                f"{BASE}/bu/{urllib.parse.quote(bu)}",
                wait_until="networkidle",
                timeout=90000,
            )
            page.wait_for_timeout(1500)
            capture(page, screen)
        elif screen == "detail_table":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            acc, pw = pick("overall")
            viewer_login(page, acc, pw)
            page.wait_for_timeout(800)
            # 滚到明细区
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            capture(page, screen)
        elif screen == "admin_console":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            a, p_ = pick("admin")
            admin_login(page, a, p_)
            page.goto(f"{BASE}/admin", wait_until="networkidle")
            page.wait_for_timeout(1000)
            capture(page, screen)
        elif screen == "admin_manual":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            a, p_ = pick("admin")
            admin_login(page, a, p_)
            page.goto(f"{BASE}/admin/edit/manual", wait_until="networkidle")
            page.wait_for_timeout(1000)
            capture(page, screen)
        elif screen == "admin_budget":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            a, p_ = pick("admin")
            admin_login(page, a, p_)
            page.goto(f"{BASE}/admin/edit/budget", wait_until="networkidle")
            page.wait_for_timeout(1000)
            capture(page, screen)
        elif screen == "admin_detail":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            a, p_ = pick("admin")
            admin_login(page, a, p_)
            page.goto(f"{BASE}/admin/edit/detail", wait_until="networkidle")
            page.wait_for_timeout(1000)
            capture(page, screen)
        elif screen == "admin_settings":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            a, p_ = pick("admin")
            admin_login(page, a, p_)
            page.goto(f"{BASE}/admin/settings", wait_until="networkidle")
            page.wait_for_timeout(1000)
            capture(page, screen)
        elif screen == "admin_console_light":
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            a, p_ = pick("admin")
            admin_login(page, a, p_)
            page.goto(f"{BASE}/admin", wait_until="networkidle")
            page.wait_for_timeout(600)
            for sel in ("text=浅色", "button:has-text('浅')", ".theme-toggle"):
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    page.wait_for_timeout(500)
                    break
            capture(page, screen)
        else:
            raise SystemExit(f"unknown screen {screen}")
    finally:
        browser.close()


def main() -> int:
    from playwright.sync_api import sync_playwright

    screens = (
        [
            "home_dark_1440",
            "home_375",
            "home_light_1440",
            "home_light_375",
            "bu",
            "detail_table",
            "admin_console",
            "admin_manual",
            "admin_budget",
            "admin_detail",
            "admin_settings",
            "admin_console_light",
        ]
        if SCREEN == "all"
        else [SCREEN]
    )
    with sync_playwright() as p:
        for s in screens:
            print("===", s)
            try:
                run_one(p, s)
            except Exception as e:
                (SCRATCH / f"capture_fail_{s}.log").write_text(str(e), encoding="utf-8")
                print("FAIL", s, e)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
