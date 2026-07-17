#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54.1：V1–V8 视觉证据（Playwright）。

用法（Vue 服务已起 :8018）:
  KANBAN_FRONTEND=vue KANBAN_OFFLINE=1 .venv/bin/python run.py --serve
  .venv/bin/python tests/frontend/playwright_task54p1_pixel.py [SCRATCH]

V8：等 animationDuration+300 再拍，杜绝空图。
产出：docs/pixel/vue54p1/
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54p1"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-65014ff4eca3/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
LEGACY_BASE = os.environ.get("KANBAN_LEGACY_BASE", "http://127.0.0.1:8019")
ACCT = os.environ.get("KANBAN_ACCT_OVERALL", "123")
PW = os.environ.get("KANBAN_PW_OVERALL", "8888")
# 图表入场动画约 800ms + 缓冲（任务书 V8）
ANIM_WAIT_MS = int(os.environ.get("KANBAN_ANIM_WAIT_MS", "1100"))
log: list[str] = []


def pick_account() -> None:
    global ACCT, PW
    try:
        acc_path = ROOT / "数据" / "看板账号.json"
        if not acc_path.is_file():
            return
        data = json.loads(acc_path.read_text(encoding="utf-8"))
        rows = data.get("accounts") or []
        for want in (ACCT, "123", "overall", "lushasha"):
            for a in rows:
                if a.get("账号") == want and str(a.get("密码") or "").strip():
                    ACCT = want
                    PW = str(a["密码"])
                    return
    except Exception as e:
        log.append(f"account pick fail: {e}")


def shot(page, name: str, full: bool = True) -> Path:
    p = OUT / name
    page.screenshot(path=str(p), full_page=full)
    log.append(f"shot {p.name} ({p.stat().st_size}b)")
    return p


def wait_anim(page) -> None:
    """V8：等动画结束再拍。"""
    page.wait_for_timeout(ANIM_WAIT_MS)


def set_theme(page, light: bool) -> None:
    page.evaluate(
        """(light) => {
      const r = document.documentElement;
      if (light) r.classList.add('theme-light'); else r.classList.remove('theme-light');
      try { localStorage.setItem('cockpit-theme', light ? 'light' : 'dark'); } catch(e) {}
      window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light } }));
    }""",
        light,
    )
    page.wait_for_timeout(500)
    wait_anim(page)


def login(page, base: str = BASE) -> None:
    page.goto(f"{base}/login", wait_until="networkidle", timeout=60000)
    for sel in ("input[type=text]", "#account", "input"):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.fill(ACCT)
                break
        except Exception:
            pass
    for sel in ("input[type=password]", "#password"):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.fill(PW)
                break
        except Exception:
            pass
    clicked = False
    for sel in ("button:has-text('登录')", "button[type=submit]", "button"):
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click()
                clicked = True
                break
        except Exception:
            pass
    if not clicked:
        page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    page.goto(f"{base}/", wait_until="networkidle", timeout=90000)
    page.wait_for_load_state("networkidle")
    wait_anim(page)
    page.wait_for_timeout(800)
    log.append(f"login ok base={base} url={page.url}")


def card_shots(page, prefix: str) -> None:
    selectors = {
        "kpi": ".kpi-host, .kpi-grid",
        "sec": "section.sec, .sec",
        "trend": "#trendChartCard, .trend-chart-card, [data-chart=trend]",
        "pl": ".pl-card, .scifi-panel.pl-card",
        "expense_donut": ".exp-donut-card",
        "expense_trend": "#expTrendCard, .exp-trend-card, [data-chart=expense-trend]",
        "rank": "#rankViews, .dual-rankings",
        "receipts": "#receiptsCard, .rc-card, [data-chart=receipts]",
    }
    for key, sel in selectors.items():
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                log.append(f"skip {prefix}_{key}")
                continue
            loc.scroll_into_view_if_needed()
            wait_anim(page)
            path = OUT / f"{prefix}_{key}.png"
            loc.screenshot(path=str(path))
            log.append(f"card {path.name} ({path.stat().st_size}b)")
        except Exception as e:
            log.append(f"card fail {prefix}_{key}: {e}")


def collect_console(page) -> list[str]:
    errs: list[str] = []

    def on_console(msg):
        if msg.type == "error":
            errs.append(msg.text)

    page.on("console", on_console)
    return errs


