#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书65：L1 单轨 / L2 按需导出 / 架构守卫。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402


class TestL1LegacyGone(unittest.TestCase):
    def test_no_admin_js_on_disk(self):
        adm = ROOT / "static" / "admin"
        self.assertFalse((adm / "admin.js").exists())
        self.assertFalse((adm / "admin.html.legacy").exists())
        self.assertTrue((adm / "bootstrap.html").exists())


class TestL2PublishNoFullHtml(unittest.TestCase):
    def test_publish_sets_has_data_clears_user_html(self):
        from app_state import _state
        from refresh_pipeline import publish

        _state["user_html"] = "OLD_FULL_PAGE"
        _state["has_data"] = False
        publish(None, {"meta": {"year_key": "2026年"}}, html="<html>big</html>", fragments={"a": 1}, views={"v": 1})
        self.assertTrue(_state.get("has_data"))
        self.assertEqual(_state.get("user_html"), "")
        self.assertEqual(_state.get("summary"), {"meta": {"year_key": "2026年"}})
        self.assertIsNone(_state.get("export_html_cache"))

    def test_assemble_export_uses_injected_html(self):
        """测试注入 user_html 时导出仍可用。"""
        from app_state import _state
        from refresh_pipeline import assemble_export_html

        _state["summary"] = {"meta": {"year_key": "2026年"}, "periods": {}}
        _state["built_at"] = "t1"
        _state["user_html"] = "<html><body>INJECT</body></html>"
        _state["export_html_cache"] = None
        h = assemble_export_html({}, bu_name=None)
        self.assertIn("INJECT", h)


class TestArchGuards(unittest.TestCase):
    def test_routes_no_direct_import_server(self):
        """routes/ 除 _srv.py 外不得 `import server`。"""
        routes = ROOT / "src" / "routes"
        bad = []
        for p in routes.glob("*.py"):
            if p.name.startswith("_"):
                continue
            t = p.read_text(encoding="utf-8")
            for i, line in enumerate(t.splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if "import server" in s or s.startswith("from server "):
                    bad.append(f"{p.name}:{i}:{s}")
        self.assertEqual(bad, [], "routes 直连 import server: " + "; ".join(bad))

    def test_static_admin_whitelist(self):
        """static/admin 仅允许 bootstrap + 可选重定向页。"""
        adm = ROOT / "static" / "admin"
        names = {p.name for p in adm.iterdir() if p.is_file()}
        allowed = {"bootstrap.html", "admin.html"}  # admin.html=重定向可选
        self.assertTrue(names <= allowed, f"多余文件: {names - allowed}")


if __name__ == "__main__":
    unittest.main()
