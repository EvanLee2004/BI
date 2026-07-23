#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.2 管理利润表视觉截图（三主题）：毛利/毛利率/税前利润率绿 + 成本抽屉两减项负号。

用法：
  KANBAN_BASE=http://127.0.0.1:8765 .venv/bin/python scripts/capture_2_3_2_pl_visual.py

输出（含数据，不进 git）：
  docs/_visual_2_3_2/{neon,dark,light}/pl_main.png
  docs/_visual_2_3_2/{neon,dark,light}/pl_cost_drawer.png
  docs/_visual_2_3_2/{neon,dark,light}/pl_bu.png
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8765")
VIS = ROOT / "docs" / "_visual_2_3_2"
THEMES = ("neon", "dark", "light")
SCRATCH = Path(
    os.environ.get(
        "SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-76ba652332be/implementer",
    )
)


def load_accounts():
    # 服务端用 config data_dir；本机默认 数据/，优先与服务一致
    for path in (ROOT / "数据" / "看板账号.json", ROOT / "_golden_data" / "看板账号.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")).get("accounts") or []
    return []


def pick(kind: str):
    rows = load_accounts()
    if kind == "bu":
        for a in rows:
            p = str(a.get("权限") or "")
            if p not in ("管理员", "整体", "") and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
        return "zhengrui", "8888"
    # 整体：先精确账号，再权限=整体，最后管理员
    for a in rows:
        if a.get("账号") in ("overall", "123") and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    for a in rows:
        if a.get("权限") == "整体" and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    for a in rows:
        if a.get("权限") == "管理员" and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "123", "8888"


def fill_login(page, acc, pw):
    page.wait_for_timeout(300)
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
    page.locator(
        "button:has-text('进入'), button:has-text('登录'), button[type=submit]"
    ).first.click()


def apply_theme(page, target: str, max_clicks: int = 6) -> str:
    def cur() -> str:
        return page.evaluate(
            "() => document.documentElement.dataset.theme || "
            "(document.documentElement.classList.contains('theme-light') ? 'light' : 'dark')"
        )

    for _ in range(max_clicks):
        if cur() == target:
            return cur()
        btn = page.locator(
            "button:has-text('浅色'), button:has-text('深色'), "
            "button:has-text('霓虹'), button:has-text('亮/暗')"
        )
        if btn.count() == 0:
            break
        btn.first.click()
        page.wait_for_timeout(200)
    return cur()


def scroll_pl(page):
    page.evaluate(
        """() => {
      const el = document.querySelector('.pl-card, [class*=pl-card], .scifi-panel.pl-card');
      if (el) el.scrollIntoView({block:'center'});
    }"""
    )
    page.wait_for_timeout(300)


def open_cost_drawer(page) -> bool:
    # 点「交付成本」行的查看构成
    hints = page.locator(".pl-row:has-text('交付成本') .pl-open-hint, .pl-row:has-text('交付成本')")
    if hints.count() == 0:
        return False
    hints.first.click()
    page.wait_for_timeout(400)
    return page.locator(".drawer.open, .drawer-panel, [data-testid=drawer-panel]").count() > 0


def close_drawer(page):
    if page.locator("button:has-text('关闭')").count():
        page.locator("button:has-text('关闭')").first.click()
        page.wait_for_timeout(200)
    elif page.locator("[data-testid=drawer-mask]").count():
        page.locator("[data-testid=drawer-mask]").first.click()
        page.wait_for_timeout(200)


def assert_pl_texts(page) -> dict:
    body = page.inner_text("body")
    return {
        "has_maoli": "毛利" in body,
        "has_maolilv": "毛利率" in body,
        "no_guanli_maoli": "管理毛利" not in body,
        "has_pretax_pct": "税前利润率" in body,
    }


def capture_theme(page, theme: str, out_dir: Path, label: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    got = apply_theme(page, theme)
    scroll_pl(page)
    page.screenshot(path=str(out_dir / f"pl_{label}.png"), full_page=False)
    opened = open_cost_drawer(page)
    if opened:
        page.screenshot(path=str(out_dir / f"pl_cost_drawer_{label}.png"), full_page=False)
        close_drawer(page)
    return {"theme_applied": got, "drawer_opened": opened, **assert_pl_texts(page)}


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        msg = "playwright not installed"
        (SCRATCH / "browser_limit.txt").write_text(msg, encoding="utf-8")
        print(msg)
        return 2

    report = {"base": BASE, "themes": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # overall
        acc, pw = pick("overall")
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        fill_login(page, acc, pw)
        page.wait_for_timeout(2500)
        for th in THEMES:
            report["themes"][f"overall_{th}"] = capture_theme(
                page, th, VIS / th, "main"
            )
        # BU
        page.goto(BASE + "/logout", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(500)
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        bacc, bpw = pick("bu")
        fill_login(page, bacc, bpw)
        page.wait_for_timeout(2500)
        for th in THEMES:
            report["themes"][f"bu_{th}"] = capture_theme(page, th, VIS / th, "bu")
        browser.close()

    out = SCRATCH / "capture_2_3_2_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("shots under", VIS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
