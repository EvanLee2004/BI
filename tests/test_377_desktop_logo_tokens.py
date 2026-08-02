#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.7：桌面 logo 放大 + theme.css cache-bust + 桌面优先 KPI 守卫（静态；不启浏览器）。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "static/css/theme.css"
BRIDGE = ROOT / "frontend/src/vendor/scifi-kit/scifi-bridge.css"
TOKENS = ROOT / "frontend/src/styles/tokens.css"
LEDGER = ROOT / "frontend/src/styles/components/LedgerTable.css"
INDEX = ROOT / "frontend/index.html"
APP_FACTORY = ROOT / "src/app_factory.py"
VERSION = ROOT / "VERSION"


def _desktop_tb_logo_block(css: str) -> str:
    """Default (non-media) .tb-logo rules only — strip @media blocks first."""
    stripped = re.sub(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "", css, flags=re.S)
    blocks = re.findall(r"\.tb-logo\s*\{([^}]+)\}", stripped)
    return "\n".join(blocks)


def _height_px(block: str) -> float | None:
    m = re.search(r"height\s*:\s*([\d.]+)px", block)
    return float(m.group(1)) if m else None


def _max_width_px(block: str) -> float | None:
    m = re.search(r"max-width\s*:\s*([\d.]+)px", block)
    return float(m.group(1)) if m else None


class Test377DesktopLogoTokens(unittest.TestCase):
    def test_version_is_377(self):
        self.assertEqual(VERSION.read_text(encoding="utf-8").strip(), "3.7.7")

    def test_theme_tb_logo_desktop_ge40_max_not_40(self):
        css = THEME.read_text(encoding="utf-8")
        desk = _desktop_tb_logo_block(css)
        self.assertTrue(desk, "theme.css must define .tb-logo outside media")
        h = _height_px(desk)
        self.assertIsNotNone(h, f"desktop .tb-logo height missing in: {desk!r}")
        self.assertGreaterEqual(h, 40.0, f"desktop logo height {h} < 40")
        self.assertLessEqual(h, 48.0, f"desktop logo height {h} too large")
        mw = _max_width_px(desk)
        self.assertIsNotNone(mw, "desktop .tb-logo must set max-width")
        self.assertGreaterEqual(mw, 56.0, f"max-width {mw} still capped <56 (was 40 bottleneck)")
        # no second historical 28px default that would win by cascade
        self.assertNotRegex(
            desk,
            r"height\s*:\s*28px",
            "duplicate 28px .tb-logo must be merged away",
        )

    def test_bridge_tb_logo_aligned(self):
        css = BRIDGE.read_text(encoding="utf-8")
        desk = _desktop_tb_logo_block(css)
        h = _height_px(desk)
        self.assertIsNotNone(h)
        self.assertGreaterEqual(h, 40.0)
        mw = _max_width_px(desk)
        self.assertIsNotNone(mw)
        self.assertGreaterEqual(mw, 56.0)

    def test_narrow_logo_32_to_36(self):
        def media_520_bodies(css: str) -> list[str]:
            out: list[str] = []
            for m in re.finditer(r"@media\s*\(\s*max-width\s*:\s*520px\s*\)\s*\{", css):
                start = m.end()
                depth = 1
                i = start
                while i < len(css) and depth:
                    if css[i] == "{":
                        depth += 1
                    elif css[i] == "}":
                        depth -= 1
                    i += 1
                out.append(css[start : i - 1])
            return out

        for path in (THEME, BRIDGE):
            css = path.read_text(encoding="utf-8")
            heights: list[float] = []
            for block in media_520_bodies(css):
                for body in re.findall(r"\.tb-logo\s*\{([^}]+)\}", block):
                    h = _height_px(body)
                    if h is not None:
                        heights.append(h)
            self.assertTrue(heights, f"{path.name}: no .tb-logo under max-width:520")
            for h in heights:
                self.assertGreaterEqual(h, 32.0, f"{path.name}: narrow logo {h} < 32")
                self.assertLessEqual(h, 36.0, f"{path.name}: narrow logo {h} > 36")

    def test_vue_img_attrs_match_desktop(self):
        for rel in ("frontend/src/App.vue", "frontend/src/components/BUPage.vue"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn('class="tb-logo"', src)
            self.assertRegex(src, r'width="4[02]"')
            self.assertRegex(src, r'height="4[02]"')
            self.assertNotIn('width="28"', src)

    def test_theme_css_cache_bust_in_index_and_serve(self):
        idx = INDEX.read_text(encoding="utf-8")
        self.assertRegex(
            idx,
            r'href="/static/css/theme\.css\?v=',
            "frontend/index.html must cache-bust theme.css with ?v=",
        )
        factory = APP_FACTORY.read_text(encoding="utf-8")
        self.assertIn("theme.css", factory)
        self.assertIn("PRODUCT_VERSION", factory)
        self.assertIn("?v=", factory)
        # inject path uses VERSION so hard-load cannot stick on pre-3.7.6 12px
        self.assertIn("theme.css?v=", factory.replace(" ", "").replace("\n", "") or factory)

    def test_desktop_kpi_stays_fs_kpi_not_22(self):
        t = TOKENS.read_text(encoding="utf-8")
        self.assertRegex(t, r"--fs-kpi:\s*38px")
        theme = THEME.read_text(encoding="utf-8")
        # desktop path uses var(--fs-kpi); 22/26 only allowed inside max-width:520
        stripped = re.sub(
            r"@media\s*\(\s*max-width\s*:\s*520px\s*\)\s*\{(?:[^{}]|\{[^{}]*\})*\}",
            "",
            theme,
            flags=re.S,
        )
        self.assertNotRegex(
            stripped,
            r"\.kpi-v\s+b[^}]*font-size:\s*22px",
            "desktop must not force KPI 22px",
        )
        self.assertNotRegex(
            stripped,
            r"\.kpi-v\s+b[^}]*font-size:\s*26px",
            "desktop must not force narrow KPI size",
        )
        # media may have 26–28 (P2)
        self.assertRegex(
            theme,
            r"@media\s*\(\s*max-width\s*:\s*520px\s*\)[\s\S]*?font-size:\s*26px",
        )

    def test_p1_meta_funnel_kpi_sub(self):
        t = TOKENS.read_text(encoding="utf-8")
        head = re.search(r"\.rank-bar__meta-head\s*\{([^}]+)\}", t)
        self.assertIsNotNone(head)
        self.assertNotIn("10px", head.group(1))
        self.assertTrue(
            "12px" in head.group(1) or "--fs-meta" in head.group(1),
            "meta-head must be ≥12",
        )
        ld = LEDGER.read_text(encoding="utf-8")
        self.assertRegex(ld, r"\.ld-funnel\{[^}]*font-size:\s*12px")
        theme = THEME.read_text(encoding="utf-8")
        self.assertRegex(theme, r"\.kpi-sub\{[^}]*font-size:\s*13px")
        bridge = BRIDGE.read_text(encoding="utf-8")
        self.assertRegex(bridge, r"\.kpi-sub\s*\{[^}]*font-size:\s*13px", re.S)


if __name__ == "__main__":
    unittest.main()
