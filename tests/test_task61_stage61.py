#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书61 stage61：排名按下单降序 / 月裁 / 分摊 API 字段 / 三类人工分摊 / 源码守卫。"""
from __future__ import annotations

import datetime
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestRankOrderByOrders(unittest.TestCase):
    def test_merge_dual_rank_sorts_by_order_amount(self):
        from render_receipts_rank import _merge_dual_rank

        o = {
            "full_items": [
                {"name": "甲", "amount": 100},
                {"name": "乙", "amount": 300},
                {"name": "丙", "amount": 50},
            ]
        }
        r = {
            "full_items": [
                {"name": "甲", "amount": 9999},
                {"name": "乙", "amount": 1},
                {"name": "丙", "amount": 8000},
            ]
        }
        dual = _merge_dual_rank(o, r, top=2)
        names = [x["name"] for x in dual["items"]]
        self.assertEqual(names, ["乙", "甲"])  # 按下单 300>100
        self.assertEqual(dual["others"]["names"], 1)
        self.assertEqual(dual["full_items"][0]["name"], "乙")


class TestMonthCap(unittest.TestCase):
    def test_chart_month_max_and_daily_defaults(self):
        from viewmodels.packers import _chart_month_max_from_meta, pack_daily_defaults

        self.assertEqual(_chart_month_max_from_meta({"current_month_key": "2026年7月"}), 7)
        self.assertEqual(_chart_month_max_from_meta({"current_month_label": "2026年3月"}), 3)
        d = pack_daily_defaults(
            {"meta": {"year": 2026, "year_key": "2026年", "current_month_key": "2026年3月"}}
        )
        self.assertEqual(d["chart_month_max"], 3)
        self.assertTrue(d["default_end"].startswith("2026-03"))


