#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S5：导出 pack 含 theme；非法回落 neon；密级页脚。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from export_html import assemble_export_pack, normalize_export_theme  # noqa: E402


class TestExportTheme230(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_export_theme("neon"), "neon")
        self.assertEqual(normalize_export_theme("dark"), "dark")
        self.assertEqual(normalize_export_theme("light"), "light")
        self.assertEqual(normalize_export_theme("weird"), "neon")
        self.assertEqual(normalize_export_theme(None), "neon")
        self.assertEqual(normalize_export_theme(""), "neon")

    def test_pack_has_theme(self):
        pack = assemble_export_pack(
            scope="整体",
            blk="2026",
            version="2.3.0",
            cockpit_vm={"period_keys": ["2026"], "year_key": "2026"},
            bu_vms={},
            theme="light",
        )
        self.assertEqual(pack.get("theme"), "light")
        pack2 = assemble_export_pack(
            scope="整体",
            cockpit_vm={},
            bu_vms={},
            theme="nope",
        )
        self.assertEqual(pack2.get("theme"), "neon")

    def test_export_html_has_theme_param(self):
        src = (ROOT / "src" / "routes" / "export.py").read_text(encoding="utf-8")
        self.assertIn("theme", src)
        top = (ROOT / "frontend" / "src" / "components" / "TopBarActions.vue").read_text(encoding="utf-8")
        self.assertIn("theme=", top)

    def test_footer_confidential_in_builder(self):
        # HTML 在模板（py 不拼标签）；token 替换在 export_html
        tpl = (ROOT / "static" / "templates" / "export" / "snapshot_shell.html").read_text(encoding="utf-8")
        self.assertIn("内部资料", tpl)
        self.assertIn("请勿外传", tpl)
        self.assertIn("__EXPORTED_AT__", tpl)
        src = (ROOT / "src" / "export_html.py").read_text(encoding="utf-8")
        self.assertIn("__EXPORTED_AT__", src)


if __name__ == "__main__":
    unittest.main()
