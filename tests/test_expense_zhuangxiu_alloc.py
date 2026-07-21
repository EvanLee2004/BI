#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.4·A/D2：装修费归固定运营费用；手填装修进 fixed + total + pretax；管理费用不含。

比较「填了装修」vs「未填装修」：delta 恰为装修额；重分类中性（同填金额下换 map 不改 total）。
"""
from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _base_cfg():
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
            "inhouse_amount": "本币结算",
            "inhouse_date": "完成日期",
            "inhouse_type": "任务类型",
        },
        "inhouse_keyword": "IN-HOUSE",
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
            "装修费": "固定运营费用",
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
            {"name": "装修费", "role": "固定运营费用", "default": "zero", "manual_alloc": True},
        ],
        "unclassified_label_expense": "未分类",
        "unclassified_label_fine_type": "未标注",
    }


def _zero_man(**overrides):
    names = [
        "营销人力成本",
        "管理人力成本",
        "研发人力成本",
        "财务费用补充",
        "PM人力成本",
        "VM人力成本",
        "实际内部译员成本",
        "税费损失",
        "技术流量成本",
        "其他（生产成本）",
        "直接成本增值税",
        "其他损益",
        "房租",
        "物业费",
        "装修费",
    ]
    m = {n: 0 for n in names}
    m.update(overrides)
    return m


class TestZhuangxiuFixedOps(unittest.TestCase):
    ZHUANGXIU_FEN = 20_000_00  # 2 万 元 = 2_000_000 分

    def test_mac_puts_zhuangxiu_in_fixed(self):
        from profit.expense_period import manual_alloc_amounts_by_cat

        cfg = _base_cfg()
        man = _zero_man(装修费=self.ZHUANGXIU_FEN)
        mac = manual_alloc_amounts_by_cat(man, cfg)
        self.assertEqual(mac.get("固定运营费用"), self.ZHUANGXIU_FEN)
        self.assertEqual(mac.get("管理费用", 0), 0)

    def test_build_period_fixed_contains_zhuangxiu(self):
        """fixture 手填装修 2万 → fixed 含之、admin 不含、total/pretax 与未填差恰好装修额。"""
        from profit.budget_manual import build_period

        cfg = _base_cfg()
        cols = cfg["columns"]
        lcols = {
            "含税金额": 0,
            "预算明细费用类型": 1,
            "对应报表大类": 2,
            "收单日期": 3,
        }
        # 台账仅一笔差旅（管理费用），无房租/装修台账行（被 manual_alloc 剔）
        ledger_rows = [(1000_00, "差旅", "管理费用", "2026-03-05")]
        start, end = datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)
        today = datetime.date(2026, 3, 15)

        filled_with = {(2026, 3): _zero_man(装修费=self.ZHUANGXIU_FEN)}
        filled_without = {(2026, 3): _zero_man()}

        common = dict(
            cfg=cfg,
            cols_cfg=cols,
            project_rows=[],
            order_rows=[],
            receipt_rows=[],
            inhouse_rows=[],
            ledger_rows=ledger_rows,
            ledger_year=2026,
            lcols=lcols,
            label="2026年3月",
            start=start,
            end=end,
            cur_date=today,
        )
        p_with = build_period(filled_manual=filled_with, **common)
        p_without = build_period(filled_manual=filled_without, **common)

        self.assertEqual(p_with["expense"]["固定运营费用"], self.ZHUANGXIU_FEN)
        self.assertEqual(p_with["expense"]["管理费用"], 1000_00)  # 仅台账差旅
        self.assertEqual(p_without["expense"]["固定运营费用"], 0)
        self.assertEqual(p_without["expense"]["管理费用"], 1000_00)

        # total / pretax 与未填相比恰好差装修额
        d_total = p_with["expense"]["total"] - p_without["expense"]["total"]
        d_pretax = p_without["pretax_profit"] - p_with["pretax_profit"]  # 费用↑ → pretax↓
        self.assertEqual(d_total, self.ZHUANGXIU_FEN)
        self.assertEqual(d_pretax, self.ZHUANGXIU_FEN)

    def test_reclass_neutral_total(self):
        """同一手填装修额：map 管理费用 vs 固定运营 → total/pretax 不变（重分类中性）。"""
        from profit.expense_period import expense_totals_from_man_led

        man = _zero_man(装修费=self.ZHUANGXIU_FEN)
        led = {"市场费用": 0, "管理费用": 500_00, "固定运营费用": 0, "技术服务费": 0, "财务费用": 0}
        cfg_fixed = _base_cfg()
        cfg_admin = _base_cfg()
        cfg_admin["manual_alloc_category_map"] = {
            "房租": "固定运营费用",
            "物业费": "固定运营费用",
            "装修费": "管理费用",
        }
        a = expense_totals_from_man_led(man, led, cfg_fixed)
        b = expense_totals_from_man_led(man, led, cfg_admin)
        self.assertEqual(a["total"], b["total"])
        self.assertEqual(a["固定运营费用"] - b["固定运营费用"], self.ZHUANGXIU_FEN)
        self.assertEqual(b["管理费用"] - a["管理费用"], self.ZHUANGXIU_FEN)

    def test_inject_fine_has_zhuangxiu_under_fixed(self):
        from profit.expense_period import inject_manual_alloc_into_breakdowns

        cfg = _base_cfg()
        pman = _zero_man(装修费=self.ZHUANGXIU_FEN)
        fine, _, _ = inject_manual_alloc_into_breakdowns(
            pman, cfg, {"管理费用": [("差旅", 1000_00)]}, [], []
        )
        fixed = dict(fine.get("固定运营费用") or [])
        self.assertEqual(fixed.get("装修费"), self.ZHUANGXIU_FEN)
        admin = dict(fine.get("管理费用") or [])
        self.assertNotIn("装修费", admin)


if __name__ == "__main__":
    unittest.main()
