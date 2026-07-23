#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.4 人审截图：自定义区间无快捷墙 + 纯 BU 账号不显「← 整体」。

用法（程序根）：
  OUT_DIR=... KANBAN_BASE=http://127.0.0.1:8029 .venv/bin/python scripts/snap_2_3_4_ui_check.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8029").rstrip("/")
OUT = Path(os.environ.get("OUT_DIR", ROOT / "docs" / "_visual_2_3_4"))
OUT.mkdir(parents=True, exist_ok=True)


def _login(page, account: str, password: str) -> None:
    page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(400)
    # skip intro if any
    skip = page.locator("text=跳过, button:has-text('跳过')")
    if skip.count():
        try:
            skip.first.click(timeout=1500)
        except Exception:
            pass
    page.locator("input").first.fill(account)
    page.locator("input[type=password]").fill(password)
    page.locator("button:has-text('进入'), button:has-text('登录')").first.click()
    page.wait_for_timeout(800)
    # dismiss intro splash if present
    for _ in range(6):
        if page.locator("[data-testid=period-picker], .kpi-grid, .tb-title").count():
            break
        skip2 = page.locator("button:has-text('跳过'), text=跳过")
        if skip2.count():
            try:
                skip2.first.click(timeout=800)
            except Exception:
                pass
        page.wait_for_timeout(500)
    page.wait_for_selector("[data-testid=period-picker], .kpi-grid, .tb-title", timeout=60000)


def main() -> int:
    report: dict = {"base": BASE, "shots": [], "checks": {}}
    overall_acc, overall_pw = "overall", "8888"
    bu_acc, bu_pw = "bu_only", "8888"
    # prefer golden accounts file
    for p in (ROOT / "_golden_data" / "看板账号.json", ROOT / "数据" / "看板账号.json"):
        if not p.is_file():
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        accs = raw.get("accounts") if isinstance(raw, dict) else raw
        for a in accs or []:
            if a.get("账号") == "overall" and a.get("密码"):
                overall_acc, overall_pw = "overall", str(a["密码"])
            if a.get("账号") == "bu_only" and a.get("密码"):
                bu_acc, bu_pw = "bu_only", str(a["密码"])
        break

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # ── A. 整体账号：自定义区间 UI ──
        _login(page, overall_acc, overall_pw)
        # skip intro animation if still on
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
        page.wait_for_selector(".pp-panel", timeout=8000)
        page.locator(".pp-tab:has-text('自定义')").click()
        page.wait_for_timeout(250)
        n_list = page.locator(".pp-custom-list .pp-opt").count()
        n_filter = page.locator("[data-testid=period-custom-filter]").count()
        n_apply = page.locator("[data-testid=period-apply], .pp-apply").count()
        shot_a = OUT / "A_custom_period_no_shortcut_wall.png"
        page.screenshot(path=str(shot_a), full_page=False)
        report["shots"].append(str(shot_a))
        report["checks"]["custom_shortcut_wall_count"] = n_list
        report["checks"]["custom_filter_panel"] = n_filter
        report["checks"]["custom_apply_btn"] = n_apply
        report["checks"]["custom_ok"] = n_list == 0 and n_filter >= 1 and n_apply >= 1

        # ── B. 纯 BU 账号：无「← 整体」──
        ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
        page2 = ctx2.new_page()
        _login(page2, bu_acc, bu_pw)
        page2.keyboard.press("Escape")
        page2.wait_for_timeout(500)
        # wait session-driven canMain settle
        page2.wait_for_timeout(800)
        back = page2.locator("[data-testid=bu-back-overall]")
        n_back = back.count()
        # also text fallback（避免 CSS 解析 text= 与箭头）
        n_back_text = page2.get_by_text("← 整体", exact=False).count()
        shot_b = OUT / "B_bu_only_no_overall_back.png"
        page2.screenshot(path=str(shot_b), full_page=False)
        report["shots"].append(str(shot_b))
        report["checks"]["bu_back_testid"] = n_back
        report["checks"]["bu_back_textish"] = n_back_text
        report["checks"]["bu_ok"] = n_back == 0
        # page title should be some BU
        title = page2.locator(".tb-title").inner_text() if page2.locator(".tb-title").count() else ""
        report["checks"]["bu_title"] = title.strip()[:80]
        # URL should be /bu/...
        report["checks"]["bu_url"] = page2.url

        # ── C. 整体账号进某个 BU 应能看到「← 整体」──
        page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)
        # click first BU nav if any
        bu_links = page.locator("a[href^='/bu/'], .bu-nav a, [data-testid=bu-nav] a")
        if bu_links.count() == 0:
            # try navigate known golden BU
            page.goto(f"{BASE}/bu/{__import__('urllib.parse').quote('营销')}", wait_until="domcontentloaded")
        else:
            bu_links.first.click()
        page.wait_for_timeout(1200)
        n_back_overall = page.locator("[data-testid=bu-back-overall]").count()
        shot_c = OUT / "C_overall_user_on_bu_has_back.png"
        page.screenshot(path=str(shot_c), full_page=False)
        report["shots"].append(str(shot_c))
        report["checks"]["overall_on_bu_back"] = n_back_overall
        report["checks"]["overall_on_bu_ok"] = n_back_overall >= 1

        browser.close()

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = (
        report["checks"].get("custom_ok")
        and report["checks"].get("bu_ok")
        and report["checks"].get("overall_on_bu_ok")
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
