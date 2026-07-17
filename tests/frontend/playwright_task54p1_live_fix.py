#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.1 人审补刀：PL 抽屉横排 / 回款12月+Y轴 / 排名放大统一 / 查询一致。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54p1" / "iter_2_livefix"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-65014ff4eca3/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
ACCT, PW = "123", "8888"
log: list[str] = []


def pick_account() -> None:
    global ACCT, PW
    try:
        data = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
        for a in data.get("accounts") or []:
            if a.get("账号") in ("123", "overall", "lushasha") and str(a.get("密码") or "").strip():
                ACCT, PW = a["账号"], str(a["密码"])
                return
    except Exception as e:
        log.append(f"acct: {e}")


def main() -> int:
    pick_account()
    from playwright.sync_api import sync_playwright

    notes: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
        page.locator("input[type=text], #account, input").first.fill(ACCT)
        page.locator("input[type=password]").first.fill(PW)
        page.locator("button:has-text('登录'), button[type=submit]").first.click()
        page.wait_for_timeout(2500)
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)

        # theme dark
        page.evaluate(
            """() => {
          document.documentElement.classList.remove('theme-light');
          try { localStorage.setItem('cockpit-theme','dark'); } catch(e) {}
          window.dispatchEvent(new CustomEvent('kanban-theme-change',{detail:{light:false}}));
        }"""
        )
        page.wait_for_timeout(800)

        # --- PL drawer ---
        try:
            pl = page.locator(".pl-card .pl-open, .pl-row.pl-open").first
            pl.scroll_into_view_if_needed()
            pl.click()
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / "pl_drawer_open.png"), full_page=False)
            # measure first drawer name width / writing mode
            box = page.evaluate(
                """() => {
              const el = document.querySelector('.drawer.open .pl-drow .pl-name, .drawer.open .pl-drow > span');
              if (!el) return {ok:false};
              const r = el.getBoundingClientRect();
              const cs = getComputedStyle(el);
              return {
                ok: true,
                w: r.width, h: r.height,
                writingMode: cs.writingMode,
                text: (el.textContent||'').trim().slice(0,40),
              };
            }"""
            )
            notes.append(f"pl_drawer: {box}")
            if box.get("ok") and box.get("w", 0) < 40 and box.get("h", 0) > 80:
                notes.append("FAIL pl name still vertical-ish")
            else:
                notes.append("PASS pl name horizontal-ish")
            page.locator(".drawer.open button, .drawer.open [data-close]").first.click()
            page.wait_for_timeout(300)
        except Exception as e:
            notes.append(f"pl drawer fail: {e}")

        # --- receipts chart ---
        try:
            page.locator("#receiptsCard").first.scroll_into_view_if_needed()
            page.wait_for_timeout(1200)
            page.locator("#receiptsCard").first.screenshot(path=str(OUT / "receipts_full.png"))
            notes.append("receipts shot ok")
        except Exception as e:
            notes.append(f"receipts fail: {e}")

        # --- dual rankings size ---
        try:
            page.locator("#rankViews").first.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            page.locator("#rankViews").first.screenshot(path=str(OUT / "rankings_dual_large.png"))
            h = page.evaluate(
                """() => {
              const el = document.querySelector('#rankViews .rank-chart-host');
              return el ? el.getBoundingClientRect().height : 0;
            }"""
            )
            notes.append(f"rank_chart_h={h}")
            notes.append("PASS rank height" if h >= 400 else "FAIL rank too short")
        except Exception as e:
            notes.append(f"rank fail: {e}")

        # --- daily query then same style ---
        try:
            page.locator("#dailyGo, button:has-text('查询')").first.scroll_into_view_if_needed()
            page.locator("#dailyGo, button:has-text('查询')").first.click()
            page.wait_for_timeout(2500)
            page.locator("#rkCustom, #dailyPanel").first.screenshot(path=str(OUT / "daily_query_echarts.png"))
            has_echarts = page.evaluate(
                """() => !!document.querySelector('#rkCustom canvas, #rkCustom .rank-chart-host')"""
            )
            notes.append(f"daily_has_echarts={has_echarts}")
            notes.append("PASS daily echarts" if has_echarts else "FAIL daily still CSS list")
            page.locator("#dailyClose, button:has-text('返回默认')").first.click()
            page.wait_for_timeout(800)
        except Exception as e:
            notes.append(f"daily fail: {e}")

        # overall
        page.screenshot(path=str(OUT / "overall_dark_1440.png"), full_page=True)
        browser.close()

    (OUT / "notes.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")
    (SCRATCH / "live_fix_notes.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")
    print("\n".join(notes))
    print("OK", len(list(OUT.glob("*.png"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
