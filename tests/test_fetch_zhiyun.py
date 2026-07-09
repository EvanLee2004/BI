#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_zhiyun 离线单测：解析器/翻页/必需列护栏/三态返回/xlsx 产物可被 loaders 读回。
不碰网络——post 用测试桩注入。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ingest import fetch_zhiyun as fz  # noqa: E402


def ctrl(cid, name, options=None):
    return {"controlId": cid, "controlName": name, "options": options or []}


class TestParseCell(unittest.TestCase):
    def test_plain_and_empty(self):
        c = ctrl("c1", "文本")
        self.assertEqual(fz.parse_cell("abc", c), "abc")
        self.assertEqual(fz.parse_cell("7806.84", c), "7806.84")
        self.assertEqual(fz.parse_cell(None, c), "")
        self.assertEqual(fz.parse_cell("", c), "")

    def test_option_keys_translated(self):
        c = ctrl("c1", "单选", options=[{"key": "k1", "value": "美元"}, {"key": "k2", "value": "人民币"}])
        self.assertEqual(fz.parse_cell(json.dumps(["k1"]), c), "美元")
        self.assertEqual(fz.parse_cell(json.dumps(["k1", "k2"]), c), "美元/人民币")
        self.assertEqual(fz.parse_cell(json.dumps(["k9"]), c), "k9")  # 未知key回退

    def test_member_department_relation(self):
        c = ctrl("c1", "人")
        self.assertEqual(fz.parse_cell(json.dumps([{"fullname": "于占国"}]), c), "于占国")
        self.assertEqual(fz.parse_cell(json.dumps([{"departmentName": "Multi-language"}]), c),
                         "Multi-language")
        self.assertEqual(fz.parse_cell(json.dumps([{"name": "北京多语"}]), c), "北京多语")

    def test_broken_json_falls_back(self):
        c = ctrl("c1", "坏")
        self.assertEqual(fz.parse_cell("[not json", c), "[not json")


class TestRowsToRecords(unittest.TestCase):
    def test_maps_control_names(self):
        controls = [ctrl("ca", "下单日期"), ctrl("cb", "下单预估额/本币")]
        rows = [{"ca": "2026-06-23", "cb": "100.5"}, {"ca": "2026-06-24", "cb": ""}]
        recs = fz.rows_to_records(rows, controls)
        self.assertEqual(recs[0], {"下单日期": "2026-06-23", "下单预估额/本币": "100.5"})
        self.assertEqual(recs[1]["下单预估额/本币"], "")


class TestRequiredColumns(unittest.TestCase):
    CFG = {"columns": {"order_amount": "下单预估额/本币", "order_date": "下单日期"}}

    def test_ok_and_missing(self):
        good = [{"下单预估额/本币": "1", "下单日期": "2026-01-01"}]
        self.assertEqual(fz.check_required_columns(good, self.CFG, "orders"), [])
        bad = [{"别的列": "x"}]
        self.assertEqual(fz.check_required_columns(bad, self.CFG, "orders"),
                         ["下单预估额/本币", "下单日期"])
        self.assertTrue(fz.check_required_columns([], self.CFG, "orders"))  # 空=缺


class TestPagination(unittest.TestCase):
    def test_pages_until_short_page(self):
        pages = [[{"i": n} for n in range(fz.PAGE_SIZE)], [{"i": "last"}]]
        calls = []

        def post(path, body):
            calls.append(body["pageIndex"])
            return {"data": {"data": pages[body["pageIndex"] - 1]}}

        rows = fz.fetch_all_rows(post, "ws1", "app1")
        self.assertEqual(len(rows), fz.PAGE_SIZE + 1)
        self.assertEqual(calls, [1, 2])

    def test_empty_table(self):
        rows = fz.fetch_all_rows(lambda p, b: {"data": {"data": []}}, "ws1", "app1")
        self.assertEqual(rows, [])


class TestFetchSourceStates(unittest.TestCase):
    """三态与产物端到端（临时目录、post 桩）。"""

    def _cfg(self, tmp):
        return {"data_dir": str(tmp),
                "files": {"orders": "下单.xlsx", "receipts": "回款记录.xlsx",
                          "project_detail_stem": "项目明细", "inhouse": "内部译员.xlsx"},
                "columns": {"order_amount": "下单预估额/本币", "order_date": "下单日期"}}

    def _zy(self):
        return {"base_url": "http://x", "app_id": "app1", "account_id": "acc1",
                "md_pss_id": "cookie", "tables": {"orders": {"worksheetId": "ws1"}}}

    def _post_ok(self, path, body):
        if path.endswith("getWorksheetInfo"):
            return {"data": {"template": {"controls": [
                ctrl("ca", "下单日期"), ctrl("cb", "下单预估额/本币"), ctrl("cc", "客户名称")]}}}
        return {"data": {"data": [{"ca": "2026-06-01", "cb": "12.5", "cc": "客户A"}]}}

    def test_no_config_no_local(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            r = fz.fetch_source(self._cfg(Path(td)), "orders", root=Path(td))
            self.assertEqual(r["status"], "no_source")

    def test_no_config_with_local_fallback(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "下单.xlsx").write_bytes(b"PK\x03\x04")
            r = fz.fetch_source(self._cfg(Path(td)), "orders", root=Path(td))
            self.assertEqual(r["status"], "local_fallback")

    def test_fetched_and_readable(self):
        import tempfile
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as td:
            cfg = self._cfg(Path(td))
            r = fz.fetch_source(cfg, "orders", root=Path(td), post=self._post_ok, zy=self._zy())
            self.assertEqual(r["status"], "fetched", r["detail"])
            ws = load_workbook(Path(td) / "下单.xlsx").active
            rows = list(ws.values)
            self.assertEqual(rows[0], ("下单日期", "下单预估额/本币", "客户名称"))
            self.assertEqual(rows[1], ("2026-06-01", "12.5", "客户A"))

    def test_missing_required_column_not_written(self):
        import tempfile

        def post(path, body):
            if path.endswith("getWorksheetInfo"):
                return {"data": {"template": {"controls": [ctrl("cc", "客户名称")]}}}
            return {"data": {"data": [{"cc": "客户A"}]}}

        with tempfile.TemporaryDirectory() as td:
            r = fz.fetch_source(self._cfg(Path(td)), "orders", root=Path(td),
                                post=post, zy=self._zy())
            self.assertEqual(r["status"], "no_source")
            self.assertIn("缺必需列", r["detail"])
            self.assertFalse((Path(td) / "下单.xlsx").exists())  # 坏产物绝不落盘

    def test_api_error_keeps_old_file(self):
        import tempfile

        def post(path, body):
            raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as td:
            old = Path(td) / "下单.xlsx"
            old.write_bytes(b"OLD")
            r = fz.fetch_source(self._cfg(Path(td)), "orders", root=Path(td),
                                post=post, zy=self._zy())
            self.assertEqual(r["status"], "local_fallback")
            self.assertEqual(old.read_bytes(), b"OLD")  # 旧文件原样保留


if __name__ == "__main__":
    unittest.main(verbosity=2)