def main() -> int:
    pick_account()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        (SCRATCH / "playwright_error.log").write_text(f"import fail: {e}\n", encoding="utf-8")
        print("PLAYWRIGHT_IMPORT_FAIL", e)
        return 2

    console_errs: list[str] = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            (SCRATCH / "playwright_error.log").write_text(f"launch fail: {e}\n", encoding="utf-8")
            print("PLAYWRIGHT_LAUNCH_FAIL", e)
            return 2

        # ---- Vue overall light/dark × 1440/375 ----
        for w, h, tag in ((1440, 900, "1440"), (375, 812, "375")):
            page = browser.new_page(viewport={"width": w, "height": h})
            errs = collect_console(page)
            try:
                login(page)
                for light, mode in ((False, "dark"), (True, "light")):
                    set_theme(page, light)
                    wait_anim(page)
                    shot(page, f"vue_overall_{mode}_{tag}.png", full=True)
                    if tag == "1440":
                        card_shots(page, f"vue_overall_{mode}")
            except Exception as e:
                log.append(f"overall {tag} fail: {e}")
                try:
                    shot(page, f"FAIL_overall_{tag}.png", full=False)
                except Exception:
                    pass
            console_errs.extend(errs)
            page.close()

        # ---- V8 resize: large then shrink ----
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        try:
            login(page)
            set_theme(page, False)
            wait_anim(page)
            page.locator("#trendChartCard, .trend-chart-card").first.scroll_into_view_if_needed()
            wait_anim(page)
            shot(page, "v8_resize_before_1600.png", full=False)
            page.set_viewport_size({"width": 900, "height": 700})
            page.wait_for_timeout(600)
            wait_anim(page)
            shot(page, "v8_resize_after_900.png", full=False)
            # 费用折线特写
            page.locator("#expTrendCard").first.scroll_into_view_if_needed()
            wait_anim(page)
            page.locator("#expTrendCard").first.screenshot(path=str(OUT / "v7_expense_trend_line.png"))
            log.append("v7 expense line + v8 resize done")
        except Exception as e:
            log.append(f"v8 resize fail: {e}")
        page.close()

        # ---- Legacy compare (if 8019 up) ----
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.goto(LEGACY_BASE + "/login", wait_until="domcontentloaded", timeout=15000)
            login(page, LEGACY_BASE)
            set_theme(page, False)
            wait_anim(page)
            shot(page, "compare_legacy_overall_dark_1440.png", full=False)
            for name, sel in (
                ("compare_legacy_kpi", ".kpi-grid"),
                ("compare_legacy_sec", ".sec"),
                ("compare_legacy_pl", ".pl-card, .pl"),
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.scroll_into_view_if_needed()
                        loc.screenshot(path=str(OUT / f"{name}.png"))
                        log.append(f"legacy {name}")
                except Exception as e:
                    log.append(f"legacy skip {name}: {e}")
        except Exception as e:
            log.append(f"legacy compare skip: {e}")
        page.close()

        # Vue compare counterparts
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            login(page)
            set_theme(page, False)
            wait_anim(page)
            shot(page, "compare_vue_overall_dark_1440.png", full=False)
            for name, sel in (
                ("compare_vue_kpi", ".kpi-grid"),
                ("compare_vue_sec", "section.sec, .sec"),
                ("compare_vue_pl", ".pl-card"),
                ("compare_vue_expense", "#expTrendCard"),
                ("compare_vue_trend", "#trendChartCard"),
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.scroll_into_view_if_needed()
                        wait_anim(page)
                        loc.screenshot(path=str(OUT / f"{name}.png"))
                        log.append(f"vue compare {name}")
                except Exception as e:
                    log.append(f"vue skip {name}: {e}")
        except Exception as e:
            log.append(f"vue compare fail: {e}")
        page.close()

        browser.close()

    (SCRATCH / "playwright_task54p1.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    err_path = SCRATCH / "console_errors.txt"
    # filter noise
    real_errs = [e for e in console_errs if e and "favicon" not in e.lower()]
    err_path.write_text("\n".join(real_errs) + "\n", encoding="utf-8")
    pngs = list(OUT.glob("*.png"))
    (OUT / "README.md").write_text(
        "# vue54p1 像素证据（任务书54.1 · B0 人审打回视觉整改）\n\n"
        "- 亮/暗 × 1440/375：`vue_overall_{dark|light}_{1440|375}.png`\n"
        "- 逐卡：`vue_overall_{mode}_{kpi|sec|trend|pl|expense_*|rank|receipts}.png`\n"
        "- V7 费用折线：`v7_expense_trend_line.png`\n"
        "- V8 resize：`v8_resize_before_1600.png` / `v8_resize_after_900.png`\n"
        "- legacy 对照：`compare_legacy_*` / `compare_vue_*`\n"
        f"- ANIM_WAIT_MS={ANIM_WAIT_MS}\n"
        f"- 文件数：{len(pngs)}\n"
        f"- 控制台错误数：{len(real_errs)}\n",
        encoding="utf-8",
    )
    print("OK shots", len(pngs), "console_errs", len(real_errs))
    print("\n".join(log[-40:]))
    if real_errs:
        print("CONSOLE_ERRORS:")
        print("\n".join(real_errs[:20]))
    return 0 if not real_errs else 0  # 截图优先；控制台记入证据


if __name__ == "__main__":
    raise SystemExit(main())
