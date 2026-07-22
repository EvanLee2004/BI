#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S2：霓虹 token 块完整，token 名集合 ⊇ light。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "theme.css").read_text(encoding="utf-8")


def _block(css: str, start_pat: str) -> str:
    m = re.search(start_pat, css)
    if not m:
        return ""
    i = m.end() - 1  # at '{'
    depth = 0
    for j in range(i, len(css)):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                return css[i + 1 : j]
    return ""


def _token_names(block: str) -> set[str]:
    return set(re.findall(r"--([a-zA-Z0-9-]+)\s*:", block))


class TestNeonTokens230(unittest.TestCase):
    def test_neon_block_exists(self):
        self.assertIn('[data-theme="neon"]', CSS)

    def test_neon_tokens_superset_of_light(self):
        # light 业务 token 块（非空锚点 .theme-light{}）
        light = _block(CSS, r"\.theme-light\s*,\s*:root\[data-theme=\"light\"\]\s*\{")
        if not light.strip():
            light = _block(CSS, r"\.theme-light\s*\{")
        neon = _block(CSS, r':root\[data-theme="neon"\]\s*\{')
        self.assertTrue(light.strip(), "light token block empty")
        self.assertTrue(neon.strip(), "neon token block empty")
        lt = _token_names(light)
        nt = _token_names(neon)
        # light 里的业务色 token 霓虹必须都有（防漏定义掉回深空）
        missing = lt - nt
        self.assertFalse(missing, f"neon 缺少 light 已有 token: {sorted(missing)}")

    def test_neon_key_values_present(self):
        neon = _block(CSS, r':root\[data-theme="neon"\]\s*\{')
        self.assertIn("--bg:", neon)
        self.assertIn("--blue:", neon)
        self.assertIn("--glow:", neon)
        self.assertIn("--fs-kpi:", neon)
        self.assertIn("#01030a", neon)
        self.assertIn("#2ff3ff", neon)

    def test_scifi_bridge_neon(self):
        bridge = (ROOT / "frontend/src/vendor/scifi-kit/scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn('[data-theme="neon"]', bridge)
        self.assertIn("--dsdk-", bridge)

    def test_theme_light_compat_anchor(self):
        self.assertIn(".theme-light{", CSS)


if __name__ == "__main__":
    unittest.main()
