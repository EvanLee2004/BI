#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P0：执行 static/js/assemble/rankings.js（node）vs render_rankings 逐字节相等。"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
JS = ROOT / "static" / "js" / "assemble" / "rankings.js"
RUNNER = ROOT / "static" / "js" / "assemble" / "rankings_node_runner.js"


class TestP0RankingsAssemble(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not JS.is_file():
            raise unittest.SkipTest("missing rankings.js")
        try:
            subprocess.run(["node", "--version"], check=True, capture_output=True)
        except Exception as e:
            raise unittest.SkipTest(f"node required: {e}")

    def test_node_js_equals_python_render(self):
        import render, api_v1
        p = {
            "range": ("2026-01-01", "2026-12-31"),
            "rankings": {
                "orders_by_sales": {
                    "items": [{"name": "甲", "amount": 1000000.0, "count": 1}],
                    "full_items": [{"name": "甲", "amount": 1000000.0, "count": 1}], "total": 1000000.0},
                "receipts_by_sales": {
                    "items": [{"name": "甲", "amount": 400000.0, "count": 1}],
                    "full_items": [{"name": "甲", "amount": 400000.0, "count": 1}], "total": 400000.0},
                "orders_by_customer": {
                    "items": [{"name": "客", "amount": 800000.0, "count": 1}],
                    "full_items": [{"name": "客", "amount": 800000.0, "count": 1}], "total": 800000.0},
                "receipts_by_customer": {
                    "items": [{"name": "客", "amount": 300000.0, "count": 1}],
                    "full_items": [{"name": "客", "amount": 300000.0, "count": 1}], "total": 300000.0},
            },
        }
        py_html = render.render_rankings(p)
        view = api_v1.rankings_view_for_period(p)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(view, f, ensure_ascii=False)
            vp = f.name
        r = subprocess.run(
            ["node", str(RUNNER), vp], capture_output=True, text=True, check=True)
        js_html = r.stdout
        # normalize: JS may omit some newlines present in tpl dual_row
        def norm(s):
            return re.sub(r">\s+<", "><", s.replace("\n", ""))
        self.assertEqual(norm(py_html), norm(js_html),
                         f"py/js mismatch\nPY:{py_html[:200]!r}\nJS:{js_html[:200]!r}")

    def test_assemble_js_no_money_math(self):
        js = JS.read_text(encoding="utf-8")
        bad = re.findall(r"\b(amount|order|receipt)\s*[\+\-\*/]", js)
        self.assertEqual(bad, [], f"组装 JS 疑似金额运算: {bad}")

    def test_js_loaded_by_shell_or_runner(self):
        self.assertTrue(JS.is_file())
        self.assertTrue(RUNNER.is_file())
        # B-P0 shipped：shell 必须加载 rankings.js + page.js
        shell = (ROOT / "static" / "shell.html").read_text(encoding="utf-8")
        self.assertIn("assemble/rankings.js", shell)
        self.assertIn("assemble/page.js", shell)


if __name__ == "__main__":
    unittest.main(verbosity=2)
