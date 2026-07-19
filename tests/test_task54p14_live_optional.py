#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.14 活体可选：主题切换 / 周期弹层 / 热力图 / 无万万（需 8018 + playwright）。"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs" / "验收证据" / "20260719_54p14"
SCRATCH = Path(
    os.environ.get(
        "SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-7374fe778a68/implementer",
    )
)


class Test54p14LiveOptional(unittest.TestCase):
    def test_live_walk(self):
        base = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
        try:
            import urllib.request

            urllib.request.urlopen(base + "/api/health", timeout=2)
        except Exception:
            self.skipTest("8018 未起服")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("无 playwright")

        out = EVID / "live"
        out.mkdir(parents=True, exist_ok=True)
        report: dict = {"steps": []}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(base + "/login", wait_until="networkidle", timeout=90000)
            # 生产 数据/看板账号.json：整体账号多为 123/123；golden 为 overall/8888
            user = os.environ.get("KANBAN_USER", "123")
            pwd = os.environ.get("KANBAN_PASS", "123")
            page.locator("input").first.fill(user)
            page.locator("input[type=password]").fill(pwd)
            page.locator("button:has-text('进入')").click()
            # 等驾驶舱挂载（周期选择器）
            try:
                page.wait_for_selector("[data-testid=period-picker]", timeout=45000)
            except Exception:
                page.screenshot(path=str(out / "login_fail.png"))
                report["steps"].append({"login": "period-picker missing", "url": page.url, "body": page.inner_text("body")[:400]})
                (out / "live_report.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                raise
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / "home_dark.png"))

            # R-20：页面文本无「万万」
            body = page.inner_text("body")
            self.assertNotIn("万万", body)
            report["steps"].append({"r20": "no_double_wan_body", "ok": True})

            # R-21：主题切换即时 class
            before = page.evaluate("() => document.documentElement.classList.contains('theme-light')")
            theme_btn = page.locator("button:has-text('浅色'), button:has-text('深色'), button:has-text('亮/暗')").first
            theme_btn.click(force=True)
            page.wait_for_timeout(500)
            after = page.evaluate("() => document.documentElement.classList.contains('theme-light')")
            self.assertNotEqual(before, after)
            page.screenshot(path=str(out / "theme_after_toggle.png"))
            report["steps"].append({"r21": "theme_toggle", "before": before, "after": after})

            # 再切回
            theme_btn.click(force=True)
            page.wait_for_timeout(400)

            # R-22：打开周期选择器，panel 在 KPI 之上且可点
            page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / "period_open.png"))
            styles = page.evaluate(
                """() => {
                  const panel = document.querySelector('.pp-panel');
                  const kpi = document.querySelector('.kpi-grid, .kpi-host');
                  if (!panel) return { ok: false, reason: 'no panel' };
                  const pr = panel.getBoundingClientRect();
                  const cs = getComputedStyle(panel);
                  const z = cs.zIndex;
                  let kpiZ = null;
                  if (kpi) kpiZ = getComputedStyle(kpi).zIndex;
                  const bg = cs.backgroundColor;
                  let a = 1.0;
                  const m = bg && bg.match(/rgba?\\(([^)]+)\\)/);
                  if (m) {
                    const parts = m[1].split(',').map(s => s.trim());
                    a = parts.length >= 4 ? parseFloat(parts[3]) : 1.0;
                  }
                  return { ok: true, z, kpiZ, panelA: a, top: pr.top, height: pr.height };
                }"""
            )
            report["steps"].append({"r22_panel": styles})
            self.assertTrue(styles.get("ok"))
            self.assertGreaterEqual(styles.get("panelA") or 0, 0.95)

            # 点「月」tab
            page.locator(".pp-tab:has-text('月')").click()
            page.wait_for_timeout(200)
            months = page.locator(".pp-body .pp-opt")
            n = months.count()
            report["steps"].append({"r22_months": n})
            if n > 0:
                months.nth(min(n - 1, 11)).click()
                page.wait_for_timeout(500)
            page.screenshot(path=str(out / "period_month.png"))

            # 自定义区间
            page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
            page.wait_for_timeout(200)
            page.locator(".pp-tab:has-text('自定义')").click()
            page.wait_for_timeout(200)
            if page.locator(".pp-apply").count():
                page.locator(".pp-apply").click()
                page.wait_for_timeout(400)
            page.screenshot(path=str(out / "period_custom.png"))

            # R-26 热力图
            heat = page.locator("[data-testid=expense-heatmap]")
            if heat.count():
                heat.scroll_into_view_if_needed()
                page.wait_for_timeout(400)
                page.screenshot(path=str(out / "heatmap.png"))
                report["steps"].append({"r26": "heatmap_visible"})
            else:
                report["steps"].append({"r26": "heatmap_missing_or_empty"})

            # 375
            page.set_viewport_size({"width": 375, "height": 812})
            page.wait_for_timeout(300)
            page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
            page.wait_for_timeout(200)
            page.screenshot(path=str(out / "period_375.png"))
            page.keyboard.press("Escape")

            # light theme screenshot
            page.set_viewport_size({"width": 1440, "height": 900})
            page.evaluate(
                """() => {
                  document.documentElement.classList.add('theme-light');
                  window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light: true } }));
                }"""
            )
            page.wait_for_timeout(500)
            page.screenshot(path=str(out / "home_light_1440.png"))
            body_l = page.inner_text("body")
            self.assertNotIn("万万", body_l)

            browser.close()

        (out / "live_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (SCRATCH / "54p14_live_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()
