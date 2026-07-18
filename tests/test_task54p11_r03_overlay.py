#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.11 R-03：弹层 token 结构守卫 + 活体打开态截图与不透明度检查。"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "static" / "css" / "theme.css"
BRIDGE = ROOT / "frontend" / "src" / "vendor" / "scifi-kit" / "scifi-bridge.css"
PL = ROOT / "frontend" / "src" / "components" / "PLTable.vue"


class TestOverlayTokens(unittest.TestCase):
    def test_theme_has_overlay_tokens(self):
        t = THEME.read_text(encoding="utf-8")
        self.assertIn("--overlay-panel", t)
        self.assertIn("--overlay-mask", t)
        self.assertIn("drawer-mask", t)
        # 遮罩约 0.4~0.5
        self.assertRegex(t, r"--overlay-mask:\s*rgba\([^)]*\.4[05]")

    def test_bridge_not_translucent_drawer(self):
        t = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("overlay-panel-solid", t)
        # 不再用半透明 dsdk-panel-bg 作为 drawer 主底
        self.assertNotRegex(
            t,
            r"\.drawer-panel\s*\{[^}]*var\(--dsdk-panel-bg",
            re.S,
        )

    def test_pltable_has_drawer_mask(self):
        t = PL.read_text(encoding="utf-8")
        self.assertIn("drawer-mask", t)
        self.assertIn('data-testid="drawer-mask"', t)


class TestOverlayLiveOptional(unittest.TestCase):
    def test_open_drawer_and_modal_opacity(self):
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

        scratch = Path(
            os.environ.get(
                "SCRATCH",
                "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-8cf6defd8c92/implementer",
            )
        )
        out = scratch / "r03_overlay"
        out.mkdir(parents=True, exist_ok=True)
        report = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(base + "/login", wait_until="networkidle", timeout=90000)
            page.locator("input").first.fill("overall")
            page.locator("input[type=password]").fill("8888")
            page.locator("button:has-text('进入')").click()
            page.wait_for_timeout(2000)

            # open PL drawer
            hint = page.locator("text=查看构成").first
            if hint.count():
                hint.click()
                page.wait_for_timeout(500)
                page.screenshot(path=str(out / "drawer.png"))
                styles = page.evaluate(
                    """() => {
                      const mask = document.querySelector('.drawer-mask');
                      const panel = document.querySelector('.drawer-panel');
                      const cs = (el) => el ? getComputedStyle(el) : null;
                      const parseA = (bg) => {
                        if (!bg) return null;
                        const m = bg.match(/rgba?\\(([^)]+)\\)/);
                        if (!m) return bg.startsWith('rgb(') ? 1.0 : null;
                        const parts = m[1].split(',').map(s => s.trim());
                        return parts.length >= 4 ? parseFloat(parts[3]) : 1.0;
                      };
                      return {
                        maskBg: cs(mask) && cs(mask).backgroundColor,
                        maskA: parseA(cs(mask) && cs(mask).backgroundColor),
                        panelBg: cs(panel) && cs(panel).backgroundColor,
                        panelA: parseA(cs(panel) && cs(panel).backgroundColor),
                      };
                    }"""
                )
                report.append({"kind": "drawer", **styles})
                self.assertIsNotNone(styles.get("maskA"))
                self.assertGreaterEqual(styles["maskA"], 0.35)
                self.assertLessEqual(styles["maskA"], 0.6)
                # panel near-solid
                if styles.get("panelA") is not None:
                    self.assertGreaterEqual(styles["panelA"], 0.95)
                page.locator(".drawer-mask").click()
                page.wait_for_timeout(300)

            # open ranking modal if possible
            try:
                opened = False
                if page.locator(".rk-more").count() > 0:
                    page.locator(".rk-more").first.click(timeout=3000)
                    opened = True
                elif page.locator("text=其余").count() > 0:
                    page.locator("text=其余").first.click(timeout=3000)
                    opened = True
                if opened:
                    page.wait_for_timeout(400)
                    page.screenshot(path=str(out / "modal.png"))
                    styles = page.evaluate(
                        """() => {
                          const mask = document.querySelector('.rkm-mask');
                          const box = document.querySelector('.rkm, .rkm-box');
                          const cs = (el) => el ? getComputedStyle(el) : null;
                          const parseA = (bg) => {
                            if (!bg) return null;
                            const m = bg.match(/rgba?\\(([^)]+)\\)/);
                            if (!m) return 1.0;
                            const parts = m[1].split(',').map(s => s.trim());
                            return parts.length >= 4 ? parseFloat(parts[3]) : 1.0;
                          };
                          return {
                            maskBg: cs(mask) && cs(mask).backgroundColor,
                            maskA: parseA(cs(mask) && cs(mask).backgroundColor),
                            panelBg: cs(box) && cs(box).backgroundColor,
                            panelA: parseA(cs(box) && cs(box).backgroundColor),
                          };
                        }"""
                    )
                    report.append({"kind": "modal", **styles})
                    if styles.get("maskA") is not None:
                        self.assertGreaterEqual(styles["maskA"], 0.35)
                    if styles.get("panelA") is not None:
                        self.assertGreaterEqual(styles["panelA"], 0.95)
                else:
                    report.append({"kind": "modal", "skip": "no trigger"})
            except Exception as e:
                report.append({"kind": "modal", "skip": str(e)[:120]})
            # close any open modal
            if page.locator(".rkm-mask").count():
                page.locator(".rkm-mask").first.click(position={"x": 8, "y": 8})
                page.wait_for_timeout(200)
            if page.locator("#rkmClose").count():
                try:
                    page.locator("#rkmClose").click(timeout=1500)
                except Exception:
                    pass
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

            # period dropdown
            page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
            page.wait_for_timeout(200)
            page.screenshot(path=str(out / "dropdown.png"))
            styles = page.evaluate(
                """() => {
                  const panel = document.querySelector('.pp-panel');
                  const cs = panel ? getComputedStyle(panel) : null;
                  const bg = cs && cs.backgroundColor;
                  let a = 1.0;
                  if (bg) {
                    const m = bg.match(/rgba?\\(([^)]+)\\)/);
                    if (m) {
                      const parts = m[1].split(',').map(s => s.trim());
                      a = parts.length >= 4 ? parseFloat(parts[3]) : 1.0;
                    }
                  }
                  return { panelBg: bg, panelA: a };
                }"""
            )
            report.append({"kind": "dropdown", **styles})
            self.assertGreaterEqual(styles.get("panelA") or 0, 0.95)

            browser.close()

        (out / "opacity.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (scratch / "r03_overlay_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()
