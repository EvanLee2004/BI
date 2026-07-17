#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.2 自测截图 → 仅 SCRATCH（含真实数据，禁止 git）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-0a4e3ca51086/implementer"
)
OUT = SCRATCH / "vue54p2"
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
ACCT, PW = "123", "8888"
log: list[str] = []
console_errs: list[str] = []


def pick() -> None:
    global ACCT, PW
    try:
        data = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
        for a in data.get("accounts") or []:
            if a.get("账号") in ("123", "overall", "lushasha") and str(a.get("密码") or "").strip():
                ACCT, PW = a["账号"], str(a["密码"])
                return
    except Exception as e:
        log.append(f"acct {e}")


def login(page) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
    page.locator("input[type=text], #account, input").first.fill(ACCT)
    page.locator("input[type=password]").first.fill(PW)
    page.locator("button:has-text('登录'), button[type=submit]").first.click()
    page.wait_for_timeout(2500)
    page.goto(f"{BASE}/", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(1500)


def theme(page, light: bool) -> None:
    page.evaluate(
        """(light) => {
      const r = document.documentElement;
      if (light) r.classList.add('theme-light'); else r.classList.remove('theme-light');
      try { localStorage.setItem('cockpit-theme', light ? 'light' : 'dark'); } catch(e) {}
      window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light } }));
    }""",
        light,
    )
    page.wait_for_timeout(700)


def shot_card(page, name: str, sel: str) -> None:
    try:
        loc = page.locator(sel).first
        if loc.count() == 0:
            log.append(f"skip {name}")
            return
        loc.scroll_into_view_if_needed()
        page.wait_for_timeout(1100)
        p = OUT / f"{name}.png"
        loc.screenshot(path=str(p))
        log.append(f"ok {name} {p.stat().st_size}b")
    except Exception as e:
        log.append(f"fail {name}: {e}")


def main() -> int:
    pick()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        (SCRATCH / "playwright_env_fail.txt").write_text(str(e), encoding="utf-8")
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for w, h, tag in ((1440, 900, "1440"), (375, 812, "375")):
            page = browser.new_page(viewport={"width": w, "height": h})
            page.on("console", lambda m: console_errs.append(m.text) if m.type == "error" else None)
            try:
                login(page)
                for light, mode in ((False, "dark"), (True, "light")):
                    theme(page, light)
                    page.wait_for_timeout(900)
                    page.screenshot(path=str(OUT / f"overall_{mode}_{tag}.png"), full_page=True)
                    log.append(f"overall_{mode}_{tag}")
                    if tag == "1440" and mode == "dark":
                        for n, s in (
                            ("kpi", ".kpi-host, .kpi-grid"),
                            ("sec", "section.sec"),
                            ("trend", "#trendChartCard"),
                            ("pl", ".pl-card"),
                            ("donut", ".exp-donut-card"),
                            ("expense_trend", "#expTrendCard"),
                            ("receipts", "#receiptsCard"),
                            ("rank", "#rankViews"),
                        ):
                            shot_card(page, f"{n}_dark_iter1", s)
            except Exception as e:
                log.append(f"fail {tag}: {e}")
            page.close()

        # BU
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            login(page)
            theme(page, False)
            href = page.evaluate(
                """() => {
              const a = document.querySelector('.bu-nav-a, a[href^="/bu/"]');
              return a ? a.getAttribute('href') : null;
            }"""
            )
            if href:
                page.goto(f"{BASE}{href}", wait_until="networkidle", timeout=90000)
                page.wait_for_timeout(2500)
                page.screenshot(path=str(OUT / "bu_dark_1440.png"), full_page=True)
                log.append("bu ok")
            else:
                log.append("no bu")
        except Exception as e:
            log.append(f"bu fail {e}")
        page.close()
        browser.close()

    real = [e for e in console_errs if e and "favicon" not in e.lower()]
    (OUT / "console.txt").write_text("\n".join(real) + "\n", encoding="utf-8")
    # 不写硬编码 PASS 假笔记。仅落拍摄日志；目检结论由实现者手写 compare_notes.txt。
    (OUT / "shot_manifest.txt").write_text(
        "\n".join(
            [
                f"shots={len(list(OUT.glob('*.png')))}",
                f"console_errs={len(real)}",
                "NOTE: open each PNG and write compare_notes.txt by hand (no auto PASS).",
            ]
            + log
        )
        + "\n",
        encoding="utf-8",
    )
    (SCRATCH / "playwright_54p2.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log[-25:]))
    print("console", len(real), "png", len(list(OUT.glob("*.png"))))
    return 0 if not real else 0


if __name__ == "__main__":
    raise SystemExit(main())
