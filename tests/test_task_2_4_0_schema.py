#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.4.0 Stage B：公共明细金额覆盖 + 明细精配规则 建表/读写/校验/历史（不接线计算）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import loaders  # noqa: E402
import schema  # noqa: E402


class TestPublicDetailSchemaTables(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = loaders.load_config()
        self.conn = db.connect(self.cfg, Path(self.tmp))

    def tearDown(self):
        self.conn.close()

    def test_tables_created(self):
        names = {
            r[0]
            for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for t in (
            "manual_公共明细金额覆盖",
            "manual_公共明细金额覆盖历史",
            "manual_分摊_明细规则",
            "manual_分摊_明细规则历史",
            "manual_分摊比例",
        ):
            self.assertIn(t, names, f"missing table {t}")
        # HUMAN_TABLES 登记
        for t in (
            "manual_公共明细金额覆盖",
            "manual_公共明细金额覆盖历史",
            "manual_分摊_明细规则",
            "manual_分摊_明细规则历史",
        ):
            self.assertIn(t, schema.HUMAN_TABLES)


class TestPublicDetailAmountOverride(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = loaders.load_config()
        self.conn = db.connect(self.cfg, Path(self.tmp))

    def tearDown(self):
        self.conn.close()

    def test_set_get_load_delete_history(self):
        db.set_public_detail_amount_override(
            self.conn, "2026-07", "房租物业", 56.4, "tester"
        )
        got = db.get_public_detail_amount_overrides(self.conn, "2026-07")
        self.assertEqual(set(got), {"房租物业"})
        # 56.4 元 → 5640 分
        self.assertEqual(got["房租物业"], 5640)

        all_ov = db.load_public_detail_amount_overrides(self.conn)
        self.assertEqual(all_ov["2026-07"]["房租物业"], 5640)

        # 覆盖更新
        db.set_public_detail_amount_override(
            self.conn, "2026-07", "房租物业", 60.0, "tester"
        )
        self.assertEqual(
            db.get_public_detail_amount_overrides(self.conn, "2026-07")["房租物业"],
            6000,
        )

        # 删除
        db.set_public_detail_amount_override(
            self.conn, "2026-07", "房租物业", None, "tester"
        )
        self.assertEqual(db.get_public_detail_amount_overrides(self.conn, "2026-07"), {})

        hist = self.conn.execute(
            "SELECT 旧值,新值 FROM manual_公共明细金额覆盖历史 ORDER BY id"
        ).fetchall()
        self.assertGreaterEqual(len(hist), 3)
        # 首次：旧 None → 5640
        self.assertIsNone(hist[0][0])
        self.assertEqual(hist[0][1], 5640)
        # 更新：5640 → 6000
        self.assertEqual(hist[1][0], 5640)
        self.assertEqual(hist[1][1], 6000)
        # 删除：6000 → None
        self.assertEqual(hist[2][0], 6000)
        self.assertIsNone(hist[2][1])

    def test_amount_negative_rejected(self):
        with self.assertRaises(ValueError):
            db.set_public_detail_amount_override(
                self.conn, "2026-07", "房租", -1, "t"
            )
        with self.assertRaises(ValueError):
            db.set_public_detail_amount_override(self.conn, "", "房租", 1, "t")


class TestAllocDetailRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = loaders.load_config()
        self.conn = db.connect(self.cfg, Path(self.tmp))

    def tearDown(self):
        self.conn.close()

    def test_ratio_set_get_delete(self):
        db.set_alloc_detail_rule(
            self.conn, "2026-07", "打印费", "数据部", "比例", 80, "t"
        )
        db.set_alloc_detail_rule(
            self.conn, "2026-07", "打印费", "游戏部", "比例", 20, "t"
        )
        got = db.get_alloc_detail_rules(self.conn, "2026-07")
        self.assertEqual(got["打印费"]["数据部"]["mode"], "比例")
        self.assertEqual(got["打印费"]["数据部"]["value"], 80.0)
        self.assertEqual(got["打印费"]["游戏部"]["value"], 20.0)

        db.set_alloc_detail_rule(
            self.conn, "2026-07", "打印费", "游戏部", None, None, "t"
        )
        self.assertNotIn("游戏部", db.get_alloc_detail_rules(self.conn, "2026-07")["打印费"])

        hist_n = self.conn.execute(
            "SELECT COUNT(*) FROM manual_分摊_明细规则历史"
        ).fetchone()[0]
        self.assertGreaterEqual(hist_n, 3)

    def test_amount_mode_yuan_fen_roundtrip(self):
        db.set_alloc_detail_rule(
            self.conn, "2026-07", "装修费", "数据部", "金额", 5.0, "t"
        )
        got = db.get_alloc_detail_rules(self.conn, "2026-07")
        self.assertEqual(got["装修费"]["数据部"]["mode"], "金额")
        self.assertAlmostEqual(got["装修费"]["数据部"]["value"], 5.0, places=2)
        # 库内分
        raw = self.conn.execute(
            "SELECT 值 FROM manual_分摊_明细规则 WHERE 明细费用类型=? AND BU=?",
            ("装修费", "数据部"),
        ).fetchone()[0]
        self.assertEqual(int(raw), 500)

    def test_ratio_range_and_mode_guard(self):
        with self.assertRaises(ValueError):
            db.set_alloc_detail_rule(
                self.conn, "2026-07", "打印费", "数据部", "比例", 120, "t"
            )
        with self.assertRaises(ValueError):
            db.set_alloc_detail_rule(
                self.conn, "2026-07", "打印费", "数据部", "未知", 10, "t"
            )
        with self.assertRaises(ValueError):
            db.set_alloc_detail_rule(
                self.conn, "2026-07", "打印费", "数据部", "金额", -1, "t"
            )

    def test_validate_over_ratio_and_over_amount(self):
        rules_ok = {
            "数据部": {"mode": "比例", "value": 80},
            "游戏部": {"mode": "比例", "value": 20},
        }
        db.validate_alloc_detail_item_rules(rules_ok)  # no raise

        with self.assertRaises(ValueError) as cm:
            db.validate_alloc_detail_item_rules(
                {
                    "数据部": {"mode": "比例", "value": 80},
                    "游戏部": {"mode": "比例", "value": 30},
                }
            )
        self.assertIn("100", str(cm.exception))

        with self.assertRaises(ValueError) as cm2:
            db.validate_alloc_detail_item_rules(
                {
                    "数据部": {"mode": "金额", "value": 8},
                    "游戏部": {"mode": "金额", "value": 5},
                },
                item_amount_yuan=10.0,
            )
        self.assertIn("超过", str(cm2.exception))

        with self.assertRaises(ValueError):
            db.validate_alloc_detail_item_rules(
                {
                    "数据部": {"mode": "比例", "value": 50},
                    "游戏部": {"mode": "金额", "value": 1},
                }
            )

    def test_load_all_months(self):
        db.set_alloc_detail_rule(
            self.conn, "2026-06", "打印费", "数据部", "比例", 100, "t"
        )
        db.set_alloc_detail_rule(
            self.conn, "2026-07", "打印费", "游戏部", "比例", 50, "t"
        )
        allr = db.load_alloc_detail_rules(self.conn)
        self.assertEqual(set(allr), {"2026-06", "2026-07"})
        self.assertEqual(allr["2026-06"]["打印费"]["数据部"]["value"], 100.0)


if __name__ == "__main__":
    unittest.main()
