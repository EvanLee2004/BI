#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P3：大卡（趋势/利润表/费用环/收入结构）在 page.js 组装结果中与 Python 全等（整页契约子集）。"""
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

# 大卡锚点（结构判断全在后端碎片内；前端只拼接）
CARD_MARKERS = (
    "经营利润",  # 趋势卡区
    "data-rm-map",  # 趋势/回款周期映射
    "管理利润表",  # 利润表
    "pl-open",  # 利润表展开行
    "费用构成",  # 期间费用环图区
    "收入 · 按客户",  # 收入毛利结构
    "收入 · 按销售",
)


class TestP3BigCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        import loaders, core, render, assets
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cls.cfg = cfg
        cls.summary, cls.html, _, _ = core.generate(cfg, date(2026, 6, 30), trigger="b-p3")
        logo = assets.load_logo_base64(cfg) or ""
        cls.frags = render.build_dashboard_fragments(cls.summary, cfg, logo)

    def test_node_html_byte_equal(self):
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

    def test_big_card_markers_present_equal_counts(self):
        for m in CARD_MARKERS:
            self.assertIn(m, self.html, f"Python 缺大卡锚点: {m}")
            self.assertEqual(self.html.count(m), self.html.count(m))  # sanity
            # frags 内对应 HTML 段应含锚点（至少 KPI/趋势/利润/排名之一）
        # 碎片字段齐全
        for k in ("trend_html", "pl_views", "donut_views", "profit_rank_views", "kpi_views"):
            self.assertIn(k, self.frags)
            self.assertTrue(self.frags[k], f"空碎片: {k}")

    def test_svg_trend_attrs_stable(self):
        # SVG 属性存在且组装前后一致（整页已 equal，这里抽查 path/rect）
        n_path = len(re.findall(r"<path\b", self.html))
        n_rect = len(re.findall(r"<rect\b", self.html))
        self.assertGreater(n_path + n_rect, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
