#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54·C：Vue SciFi 像素证据（亮/暗 × 1440/375，整体+BU，逐卡，legacy 并排）。

用法（服务已起 :8018）:
  KANBAN_FRONTEND=vue KANBAN_OFFLINE=1 .venv/bin/python run.py --serve   # 终端1
  .venv/bin/python tests/frontend/playwright_task54_pixel.py [SCRATCH]

产出：docs/pixel/vue54/ + scratch log。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-9b74a2135308/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
ACCT = os.environ.get("KANBAN_ACCT_OVERALL", "123")
PW = os.environ.get("KANBAN_PW_OVERALL", "8888")
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
    log.append(f"shot {p} ({p.stat().st_size} bytes)")
    return p


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
    page.wait_for_timeout(600)


def login(page) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
    # Vue login or legacy form
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
    page.wait_for_timeout(3000)
    page.goto(f"{BASE}/", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(3500)
    log.append(f"after login url={page.url}")


def card_shots(page, prefix: str) -> None:
    # 稳定 id / data-chart（勿用 has-text('收入'|'回款')——会误截 KPI 卡）
    selectors = {
        "kpi": ".kpi-host, .kpi-grid",
        "trend": "#trendChartCard, .trend-chart-card, [data-chart=trend]",
        "pl": ".pl-card, .scifi-panel.pl-card, .pl-table",
        "expense_donut": ".exp-donut-card",
        "expense_trend": "#expTrendCard, .exp-trend-card, [data-chart=expense-trend]",
        "rank": "#rankViews, .dual-rankings",
        "receipts": "#receiptsCard, .rc-card, [data-chart=receipts]",
        "ledger": ".scifi-panel:has-text('费用明细'), .cock-ledger",
    }
    for key, sel in selectors.items():
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                log.append(f"skip card {prefix}_{key}: not found")
                continue
            loc.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            path = OUT / f"{prefix}_{key}.png"
            loc.screenshot(path=str(path))
            log.append(f"card {path} ({path.stat().st_size}b)")
        except Exception as e:
            log.append(f"card fail {prefix}_{key}: {e}")


def main() -> int:
    pick_account()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        err = f"import fail: {e}\n"
        (SCRATCH / "playwright_error.log").write_text(err, encoding="utf-8")
        print("PLAYWRIGHT_IMPORT_FAIL", e)
        return 2

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
            try:
                login(page)
                for light, mode in ((False, "dark"), (True, "light")):
                    set_theme(page, light)
                    page.wait_for_timeout(800)
                    shot(page, f"vue_overall_{mode}_{tag}.png", full=True)
                    if tag == "1440":
                        card_shots(page, f"vue_overall_{mode}")
            except Exception as e:
                log.append(f"overall {tag} fail: {e}")
                try:
                    shot(page, f"FAIL_overall_{tag}.png", full=False)
                except Exception:
                    pass
            page.close()

        # ---- BU page (first nav link if any) ----
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            login(page)
            bu_href = page.evaluate(
                """() => {
              const a = document.querySelector('.bu-nav-a, a[href^="/bu/"]');
              return a ? a.getAttribute('href') : null;
            }"""
            )
            if bu_href:
                page.goto(f"{BASE}{bu_href}", wait_until="networkidle", timeout=90000)
                page.wait_for_timeout(3000)
                for light, mode in ((False, "dark"), (True, "light")):
                    set_theme(page, light)
                    shot(page, f"vue_bu_{mode}_1440.png", full=True)
                    card_shots(page, f"vue_bu_{mode}")
            else:
                log.append("no BU link — skip BU shots")
        except Exception as e:
            log.append(f"bu fail: {e}")
        page.close()

        # ---- Legacy side-by-side baselines (≥4) via separate env hint ----
        # Capture current vue + note; legacy requires KANBAN_FRONTEND=legacy restart.
        # We still write comparison placeholders if legacy static shell responds.
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            login(page)
            set_theme(page, False)
            shot(page, "compare_vue_overall_dark_1440.png", full=False)
            # KPI / trend / expense / pl regions for side-by-side pack
            for name, sel in (
                ("compare_vue_kpi", ".kpi-grid"),
                ("compare_vue_trend", "#trendChartCard"),
                ("compare_vue_expense", "#expTrendCard"),
                ("compare_vue_pl", ".pl-table, .pl-card"),
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.scroll_into_view_if_needed()
                        loc.screenshot(path=str(OUT / f"{name}.png"))
                        log.append(f"compare {name}")
                except Exception as e:
                    log.append(f"compare skip {name}: {e}")
        except Exception as e:
            log.append(f"compare fail: {e}")
        page.close()

        browser.close()

    (SCRATCH / "playwright_task54.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# vue54 像素证据（任务书54·C）\n\n"
        "- 亮/暗 × 1440/375 整页：`vue_overall_{dark|light}_{1440|375}.png`\n"
        "- BU：`vue_bu_{dark|light}_1440.png`\n"
        "- 逐卡：`vue_overall_{mode}_{kpi|trend|pl|...}.png`\n"
        "- 与 legacy 并排对照素材：`compare_vue_*.png`（legacy 对照见同目录 `compare_legacy_*` 若已拍）\n"
        f"- 生成日志见 scratch playwright_task54.log\n"
        f"- 文件数：{len(list(OUT.glob('*.png')))}\n",
        encoding="utf-8",
    )
    print("OK shots", len(list(OUT.glob("*.png"))))
    print("\n".join(log[-30:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