class TestManualAllocJ(unittest.TestCase):
    def _cfg(self):
        return {
            "tax": {"vat_rate": 0.06, "surtax_rate": 0.12},
            "columns": {
                "project_delivery_date": "交付日期",
                "project_revenue": "交付额",
                "project_cost": "项目成本",
                "order_amount": "下单预估额",
                "order_date": "下单日期",
                "receipt_amount": "到账金额",
                "receipt_date": "到账日期",
            },
            "expense_categories_included": [
                "市场费用",
                "管理费用",
                "固定运营费用",
                "技术服务费",
                "财务费用",
            ],
            "manual_alloc_fine_types": ["房租", "物业费", "装修费"],
            "manual_alloc_category_map": {
                "房租": "固定运营费用",
                "物业费": "固定运营费用",
                "装修费": "管理费用",
            },
            "manual_items": [
                {"name": "营销人力成本", "role": "营销费用", "default": "zero"},
                {"name": "管理人力成本", "role": "管理费用", "default": "zero"},
                {"name": "研发人力成本", "role": "研发费用", "default": "zero"},
                {"name": "财务费用补充", "role": "财务费用", "default": "zero"},
                {"name": "PM人力成本", "role": "生产成本", "default": "zero"},
                {"name": "VM人力成本", "role": "生产成本", "default": "zero"},
                {"name": "实际内部译员成本", "role": "生产成本", "default": "zero"},
                {"name": "税费损失", "role": "生产成本", "default": "zero"},
                {"name": "技术流量成本", "role": "生产成本", "default": "zero"},
                {"name": "其他（生产成本）", "role": "生产成本", "default": "zero"},
                {"name": "直接成本增值税", "role": "生产成本抵减", "default": "zero"},
                {"name": "其他损益", "role": "利润表", "default": "zero"},
                {"name": "房租", "role": "固定运营费用", "default": "zero", "manual_alloc": True},
                {"name": "物业费", "role": "固定运营费用", "default": "zero", "manual_alloc": True},
                {"name": "装修费", "role": "管理费用", "default": "zero", "manual_alloc": True},
            ],
            "unclassified_label_expense": "未分类",
            "unclassified_label_fine_type": "未标注",
        }

    def test_excludes_ledger_and_adds_manual_to_expense(self):
        from profit.expense_period import (
            compute_ledger_expenses,
            is_manual_alloc_ledger_row,
            manual_alloc_amounts_by_cat,
        )

        cfg = self._cfg()
        lcols = {"含税金额": 0, "预算明细费用类型": 1, "对应报表大类": 2, "收单日期": 3}
        rows = [
            (50000_00, "房租", "固定运营费用", "2026-03-01"),
            (1000_00, "差旅", "管理费用", "2026-03-05"),
        ]
        self.assertTrue(is_manual_alloc_ledger_row(rows[0], cfg, lcols))
        self.assertFalse(is_manual_alloc_ledger_row(rows[1], cfg, lcols))
        led, cnt = compute_ledger_expenses(
            rows, 2026, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31), cfg, lcols
        )
        self.assertEqual(led["固定运营费用"], 0)
        self.assertEqual(led["管理费用"], 1000_00)
        self.assertEqual(cnt, 1)

        man = {
            "营销人力成本": 0,
            "管理人力成本": 0,
            "研发人力成本": 0,
            "财务费用补充": 0,
            "PM人力成本": 0,
            "VM人力成本": 0,
            "实际内部译员成本": 0,
            "税费损失": 0,
            "技术流量成本": 0,
            "其他（生产成本）": 0,
            "直接成本增值税": 0,
            "其他损益": 0,
            "房租": 12000_00,
            "物业费": 0,
            "装修费": 0,
        }
        self.assertEqual(manual_alloc_amounts_by_cat(man, cfg).get("固定运营费用"), 12000_00)
        # 与 build_period 同口径：台账 led + 人工 mac
        fixed = int(led["固定运营费用"] + manual_alloc_amounts_by_cat(man, cfg).get("固定运营费用", 0))
        admin = int(led["管理费用"] + man["管理人力成本"] + manual_alloc_amounts_by_cat(man, cfg).get("管理费用", 0))
        self.assertEqual(fixed, 12000_00)
        self.assertEqual(admin, 1000_00)
        # 源码守卫：budget_manual 已接 mac
        bm = (ROOT / "src" / "profit" / "budget_manual.py").read_text(encoding="utf-8")
        self.assertIn("manual_alloc_amounts_by_cat", bm)

    def test_merge_ledger_caliber_excludes_types(self):
        from domain.expense.chart_whitelist import merge_ledger_caliber_filters

        cfg = {
            "expense_categories_included": ["管理费用", "固定运营费用"],
            "manual_alloc_fine_types": ["房租", "物业费", "装修费"],
        }
        f = merge_ledger_caliber_filters(None, cfg, show_all=False)
        d = json.loads(f) if isinstance(f, str) else f
        self.assertIn("房租", d["预算明细费用类型"]["not_in"])
        f2 = merge_ledger_caliber_filters(None, cfg, show_all=True)
        self.assertTrue(f2 is None or f2 == {} or f2 is None)


class TestStage61SourceGuards(unittest.TestCase):
    def test_frontend_marks(self):
        root = ROOT / "frontend" / "src"
        rc = (root / "components" / "ReceiptsCard.vue").read_text(encoding="utf-8")
        self.assertIn("本年下单", rc)
        # UI 模板不得再渲染尚待回款（注释里可提及）
        tmpl = rc.split("<template>")[-1] if "<template>" in rc else rc
        self.assertNotIn("尚待回款", tmpl)
        self.assertNotIn("gap_disp", tmpl)
        self.assertNotIn("回款占下单", tmpl)
        self.assertIn("clipToCurrentMonth", rc)
        self.assertFalse((root / "components" / "ExpenseTrend.vue").exists())
        app = (root / "App.vue").read_text(encoding="utf-8")
        self.assertNotIn("ExpenseTrend", app)
        man = (root / "admin" / "views" / "ManualView.vue").read_text(encoding="utf-8")
        self.assertIn("/api/alloc_ratios", man)
        self.assertNotIn("/api/alloc_rates", man)
        rk = (root / "components" / "RankingsDual.vue").read_text(encoding="utf-8")
        self.assertIn("rk-others-btn", rk)
        exp = (root / "components" / "ExpenseSection.vue").read_text(encoding="utf-8")
        self.assertIn("exp-dept-md", exp)
        lt = (root / "components" / "LedgerTable.vue").read_text(encoding="utf-8")
        self.assertIn("ld-col-filter", lt)
        cfg = (ROOT / "config.json").read_text(encoding="utf-8")
        self.assertIn("manual_alloc_fine_types", cfg)
        self.assertIn("房租", cfg)


if __name__ == "__main__":
    unittest.main()
