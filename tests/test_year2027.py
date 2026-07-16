#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书36·D/E：非法日历日 + 2027 跨年稳定性小基线（不动 2026 golden）。

- 非法日 parse → None（与 test_hygiene_b 互补，覆盖到体检黄文案路径）
- 台账缺「2027」sheet → KeyError 清晰指路（不静默 0、不崩成其它异常）
- today≈2027-01-15 合成数据：能 build_summary，周期键属 2027 系；2026 历史键不强制出现在当年矩阵
- zhiyun_since auto 见 test_fetch_zhiyun
"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import periods  # noqa: E402
import profit  # noqa: E402
from profit import build_summary  # noqa: E402


class TestIllegalDateHealthPath(unittest.TestCase):
    def test_illegal_date_counted_in_source_scan(self):
        loaders._DATE_PARTS_CACHE.clear()
        rows = [
            {"下单日期": "2024-02-30", "下单预估额/本币": "100"},
            {"下单日期": "2027-01-01", "下单预估额/本币": "200"},
        ]
        bad, amt = profit._scan_dict_source_issues(rows, "下单日期", "下单预估额/本币")
        self.assertEqual(bad, 1)
        self.assertEqual(amt, 0)


class TestLedgerSheet2027Missing(unittest.TestCase):
    def test_missing_year_sheet_raises_clear_keyerror(self):
        tmp = Path(tempfile.mkdtemp())
        data = tmp / "数据"
        data.mkdir()
        # 仅有 2026 sheet，无 2027
        wb = Workbook()
        ws = wb.active
        ws.title = "2026"
        ws.append(["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"])
        ws.append(["2026年1月", "2026-01-05", 10, "语言", "管理费用", "办公", "运保"])
        path = data / "收单台账.xlsx"
        wb.save(path)
        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "数据"
        cfg["files"] = dict(cfg["files"])
        cfg["files"]["ledger"] = "收单台账.xlsx"
        with self.assertRaises(KeyError) as cm:
            loaders.load_ledger(cfg, "2027", root=tmp)
        msg = str(cm.exception)
        self.assertIn("2027", msg)
        self.assertTrue("sheet" in msg.lower() or "找不到" in msg)
        # 建了 2027 后可读
        wb2 = Workbook()
        ws2 = wb2.active
        ws2.title = "2027"
        ws2.append(["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"])
        ws2.append(["2027年1月", "2027-01-10", 20, "语言", "管理费用", "办公", "运保"])
        wb2.save(path)
        hdr, rows = loaders.load_ledger(cfg, "2027", root=tmp)
        self.assertEqual(hdr[0], "收单月份")
        self.assertEqual(len(rows), 1)


class TestYear2027SyntheticBaseline(unittest.TestCase):
    """合成小基线：today=2027-01-15，空/微数据出页结构；周期属 2027。"""

    def test_periods_and_summary_for_2027_jan(self):
        today = datetime.date(2027, 1, 15)
        ranges = periods.all_period_ranges(today)
        self.assertIn("2027年", ranges)
        self.assertIn("2027年1月", ranges)
        # 1 月不应生成 2 月键
        self.assertNotIn("2027年2月", ranges)

        cfg = loaders.load_config(ROOT)
        # 一行 2027-01-01 下单 + 一行 2026 历史（确认解析不炸；当年汇总不依赖 2026 行）
        orders = [
            {"下单日期": "2027-01-01", "下单预估额/本币": "1060", "部门": "A", "销售": "甲"},
            {"下单日期": "2026-06-01", "下单预估额/本币": "500", "部门": "A", "销售": "甲"},
        ]
        project = [
            {
                "整单交付日期": "2027-01-05",
                "交付额/本币": "1060",
                "项目成本/本币": "100",
                "业务线": "语言",
                "销售": "甲",
                "客户": "客户甲",
            }
        ]
        receipts = [{"到账日期": "2027-01-08", "到账金额/本币": "500", "客户": "客户甲", "销售": "甲"}]
        inhouse = []
        lhdr = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]
        lrows = [
            ("2027年1月", "2027-01-03", 100.0, "语言", "管理费用", "办公用品", "运保"),
        ]
        s = build_summary(
            cfg,
            project,
            orders,
            receipts,
            inhouse,
            lhdr,
            lrows,
            2027,
            today,
            manual_raw={},
        )
        self.assertIn("periods", s)
        yk = (s.get("meta") or {}).get("year_key") or ""
        self.assertIn("2027", yk)
        self.assertIn("2027年", s["periods"])
        self.assertIn("2027年1月", s["periods"])
        # 2027-01-01 边界日必须进周期（非法日严校后仍有效）
        y = s["periods"]["2027年"]
        self.assertIn("orders", y)
        # 下单额应 >0（合成 1060）
        self.assertGreater(float(y.get("orders") or 0), 0)
        # 健康警告存在结构
        h = (s.get("meta") or {}).get("health") or {}
        self.assertIn("warnings", h)


if __name__ == "__main__":
    unittest.main(verbosity=2)
