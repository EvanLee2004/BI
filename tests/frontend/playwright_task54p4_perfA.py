#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54.4 批次A：性能证据（Playwright）。

用法（Vue 服务已起 :8018）:
  .venv/bin/python tests/frontend/playwright_task54p4_perfA.py [SCRATCH]

产出：docs/pixel/vue54p4/perfA/（合成/结构证据，不含业务断言数字）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54p4" / "perfA"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-7034d6e0fee6/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
ACCT = os.environ.get("KANBAN_ACCT_OVERALL", "123")
PW = os.environ.get("KANBAN_PW_OVERALL", "8888")
log: list[str] = []


def pick_account() -> None:
    global ACCT, PW
    for path in (ROOT / "数据" / "看板账号.json", ROOT / "_golden_data" / "看板账号.json"):
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data.get("accounts") or []
            for want in (ACCT, "123", "overall"):
                for a in rows:
                    if a.get("账号") == want and str(a.get("密码") or "").strip():
                        ACCT = want
                        PW = str(a["密码"])
                        log.append(f"account={want} from {path.name}")
                        return
        except Exception as e:
            log.append(f"account pick fail {path}: {e}")


def login(page) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
    for sel in ("input[type=password]", "#password"):
        try:
            if page.locator("input[type=text], #account, input").count():
                page.locator("input[type=text], #account, input").first.fill(ACCT)
            if page.locator(sel).count():
                page.locator(sel).first.fill(PW)
                break
        except Exception:
            pass
    for sel in ("button:has-text('登录')", "button[type=submit]", "button"):
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click()
                break
        except Exception:
            pass
    page.wait_for_load_state("networkidle", timeout=60000)
    page.wait_for_timeout(800)


def main() -> int:
    pick_account()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        (SCRATCH / "browser_env_fail.log").write_text(f"import fail: {e}\n", encoding="utf-8")
        log.append(f"FAIL import: {e}")
        (SCRATCH / "playwright_54p4_perfA.log").write_text("\n".join(log) + "\n", encoding="utf-8")
        return 2

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            (SCRATCH / "browser_env_fail.log").write_text(f"launch fail: {e}\n", encoding="utf-8")
            log.append(f"FAIL launch: {e}")
            (SCRATCH / "playwright_54p4_perfA.log").write_text("\n".join(log) + "\n", encoding="utf-8")
            return 2

        page = browser.new_page(viewport={"width": 1440, "height": 900})
        cons: list[str] = []
        page.on("console", lambda m: cons.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)

        try:
            login(page)
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / "overall_dark_1440.png"), full_page=True)
            log.append(f"shot overall_dark_1440.png size={ (OUT/'overall_dark_1440.png').stat().st_size}")

            # count live echarts instances + renderer
            metrics = page.evaluate(
                """() => {
                  const hosts = document.querySelectorAll('[data-chart], .rc-body > div, .trend-fill > div');
                  // echarts stores instance on DOM via getAttribute _echarts_instance_
                  const els = Array.from(document.querySelectorAll('[_echarts_instance_], canvas, svg'));
                  const echartsIds = Array.from(document.querySelectorAll('div[_echarts_instance_]')).length;
                  const canvases = document.querySelectorAll('canvas').length;
                  const svgs = document.querySelectorAll('div[_echarts_instance_] svg, .rc-body svg').length;
                  // star animation check
                  const before = getComputedStyle(document.body, '::before');
                  let starAnim = '';
                  try { starAnim = before.animationName || before.getPropertyValue('animation-name') || ''; } catch(e) {}
                  return {
                    echartsIds,
                    canvases,
                    svgs,
                    starAnim,
                    bodyClass: document.documentElement.className,
                    hasScifiPanel: !!document.querySelector('.scifi-panel'),
                  };
                }"""
            )
            log.append(f"metrics={json.dumps(metrics, ensure_ascii=False)}")
            (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

            # scroll performance rough timing
            t0 = page.evaluate("() => performance.now()")
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
            t1 = page.evaluate("() => performance.now()")
            log.append(f"scroll_roundtrip_ms={t1 - t0:.1f}")

            page.screenshot(path=str(OUT / "after_scroll.png"), full_page=False)
            log.append("shot after_scroll.png")

            # viewport count after scroll to bottom (lazy dispose)
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(400)
            bottom = page.evaluate(
                """() => ({
                  echartsIds: document.querySelectorAll('div[_echarts_instance_]').length,
                  y: window.scrollY
                })"""
            )
            log.append(f"bottom_metrics={json.dumps(bottom)}")
            (OUT / "bottom_metrics.json").write_text(
                json.dumps(bottom, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            errs = [c for c in cons if c.startswith("error")]
            log.append(f"console_errors={len(errs)}")
            if errs:
                log.append("ERR samples: " + " | ".join(errs[:5]))
                (OUT / "console_errors.txt").write_text("\n".join(errs), encoding="utf-8")
            else:
                (OUT / "console_errors.txt").write_text("none\n", encoding="utf-8")

        except Exception as e:
            log.append(f"FAIL run: {e}")
            try:
                page.screenshot(path=str(OUT / "fail.png"), full_page=True)
            except Exception:
                pass
            browser.close()
            (SCRATCH / "playwright_54p4_perfA.log").write_text("\n".join(log) + "\n", encoding="utf-8")
            return 1

        browser.close()

    (SCRATCH / "playwright_54p4_perfA.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    (OUT / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0 if not any(x.startswith("FAIL") for x in log) else 1


if __name__ == "__main__":
    raise SystemExit(main())
