# -*- coding: utf-8 -*-
"""P2-03 · 390 看数相关 CSS 契约（影响可读/横溢）。"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KC_CSS = ROOT / "frontend" / "src" / "styles" / "components" / "KeyCustomersPanel.css"
THEME = ROOT / "static" / "css" / "theme.css"


class TestMobile390LookAffectingCss(unittest.TestCase):
    def test_kc_420_help_popover_viewport_bound(self):
        css = KC_CSS.read_text(encoding="utf-8")
        self.assertIn("max-width: 420px", css)
        self.assertIn("calc(100vw - 1.5rem)", css)
        self.assertIn("overflow-x: hidden", css)
        self.assertIn(".kc-structure-pies", css)

    def test_theme_html_body_overflow_x_and_title_cap(self):
        css = THEME.read_text(encoding="utf-8")
        compact = css.replace(" ", "")
        self.assertIn("overflow-x:hidden", compact)
        self.assertIn("max-width:520px", compact)
        # 390 标题宽度上限
        self.assertIn("max-width:min(42vw,11rem)", compact.replace("\n", ""))


if __name__ == "__main__":
    unittest.main()
