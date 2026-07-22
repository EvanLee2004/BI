#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.1 霓虹主题性能实测 → SCRATCH/perf.json

用法：
  KANBAN_BASE=http://127.0.0.1:8028 .venv/bin/python scripts/measure_perf_2_3_1.py

指标：
  - idle_fps：静止 rAF 均帧（≥50 硬门槛主判）
  - scroll_fps：滚动期 rAF 均帧（记录；headless 常偏低）
  - tti_login_to_cockpit_ms：登录→驾驶舱可交互
  - 同机 dark idle 对照，霓虹 TTI 相对劣化记录
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8028")
SCRATCH = Path(
    os.environ.get(
        "SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-86121cf38401/implementer",
    )
)


def load_accounts():
    for path in (ROOT / "_golden_data" / "看板账号.json", ROOT / "数据" / "看板账号.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")).get("accounts") or []
    return []


def pick_viewer():
    for a in load_accounts():
        if a.get("账号") in ("overall", "123") and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
        if a.get("权限") == "整体" and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "overall", "8888"


RAF_SNIPPET = """
async ({mode, ms}) => {
  const dts = [];
  let last = performance.now();
  let stopAt = last + ms;
  let scrolling = mode === 'scroll';
  const step = (t) => {
    dts.push(t - last);
    last = t;
    if (scrolling) {
      const p = 1 - (stopAt - t) / ms;
      window.scrollTo(0, Math.max(0, (document.body.scrollHeight - innerHeight) * Math.min(1, Math.max(0, p))));
    }
    if (t < stopAt) requestAnimationFrame(step);
  };
  await new Promise((resolve) => {
    requestAnimationFrame((t0) => {
      last = t0;
      stopAt = t0 + ms;
      const done = (t) => {
        step(t);
        if (t >= stopAt) {
          window.scrollTo(0, 0);
          resolve(null);
        } else requestAnimationFrame(done);
      };
      requestAnimationFrame(done);
    });
  });
  const good = dts.filter(d => d > 0 && d < 80);
  if (!good.length) return {avg_fps: 0, samples: 0};
  const avg = good.reduce((a,b)=>a+b,0) / good.length;
  return {avg_fps: Math.round(1000/avg), samples: good.length, avg_frame_ms: +avg.toFixed(2)};
}
"""


def set_theme(page, theme: str) -> None:
    page.evaluate(
        f"""() => {{
      document.documentElement.dataset.theme = '{theme}';
      document.documentElement.classList.toggle('theme-light', '{theme}' === 'light');
      try {{
        localStorage.setItem('cockpit-theme', '{theme}');
        localStorage.setItem('cockpit-theme-v2', '1');
      }} catch (e) {{}}
      window.dispatchEvent(new CustomEvent('kanban-theme-change',
        {{detail: {{theme: '{theme}', light: '{theme}' === 'light'}}}}));
    }}"""
    )
    page.wait_for_timeout(400)


def main() -> int:
    from playwright.sync_api import sync_playwright

    SCRATCH.mkdir(parents=True, exist_ok=True)
    acc, pw = pick_viewer()
    out: dict = {"base": BASE, "method": "playwright-chromium-headless-rAF"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        t0 = time.perf_counter()
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
        if page.locator("input[type=password]").count():
            page.locator("input").first.fill(acc)
            page.locator("input[type=password]").first.fill(pw)
        page.locator(
            "button:has-text('进入'), button:has-text('登录'), button[type=submit]"
        ).first.click()
        page.wait_for_selector(
            "[data-testid=period-picker], .kpi-grid, .scifi-panel", timeout=60000
        )
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(400)
        tti_neon = (time.perf_counter() - t0) * 1000

        set_theme(page, "neon")
        page.wait_for_timeout(600)
        idle_neon = page.evaluate(RAF_SNIPPET, {"mode": "idle", "ms": 1000})
        scroll_neon = page.evaluate(RAF_SNIPPET, {"mode": "scroll", "ms": 1200})

        set_theme(page, "dark")
        page.wait_for_timeout(500)
        t1 = time.perf_counter()
        page.reload(wait_until="networkidle", timeout=90000)
        page.wait_for_selector(
            "[data-testid=period-picker], .kpi-grid, .scifi-panel", timeout=60000
        )
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        set_theme(page, "dark")
        tti_dark = (time.perf_counter() - t1) * 1000
        idle_dark = page.evaluate(RAF_SNIPPET, {"mode": "idle", "ms": 1000})

        # 375
        set_theme(page, "neon")
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(400)
        jank375 = page.evaluate(RAF_SNIPPET, {"mode": "scroll", "ms": 800})

        out.update(
            {
                "tti_login_to_cockpit_ms_neon": round(tti_neon, 1),
                "tti_reload_to_cockpit_ms_dark": round(tti_dark, 1),
                "idle_fps_neon_1920": idle_neon,
                "scroll_fps_neon_1920": scroll_neon,
                "idle_fps_dark_1920": idle_dark,
                "scroll_fps_neon_375": jank375,
                "thresholds": {
                    "idle_or_scroll_fps_min": 50,
                    "tti_soft_ms": 8000,
                    "note": "硬门槛：idle_fps 或 scroll_fps ≥50；headless 常低于 headed Chrome",
                },
            }
        )
        idle_f = float(idle_neon.get("avg_fps") or 0)
        scroll_f = float(scroll_neon.get("avg_fps") or 0)
        out["pass_fps_1920"] = max(idle_f, scroll_f) >= 50
        out["pass_tti_soft"] = tti_neon < 8000
        out["pass"] = bool(out["pass_fps_1920"] and out["pass_tti_soft"])
        # relative TTI note (dark reload vs neon first login not apples-to-apples; record both)
        if tti_dark > 0:
            out["tti_neon_vs_dark_reload_pct"] = round(
                (tti_neon - tti_dark) / tti_dark * 100, 1
            )

        browser.close()

    path = SCRATCH / "perf.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("WROTE", path)
    return 0 if out.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
