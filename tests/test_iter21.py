#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代21 测试：
A 回款卡月份高亮结构（见 test_cockpit）
B 月周期待分类提示（见 test_cockpit）
C 台账「利润归属中心」未知名 → warnings / 无 BU 不报警 / 已知不误报 / XSS 文案含原文（渲染 esc）

跑：.venv/bin/python tests/test_iter21.py
"""

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import columns
import profit
import core
import bu
import loaders
import db  # noqa: E402

TODAY = datetime.date(2026, 7, 15)
HEADER = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型"]


def _cfg():
    return loaders.load_config()


def _lcols():
    return columns.resolve_ledger_columns(HEADER)


def _row(month, amt, pc, cat="管理费用"):
    """台账行：(收单月份, 收单日期, 含税金额, 业务BU, 对应报表大类, 预算明细费用类型)"""
    return (month, f"2026-{month:02d}-10", amt, pc, cat, "差旅费")


class TestUnknownProfitCenter(unittest.TestCase):
    """任务C：未知归属中心校验。"""

    def test_unknown_name_collected(self):
        cfg = _cfg()
        rows = [
            _row(3, 10000, "语言部"),  # 未知（「语言」可归营销，语言部不行）
            _row(4, 5000, "语言部"),
            _row(5, 20000, "数据"),  # 已知 BU
            _row(6, 8000, "公共"),  # 公共池
            _row(6, 3000, "财务部"),  # 归一→公共
            _row(7, 1000, ""),  # 空=不算未知
        ]
        items = profit.scan_unknown_profit_centers(rows, 2026, _lcols(), cfg, {"数据", "游戏", "营销"}, year=2026)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "语言部")
        self.assertEqual(items[0]["count"], 2)
        self.assertAlmostEqual(items[0]["amount"], 15000.0)

    def test_known_bu_and_public_not_flagged(self):
        cfg = _cfg()
        rows = [
            _row(3, 10000, "数据"),
            _row(3, 10000, "数据部门"),  # 归一→数据
            _row(3, 10000, "语言"),  # 归一→营销
            _row(3, 10000, "公共"),
            _row(3, 10000, "集团"),
            _row(3, 10000, "游戏部门"),
        ]
        items = profit.scan_unknown_profit_centers(rows, 2026, _lcols(), cfg, {"数据", "游戏", "营销"}, year=2026)
        self.assertEqual(items, [])

    def test_no_bu_config_skips_attach(self):
        """没配任何 BU → attach 不报警。"""
        cfg = _cfg()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 空 data_dir，无 BU配置.json
            cfg2 = dict(cfg)
            cfg2["data_dir"] = str(root / "数据")
            (root / "数据").mkdir()
            conn = db.connect(cfg2, root)
            # 最小 summary 壳
            summary = {"meta": {"health": {"warnings": [], "sources": [], "ok": True}}}
            # 写几行未知台账进库也无所谓——没 BU 就该跳过
            core.attach_unknown_pc_warnings(cfg2, conn, TODAY, summary, root=root)
            warns = summary["meta"]["health"]["warnings"]
            self.assertFalse(any("利润归属中心" in w for w in warns))
            conn.close()

    def test_warnings_format_and_attach(self):
        cfg = _cfg()
        items = [{"name": "语言部", "count": 2, "amount": 15000.0}]
        warns = profit.unknown_pc_warnings(items)
        self.assertEqual(len(warns), 1)
        self.assertIn("语言部", warns[0])
        self.assertIn("不在 BU 名单", warns[0])
        self.assertIn("2 笔", warns[0])
        self.assertIn("不进任何 BU 直记也不进公共池", warns[0])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "数据"
            data.mkdir()
            # 写 BU 配置
            import json

            (data / "BU配置.json").write_text(
                json.dumps(
                    {
                        "bus": [
                            {"name": "数据", "销售": ["甲"], "负责人": []},
                            {"name": "营销", "销售": ["乙"], "负责人": []},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            cfg2 = dict(cfg)
            cfg2["data_dir"] = str(data)
            conn = db.connect(cfg2, root)  # connect 建表
            conn.execute(
                "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
                "预算明细费用类型,预算归属部门,归属月,已删除) VALUES (?,?,?,?,?,?,?,?,?,0)",
                ("k1", 3, "2026-03-10", 1500000, "语言部", "管理费用", "差旅费", "", "2026-03"),  # 15000 元
            )
            conn.commit()
            summary = {"meta": {"health": {"warnings": [], "sources": [], "ok": True}}}
            core.attach_unknown_pc_warnings(cfg2, conn, TODAY, summary, root=root)
            w = summary["meta"]["health"]["warnings"]
            self.assertTrue(any("语言部" in x and "不在 BU 名单" in x for x in w), w)
            self.assertEqual(len(summary["meta"]["unknown_profit_centers"]), 1)
            conn.close()

    def test_xss_name_in_warning_is_raw_for_esc_later(self):
        """自由文本进 warning 串时保留原文；渲染层/管理端用 esc()（铁律10）。
        守卫：warning 含危险字符原文（供服务端算好），且 unknown_pc_warnings 不自行剥掉。"""
        evil = "<img src=x onerror=alert(1)>"
        items = [{"name": evil, "count": 1, "amount": 100.0}]
        warns = profit.unknown_pc_warnings(items)
        self.assertEqual(len(warns), 1)
        self.assertIn(evil, warns[0])
        # 管理端渲染路径：esc 后不得保留裸 <img
        from render import _esc

        escaped = _esc(warns[0])
        self.assertNotIn("<img", escaped)
        self.assertIn("&lt;img", escaped)

    def test_whitelist_only(self):
        """非白名单大类（未分类/口径外）不进未知归属扫描。"""
        cfg = _cfg()
        rows = [
            _row(3, 99999, "语言部", cat=""),  # 未填大类=未分类，不进白名单
        ]
        # 空 cat → classify 返回 unclassified_label，不在 included
        items = profit.scan_unknown_profit_centers(rows, 2026, _lcols(), cfg, {"数据"}, year=2026)
        self.assertEqual(items, [])


class TestPeriodMonthsMap(unittest.TestCase):
    """任务A：周期→月份映射（Python 侧）。"""

    def test_key_shapes(self):
        from render import _months_for_period_key

        yk = "2026年"
        self.assertEqual(_months_for_period_key("2026年", yk), list(range(1, 13)))
        self.assertEqual(_months_for_period_key("2026年3月", yk), [3])
        self.assertEqual(_months_for_period_key("2026年Q1", yk), [1, 2, 3])
        self.assertEqual(_months_for_period_key("2026年Q2", yk), [4, 5, 6])
        self.assertEqual(_months_for_period_key("2026年1-3月", yk), [1, 2, 3])
        self.assertEqual(_months_for_period_key("2026年5-7月", yk), [5, 6, 7])


if __name__ == "__main__":
    unittest.main(verbosity=2)
