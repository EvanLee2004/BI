#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B：整页碎片 + page.js（node）组装 == render_dashboard 逐字节。"""
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
        import loaders, core, render, assets
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cls.cfg = cfg
        cls.summary, cls.html, _, _ = core.generate(cfg, date(2026, 6, 30), trigger="b-page")
        cls.logo = assets.load_logo_base64(cfg) or ""
        cls.frags = render.build_dashboard_fragments(cls.summary, cfg, cls.logo)

    def test_python_assemble_equals_dashboard(self):
        import render
        a = render.assemble_dashboard_html(self.frags)
        self.assertEqual(a, self.html)

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
        # 铁律2：组装 JS 禁止金额运算（勿用过宽正则误伤字符类里的 0-9）
        self.assertNotRegex(js, r"\bparseFloat\b|\bNumber\s*\(")
        self.assertNotRegex(js, r"\b(amount|order|receipt|money|revenue|profit|cost)\w*\s*[\+\-\*/]")
        self.assertNotRegex(js, r"[\+\-\*/]\s*(amount|order|receipt|money|revenue|profit|cost)\w*\b")
        self.assertIsNone(re.search(r"(?<![=!<>])\s[\+\*\/]\s*\d", js))


if __name__ == "__main__":
    unittest.main(verbosity=2)
