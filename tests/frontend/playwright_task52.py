#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书52：Playwright 活体证据（F-1 弹窗 / F-2 PL 布局 / F-4 面积轴）。

用法（服务已起 :8018，KANBAN_OFFLINE=1）:
  .venv/bin/python tests/frontend/playwright_task52.py [SCRATCH_DIR]

账号：overall / 8888（seed 默认整体）；若本机改过密码请设环境变量
  KANBAN_PW_OVERALL / KANBAN_ACCT_OVERALL
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-77a6942e8614/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
# 优先 123（整体），再 overall，再 seed 默认
ACCT = os.environ.get("KANBAN_ACCT_OVERALL", "123")
PW = os.environ.get("KANBAN_PW_OVERALL", "8888")
try:
    acc_path = ROOT / "数据" / "看板账号.json"
    if acc_path.is_file():
        data = json.loads(acc_path.read_text(encoding="utf-8"))
        rows = data.get("accounts") or []
        preferred = [ACCT, "123", "overall"]
        for want in preferred:
            for a in rows:
                if a.get("账号") == want and str(a.get("密码") or "").strip():
                    ACCT = want
                    PW = str(a["密码"])
                    break
            else:
                continue
            break
except Exception:
    pass


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        (SCRATCH / "playwright_env_fail.txt").write_text(f"import fail: {e}\n", encoding="utf-8")
        print("PLAYWRIGHT_IMPORT_FAIL", e)
        return 2

    log = []
    shots = []

    def shot(page, name):
        p = SCRATCH / name
        page.screenshot(path=str(p), full_page=False)
        shots.append(str(p))
        log.append(f"screenshot {p}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            (SCRATCH / "playwright_env_fail.txt").write_text(f"launch fail: {e}\n", encoding="utf-8")
            print("PLAYWRIGHT_LAUNCH_FAIL", e)
            return 2
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # login
        log.append(f"login as {ACCT}")
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
        page.fill("#account", ACCT)
        page.fill("#password", PW)
        page.click('button[type="submit"]')
        page.wait_for_timeout(2500)
        # Vue 壳在 / 或 /app/
        if "/login" in page.url:
            log.append("WARN still on login — retry goto /")
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(4000)
        log.append(f"url after login {page.url}")
        # 等 KPI/板块渲染
        try:
            page.wait_for_selector(".kpi-grid, .pl-card, .pl-table, #rankViews", timeout=30000)
        except Exception as e:
            log.append(f"WARN main selectors missing: {e}")
            shot(page, "login_land_fail.png")

        # ---- F-1 modal ----
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(800)
            btn = page.get_by_text("点开看明细", exact=False).first
            if btn.count() == 0:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)
                btn = page.get_by_text("点开看明细", exact=False).first
            btn.click(timeout=20000)
            page.wait_for_timeout(800)
            mask = page.locator(".rkm-mask").first
            mask.wait_for(state="visible", timeout=10000)
            pos = page.evaluate(
                """() => {
                const el = document.querySelector('.rkm-mask');
                if (!el) return null;
                const cs = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return {position: cs.position, top: r.top, left: r.left, w: r.width, h: r.height,
                        parent: el.parentElement && el.parentElement.tagName};
            }"""
            )
            log.append(f"F1 mask computed {pos}")
            assert pos and pos.get("position") == "fixed", pos
            assert pos.get("parent") == "BODY", pos
            assert pos.get("h", 0) > 100 and pos.get("top", 9999) < 200, pos
            shot(page, "f1_others_modal.png")
            # close ESC
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            log.append(f"F1 after ESC count={page.locator('.rkm-mask').count()}")
        except Exception as e:
            log.append(f"F1 FAIL {e}")
            shot(page, "f1_fail.png")

        # monthly drill if bar exists
        try:
            page.locator("#rankViews canvas, .dual-rankings canvas").first.click(timeout=8000, position={"x": 80, "y": 40})
            page.wait_for_timeout(600)
            if page.locator(".rkm-mask").count():
                shot(page, "f1_monthly_drill.png")
                page.keyboard.press("Escape")
                log.append("F1 monthly drill ok")
        except Exception as e:
            log.append(f"F1 monthly skip/fail {e}")

        # ---- F-2 PL layout ----
        for w, name in ((1440, "f2_pl_1440.png"), (1280, "f2_pl_1280.png"), (375, "f2_pl_375.png")):
            page.set_viewport_size({"width": w, "height": 900})
            page.wait_for_timeout(500)
            try:
                page.locator(".pl-card, .pl-table").first.scroll_into_view_if_needed(timeout=10000)
            except Exception as e:
                log.append(f"F2 scroll skip {e}")
            metrics = page.evaluate(
                """() => {
                const name = document.querySelector('.pl-table .pl-name, .pl-card .pl-name, .pl-name');
                if (!name) return null;
                const r = name.getBoundingClientRect();
                return {w: r.width, h: r.height, text: (name.textContent||'').slice(0,40)};
            }"""
            )
            log.append(f"F2 width={w} pl-name {metrics}")
            if metrics and metrics.get("w", 0) < 80:
                log.append(f"F2 FAIL pl-name too narrow at {w}: {metrics}")
            shot(page, name)

        # ---- F-4 area chart ----
        page.set_viewport_size({"width": 1440, "height": 900})
        try:
            page.locator("#expTrendCard, .exp-trend-card").first.scroll_into_view_if_needed()
            page.wait_for_timeout(800)
            shot(page, "f4_area_axis.png")
            # axis labels from option if echarts exposed — DOM text check hard; screenshot is evidence
            log.append("F4 area screenshot taken")
        except Exception as e:
            log.append(f"F4 fail {e}")

        # dark/light charts
        try:
            page.evaluate(
                """() => {
                document.documentElement.classList.toggle('light');
                document.body && document.body.classList.toggle('light');
            }"""
            )
            page.wait_for_timeout(500)
            shot(page, "f6_overall_light_1440.png")
            page.set_viewport_size({"width": 375, "height": 800})
            page.wait_for_timeout(400)
            shot(page, "f6_overall_375.png")
        except Exception as e:
            log.append(f"F6 theme shots {e}")

        browser.close()

    (SCRATCH / "playwright_task52.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    print("SCRATCH", SCRATCH)
    fails = [x for x in log if "FAIL" in x]
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
