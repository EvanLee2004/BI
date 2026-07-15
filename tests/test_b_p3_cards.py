#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P3：大卡 shipped 路径（views + page.js），非 Python 预拼 fragments fill。"""

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

CARD_MARKERS = (
    "经营利润",
    "data-rm-map",
    "管理利润表",
    "pl-open",
    "费用构成",
    "收入 · 按客户",
    "收入 · 按销售",
)


def _norm(s: str) -> str:
    return re.sub(r">\s+<", "><", s.replace("\n", ""))


class TestP3BigCardsShipped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        import loaders, core, api_v1, assets

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cls.summary, cls.py_html, _, _ = core.generate(cfg, date(2026, 6, 30), trigger="b-p3")
        logo = assets.load_logo_base64(cfg) or ""
        cls.pack = api_v1.cockpit_fragments(cls.summary, cfg, logo, client=True)

    def test_client_does_not_ship_prejoined_card_html(self):
        fr = self.pack["fragments"]
        for f in ("kpi_views", "pl_views", "donut_views", "profit_rank_views", "trend_html"):
            self.assertEqual(fr.get(f), "")
        v = self.pack["views"]
        self.assertTrue(v.get("kpi_body") and v.get("pl_body") and v.get("trend_html"))

    def test_node_views_assemble_equals_python(self):
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
        self.assertEqual(_norm(r.stdout), _norm(self.py_html))

    def test_big_card_markers_in_js_html(self):
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
        for m in CARD_MARKERS:
            self.assertIn(m, r.stdout, m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
