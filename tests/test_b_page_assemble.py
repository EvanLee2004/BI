#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B：整页碎片 + page.js（node）组装 == Python assemble_dashboard_html 逐字节。

2.7.7 G2：core.generate 运行态不再预装 HTML（html=""）；本测仍锁导出/遗留 assemble 链
（build_dashboard_fragments → assemble_dashboard_html / page.js）Python 与 Node 同源。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RUNNER = ROOT / "static" / "js" / "assemble" / "page_node_runner.js"


class TestPageAssemble(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        import loaders
        import core
        import render
        import assets

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cls.cfg = cfg
        cls.summary, gen_html, _, _ = core.generate(cfg, date(2026, 6, 30), trigger="b-page")
        # G2：刷新/generate 不再返回预装整页 HTML
        cls.gen_html = gen_html
        cls.logo = assets.load_logo_base64(cfg) or ""
        cls.frags = render.build_dashboard_fragments(cls.summary, cfg, cls.logo)
        cls.html = render.assemble_dashboard_html(cls.frags)

    def test_generate_no_longer_ships_html(self):
        """2.7.7：generate 运行态 html 为空，看数走 VM。"""
        self.assertEqual(self.gen_html, "")
        self.assertGreater(len(self.html), 100_000, "assemble 导出链仍应产出完整 HTML")

    def test_python_assemble_equals_dashboard(self):
        import render

        a = render.assemble_dashboard_html(self.frags)
        # 与 render_dashboard 兼容入口同源
        b = render.render_dashboard(self.summary, self.cfg, self.logo)
        self.assertEqual(a, self.html)
        self.assertEqual(b, self.html)

    def test_node_page_js_equals_dashboard(self):
        pack = {
            "fragments": self.frags,
            "templates": {
                "dashboard_body": (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8"),
                "page_shell": (ROOT / "static/templates/render/page_shell.html").read_text(encoding="utf-8"),
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
            path = f.name
        r = subprocess.run(["node", str(RUNNER), path], capture_output=True, text=True, check=True)
        js_html = r.stdout
        self.assertEqual(js_html, self.html, f"len py={len(self.html)} js={len(js_html)}")

    def test_page_js_no_money_ops(self):
        import re

        js = (ROOT / "static/js/assemble/page.js").read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        code = re.sub(r"//.*?$", "", code, flags=re.M)
        self.assertNotRegex(code, r"\bparseFloat\b|\bNumber\s*\(")
        self.assertNotRegex(code, r"\b(amount|order|receipt|money|revenue|profit|cost)\w*\s*[\+\-\*/]")
        self.assertNotRegex(code, r"[\+\-\*/]\s*(amount|order|receipt|money|revenue|profit|cost)\w*\b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
