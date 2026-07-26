# -*- coding: utf-8 -*-
"""2.6.8 T2：费用定位键含「事项」；仍撞则稳定序号；重复组归零。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import columns  # noqa: E402
from ingest import normalize  # noqa: E402


# 最小台账表头（与 resolve_ledger_columns 兼容）
HDR = [
    "收单月份",
    "收单日期",
    "含税金额",
    "业务BU",
    "对应报表大类",
    "预算明细费用类型",
    "预算归属部门",
    "事项",
    "提单人",
    "提单人部门",
    "业务员",
    "配音费合同号",
]


def _row(month="07", day="21", amt=100, bu="语言", cat="管理费用", fine="办公费", item="A", **kw):
    base = {
        "收单月份": month,
        "收单日期": day,
        "含税金额": amt,
        "业务BU": bu,
        "对应报表大类": cat,
        "预算明细费用类型": fine,
        "预算归属部门": "行政",
        "事项": item,
        "提单人": "",
        "提单人部门": "",
        "业务员": "",
        "配音费合同号": "",
    }
    base.update(kw)
    return [base.get(h) for h in HDR]


class TestExpenseLocatorWithItem(unittest.TestCase):
    def setUp(self):
        self.lcols = columns.resolve_ledger_columns(HDR)

    def test_different_items_different_keys(self):
        rows = [_row(item="事项甲"), _row(item="事项乙")]
        out = normalize.norm_ledger(HDR, rows, 2026, self.lcols)
        self.assertEqual(len(out), 2)
        self.assertNotEqual(out[0]["定位键"], out[1]["定位键"])
        # 不含事项的旧键应相同，但新键不同
        self.assertEqual(out[0]["_legacy_定位键"], out[1]["_legacy_定位键"])

    def test_same_all_fields_get_seq_suffix(self):
        rows = [_row(item="同"), _row(item="同"), _row(item="同")]
        out = normalize.norm_ledger(HDR, rows, 2026, self.lcols)
        keys = [r["定位键"] for r in out]
        self.assertEqual(len(set(keys)), 3, keys)
        # 第一条无后缀，后两条 #1 #2
        base = keys[0]
        self.assertNotIn("#", base)
        self.assertEqual(keys[1], f"{base}#1")
        self.assertEqual(keys[2], f"{base}#2")

    def test_zero_duplicate_groups(self):
        # 模拟审查场景：同金额同日不同事项
        rows = [
            _row(item="差旅-北京"),
            _row(item="差旅-上海"),
            _row(item="差旅-北京"),  # 与第一条完全同 → 序号
            _row(item="招待", amt=200),
        ]
        out = normalize.norm_ledger(HDR, rows, 2026, self.lcols)
        keys = [r["定位键"] for r in out]
        self.assertEqual(len(keys), len(set(keys)), f"仍有重复: {keys}")

    def test_include_item_in_hash_not_legacy(self):
        from ingest.normalize import _hash

        a = _hash("07", "21", 100.0, "语言", "管理费用", "办公费")
        b = _hash("07", "21", 100.0, "语言", "管理费用", "办公费", "事项X")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
