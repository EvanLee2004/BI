#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P2~P4 shipped：client 路径 fragments 卡字段为空 + views 显示串；
page.js 组装后与 Python render_dashboard 规范化全等。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RUNNER = ROOT / "static" / "js" / "assemble" / "page_node_runner.js"

_CLIENT_FIELDS = (
    "kpi_views",
    "pl_views",
    "donut_views",
    "profit_rank_views",
    "rank_views",
    "trend_html",
    "receipts_budget",
    "period_bar",
    "daily_html",
)


def _norm(s: str) -> str:
    return re.sub(r">\s+<", "><", s.replace("\n", ""))


class TestShippedCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        import loaders, core, api_v1, assets

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cls.cfg = cfg
        cls.summary, cls.py_html, _, _ = core.generate(cfg, date(2026, 6, 30), trigger="b-shipped")
        logo = assets.load_logo_base64(cfg) or ""
        cls.pack = api_v1.cockpit_fragments(cls.summary, cfg, logo, client=True)

    def test_client_fragments_card_fields_empty(self):
        fr = self.pack["fragments"]
        for f in _CLIENT_FIELDS:
            self.assertEqual(fr.get(f), "", f"client 路径 {f} 应为空，逼 JS 组装")
        v = self.pack["views"]
        self.assertTrue(v.get("kpi_body"))
        self.assertTrue(v.get("pl_body"))
        self.assertTrue(v.get("donut_body"))
        self.assertTrue(v.get("profit_rank_body"))
        self.assertTrue(v.get("rankings_view"))
        self.assertTrue(v.get("trend_html"))
        self.assertTrue(v.get("period_bar"))

    def test_node_client_assemble_equals_python_dashboard(self):
        pack = {
            "fragments": self.pack["fragments"],
            "views": self.pack["views"],
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
        self.assertEqual(
            _norm(self.py_html),
            _norm(js_html),
            f"len py={len(self.py_html)} js={len(js_html)}",
        )

    def test_markers_present_after_js_assemble(self):
        """大卡锚点须出现在 JS 组装结果中。"""
        pack = {
            "fragments": self.pack["fragments"],
            "views": self.pack["views"],
            "templates": {
                "dashboard_body": (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8"),
                "page_shell": (ROOT / "static/templates/render/page_shell.html").read_text(encoding="utf-8"),
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
            path = f.name
        r = subprocess.run(["node", str(RUNNER), path], capture_output=True, text=True, check=True)
        html = r.stdout
        for m in ("管理利润表", "经营利润", "费用构成", "收入 · 按客户", "下单与回款", "dual-grid"):
            self.assertIn(m, html, m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
