#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书33·B：配置健壮性 + 时间边界（跨年/1月看去年）抽查。"""
from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import periods  # noqa: E402
import profit  # noqa: E402


class TestConfigValidate(unittest.TestCase):
    def test_missing_key_clear_error(self):
        with self.assertRaises(ValueError) as cm:
            loaders.validate_config({"data_dir": "数据"})
        self.assertIn("files", str(cm.exception))

    def test_real_config_ok(self):
        cfg = loaders.load_config(ROOT)
        loaders.validate_config(cfg)  # 不抛


class TestTimeBoundaries(unittest.TestCase):
    """跨年 / 1 月看去年 / 闰年路径：归属月与周期键。"""

    def test_leap_and_year_boundary_dates(self):
        self.assertEqual(loaders.parse_date_parts("2024-02-29"), (2024, 2, 29))
        self.assertEqual(loaders.parse_date_parts("2026-12-31"), (2026, 12, 31))
        self.assertEqual(loaders.parse_date_parts("2027-01-01"), (2027, 1, 1))
        self.assertIsNone(loaders.parse_date_parts(""))
        self.assertIsNone(loaders.parse_date_parts(None))

    def test_illegal_calendar_day_is_none(self):
        """任务书36·D：非法日历日返回 None（datetime.date 校验），不造 (2024,2,30)。"""
        # 清缓存，避免旧结果残留
        loaders._DATE_PARTS_CACHE.clear()
        self.assertIsNone(loaders.parse_date_parts("2024-02-30"))
        self.assertIsNone(loaders.parse_date_parts("2024-02-31"))
        self.assertIsNone(loaders.parse_date_parts("2023-02-29"))  # 非闰年
        self.assertIsNone(loaders.parse_date_parts("2024-04-31"))
        self.assertIsNone(loaders.parse_date_parts("20240230"))
        # 闰年合法
        self.assertEqual(loaders.parse_date_parts("2024-02-29"), (2024, 2, 29))
        self.assertEqual(loaders.parse_date_parts("2020-02-29"), (2020, 2, 29))

    def test_period_label_year_boundary(self):
        """build_summary 在 1 月 today 时不炸，且有 periods 结构。"""
        cfg = loaders.load_config(ROOT)
        s = profit.build_summary(
            cfg,
            [],
            [],
            [],
            [],
            ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"],
            [],
            2027,
            datetime.date(2027, 1, 8),
            manual_raw={},
        )
        self.assertIn("periods", s)
        self.assertGreaterEqual(len(s["periods"]), 1)
        self.assertIn("meta", s)
        # 周期键属 2027 系
        self.assertTrue(any("2027" in k for k in s["periods"]), list(s["periods"].keys())[:5])


if __name__ == "__main__":
    unittest.main()
