#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S1：主题机制升枚举（neon | dark | light）结构守卫。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
STATIC = ROOT / "static"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class TestThemeEnum230(unittest.TestCase):
    def test_theme_ts_has_three_modes_and_normalize(self):
        src = _read(FE / "src" / "utils" / "theme.ts")
        self.assertIn("ThemeMode", src)
        self.assertTrue("'neon'" in src or '"neon"' in src)
        self.assertTrue("'dark'" in src or '"dark"' in src)
        self.assertTrue("'light'" in src or '"light"' in src)
        self.assertIn("normalizeTheme", src)
        self.assertIn("cockpit-theme-v2", src)
        self.assertIn("theme-light", src)
        self.assertIn("深色", src)
        self.assertIn("浅色", src)

    def test_theme_css_keeps_theme_light_compat_class(self):
        css = _read(STATIC / "css" / "theme.css")
        self.assertTrue(".theme-light{" in css or ".theme-light {" in css)

    def test_antiflicker_scripts_have_data_theme_and_v2(self):
        """S1.4 五处内联防闪脚本统一。"""
        paths = [
            FE / "index.html",
            FE / "snapshot.html",
            STATIC / "view_login.html",
            STATIC / "admin_login.html",
            STATIC / "templates" / "view_login.html",
            STATIC / "templates" / "login.html",
        ]
        for p in paths:
            text = _read(p)
            self.assertTrue(
                "data-theme" in text
                or 'setAttribute("data-theme"' in text
                or "setAttribute('data-theme'" in text,
                msg=str(p),
            )
            self.assertIn("cockpit-theme-v2", text, msg=str(p))
            self.assertIn("neon", text, msg=str(p))

    def test_admin_bootstrap_forces_dark_no_localstorage_read(self):
        src = _read(FE / "src" / "admin" / "bootstrap.ts")
        self.assertTrue(
            "dataset.theme" in src or "data-theme" in src or "theme = 'dark'" in src or 'theme = "dark"' in src
        )
        self.assertNotIn("localStorage.getItem('cockpit-theme')", src)
        self.assertNotIn('localStorage.getItem("cockpit-theme")', src)

    def test_boot_cockpit_migrates_theme(self):
        src = _read(FE / "src" / "boot-cockpit.ts")
        self.assertIn("migrateThemeIfNeeded", src)

    def test_echarts_theme_three_modes(self):
        src = _read(FE / "src" / "echarts-theme.ts")
        self.assertIn("neon", src)
        self.assertIn("currentThemeMode", src)

    def test_theme_toggle_labels_keep_dark_light_words(self):
        src = _read(FE / "src" / "components" / "ThemeToggle.vue")
        util = _read(FE / "src" / "utils" / "theme.ts")
        self.assertIn("深色", util)
        self.assertIn("浅色", util)
        self.assertTrue("themeToggleLabel" in src or "深色" in src)


if __name__ == "__main__":
    unittest.main()
