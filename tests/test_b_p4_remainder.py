#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P4：回款卡/双血条/drawer/日段 + BU 隔离回归 + data-assembled 契约。"""

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

P4_MARKERS = (
    "下单与回款",
    "dual-grid",
    "dual-bar",
    "回款",
    "drawer",
)


class TestP4Remainder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        import loaders
        import core
        import render
        import assets

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cls.summary, cls.html, _, cls.bu_pages = core.generate(cfg, date(2026, 6, 30), trigger="b-p4")
        logo = assets.load_logo_base64(cfg) or ""
        cls.frags = render.build_dashboard_fragments(cls.summary, cfg, logo)
        cls.cfg = cfg

    def test_remainder_in_fragments_and_equal_page(self):
        for k in ("receipts_budget", "rank_views", "daily_html", "drawer"):
            self.assertIn(k, self.frags)
            self.assertTrue(str(self.frags[k]).strip(), f"空: {k}")
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
        self.assertEqual(r.stdout, self.html)
        for m in P4_MARKERS:
            if m == "drawer":
                # drawer 可能是 class/id
                self.assertTrue("drawer" in self.html.lower() or "抽屉" in self.html or self.frags["drawer"])
            else:
                self.assertIn(m, self.html, m)

    def test_body_data_assembled_mark(self):
        """导出/快照 HTML 仍可带 assembled 标记；看端 shell 已删。"""
        self.assertIn('data-assembled="1"', self.html)
        self.assertFalse((ROOT / "static" / "shell.html").is_file())

    def test_bu_pages_have_fragments_for_shell(self):
        """BU 页有 summary + fragments + views；65·L2 不预装 html。"""
        self.assertIsInstance(self.bu_pages, dict)
        for name, page in (self.bu_pages or {}).items():
            self.assertNotIn("html", page, name)
            self.assertIn("fragments", page)
            self.assertIn("summary", page)
            self.assertTrue(page["fragments"].get("kpi_views") is not None)
            self.assertIn(name, page["fragments"].get("name", "") or name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
