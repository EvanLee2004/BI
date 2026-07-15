#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P1：模板清单 vs contract 节点表 diff 为空；rankings_view 挂载。"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CONTRACT = ROOT / "docs" / "cockpit_render_contract_v1.md"
TPL = ROOT / "static" / "templates"


class TestTemplateContract(unittest.TestCase):
    def test_contract_lists_all_template_dirs(self):
        text = CONTRACT.read_text(encoding="utf-8")
        # 顶层目录均应出现在合同
        for d in ("render", "partials", "charts"):
            self.assertTrue((TPL / d).is_dir(), d)
            self.assertIn(d, text, f"contract 未覆盖 templates/{d}")
        # login
        self.assertTrue((TPL / "login.html").is_file())
        self.assertIn("login.html", text)

    def test_every_render_template_mentioned_or_family(self):
        """每个 templates 下 html 文件名（或族前缀）应在合同表出现。"""
        text = CONTRACT.read_text(encoding="utf-8")
        missing = []
        for p in sorted(TPL.rglob("*.html")):
            rel = p.relative_to(TPL).as_posix()
            stem = p.stem
            # 族：kpi_*, dual_*, rc_*, render/ 等
            fam = stem.split("_")[0]
            if rel in text or stem in text or fam in text or p.parent.name in text:
                continue
            missing.append(rel)
        self.assertEqual(missing, [], "合同未覆盖模板: " + ", ".join(missing))

    def test_payload_has_rankings_view(self):
        import api_v1

        summary = {
            "meta": {"year": 2026, "year_key": "2026年"},
            "periods": {
                "2026年": {
                    "range": ("2026-01-01", "2026-12-31"),
                    "rankings": {
                        "orders_by_sales": {"items": [], "total": 0},
                        "receipts_by_sales": {"items": [], "total": 0},
                        "orders_by_customer": {"items": [], "total": 0},
                        "receipts_by_customer": {"items": [], "total": 0},
                    },
                }
            },
        }
        payload = api_v1.cockpit_payload(summary)
        self.assertIn("rankings_view", payload)
        self.assertIn("2026年", payload["rankings_view"])
        self.assertTrue(payload["rankings_view"]["2026年"]["visible"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
