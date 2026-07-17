#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书51·B2：pl_structure 单一建造 —— HTML/VM 与重构前等价守卫。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import render  # noqa: E402
from domain.pl.structure import pl_structure, structure_for_vm  # noqa: E402
from viewmodels import packers  # noqa: E402

FAKE = ROOT / "_golden_data"


class TestPLStructureSingleChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            cls.summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        cls.cfg = cfg
        cls.yk = cls.summary["meta"]["year_key"]
        cls.P = cls.summary["periods"]
        cls.FT = cls.summary.get("expense_fine_type") or {}
        unc = (cls.summary.get("meta") or {}).get("unclassified") or {}
        cls.unc_amt = float((unc.get("expense") or {}).get("amount") or 0)

    def test_structure_for_vm_equals_pack_overall(self):
        packed = packers.pack_pl_by_period(self.summary, is_bu=False)[self.yk]
        unc = self.unc_amt if self.unc_amt > 0 else None
        struct = pl_structure(
            self.P[self.yk],
            self.FT.get(self.yk) or {},
            is_bu=False,
            unclassified_amt=unc,
        )
        self.assertEqual(structure_for_vm(struct), packed)

    def test_structure_for_vm_equals_pack_bu(self):
        packed = packers.pack_pl_by_period(self.summary, is_bu=True)[self.yk]
        alloc = self.summary["meta"].get("public_allocation") or {}
        struct = pl_structure(
            self.P[self.yk],
            self.FT.get(self.yk) or {},
            is_bu=True,
            alloc_meta=alloc,
        )
        self.assertEqual(structure_for_vm(struct), packed)

    def test_render_pl_table_consumes_structure(self):
        unc = self.unc_amt if self.unc_amt > 0 else None
        html = render.render_pl_table(self.P[self.yk], self.FT.get(self.yk) or {}, unclassified_amt=unc)
        self.assertIn("交付收入", html)
        self.assertIn("税前利润", html)
        self.assertIn("pl-row", html)

    def test_render_bu_pl_table_returns_tag(self):
        html, tag = render.render_bu_pl_table(
            self.P[self.yk],
            self.summary["meta"].get("public_allocation"),
            fine=self.FT.get(self.yk),
        )
        self.assertIn("交付收入", html)
        self.assertIsInstance(tag, str)

    def test_pack_pl_no_duplicate_business_rules_in_module(self):
        """packers 不再内嵌 PL 行构造（消费 domain.pl.structure）。"""
        src = (ROOT / "src" / "viewmodels" / "packers.py").read_text(encoding="utf-8")
        self.assertIn("pl_structure", src)
        self.assertIn("structure_for_vm", src)
        # 旧分叉关键字不应再作为 PL 主逻辑硬编码整段
        self.assertNotIn('details["sales"] = {', src)

    def test_kpi_uses_shared_peak_target(self):
        src = (ROOT / "src" / "viewmodels" / "packers.py").read_text(encoding="utf-8")
        self.assertIn("kpi_peak_for", src)
        self.assertIn("kpi_target_bar", src)
        cards = packers.pack_kpi_cards_by_period(self.summary, self.cfg).get(self.yk) or []
        self.assertGreaterEqual(len(cards), 5)
        self.assertIn("value_disp", cards[0])

    def test_legacy_html_kpi_consumes_shared_structure(self):
        """任务书51·B2：legacy HTML 路径 render_widgets 必须 import/调用共享 KPI 函数（非平行实现）。"""
        src = (ROOT / "src" / "render_widgets.py").read_text(encoding="utf-8")
        self.assertIn("from domain.pl.structure import kpi_target_bar", src)
        self.assertIn("from domain.pl.structure import kpi_peak_for", src)
        self.assertIn("kpi_target_bar(", src)
        self.assertIn("kpi_peak_for(", src)
        # 旧平行实现关键字不得再作为主逻辑（业务规则已迁到 structure）
        self.assertNotIn("best_v, best_mk = None, None", src)
        self.assertNotIn('label = "H1目标"', src)
        # 运行时：共享函数 + HTML 渲染都能产出
        from domain.pl.structure import kpi_peak_for, kpi_target_bar
        from render_widgets import _kpi_peak_row, _target_bar

        peak = kpi_peak_for(self.summary, "orders")
        month_keys = (self.summary.get("meta") or {}).get("tab_groups", {}).get("月") or []
        year = (self.summary.get("meta") or {}).get("year")
        html_peak = _kpi_peak_row(month_keys, self.P, "orders", year)
        if peak:
            self.assertIn(peak["label"], html_peak)
            self.assertIn(peak["value_wan"], html_peak)
        budget = (self.summary.get("meta") or {}).get("budget") or {}
        p = self.P[self.yk]
        bar = kpi_target_bar("order", self.yk, p, budget)
        html_bar = _target_bar(budget, "order", self.yk, year, p)
        if bar is None:
            self.assertEqual(html_bar, "")
        elif bar.get("empty"):
            self.assertIn("未设目标", html_bar)
        else:
            self.assertIn("kpi-tgt", html_bar)


if __name__ == "__main__":
    unittest.main()
