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

    def test_cell_already_object(self):
        c = ctrl("c1", "人")
        self.assertEqual(fz.parse_cell([{"fullname": "于占国"}], c), "于占国")
        c2 = ctrl("c2", "单选", options=[{"key": "k1", "value": "美元"}])
        self.assertEqual(fz.parse_cell(["k1"], c2), "美元")


class TestRowsToRecords(unittest.TestCase):
    def test_maps_control_names(self):
        controls = [ctrl("ca", "下单日期"), ctrl("cb", "下单预估额/本币")]
        rows = [{"ca": "2026-06-23", "cb": "100.5"}, {"ca": "2026-06-24", "cb": ""}]
        recs = fz.rows_to_records(rows, controls)
        self.assertEqual(recs[0], {"下单日期": "2026-06-23", "下单预估额/本币": "100.5"})
        self.assertEqual(recs[1]["下单预估额/本币"], "")

    def test_duplicate_name_non_empty_wins(self):
        """同名列合并：空值不覆盖有值（防两个"整单交付日期"的空把有值清掉）。"""
        controls = [ctrl("c_val", "整单交付日期"), ctrl("c_empty", "整单交付日期")]
        rows = [{"c_val": "2026-06-30", "c_empty": ""}]      # 有值在前、空在后
        self.assertEqual(fz.rows_to_records(rows, controls)[0]["整单交付日期"], "2026-06-30")
        rows2 = [{"c_val": "", "c_empty": "2026-06-30"}]     # 空在前、有值在后
        self.assertEqual(fz.rows_to_records(rows2, controls)[0]["整单交付日期"], "2026-06-30")


class TestDateSinceFilter(unittest.TestCase):
    CTRLS = [{"controlId": "d1", "controlName": "下单日期", "type": 15}]

    def test_builds_filter_for_known_col(self):
        fc = fz.build_date_since_filter(self.CTRLS, "下单日期", "2026-01-01")
        self.assertEqual(len(fc), 1)
        self.assertEqual(fc[0]["controlId"], "d1")
        self.assertEqual(fc[0]["filterType"], 13)      # 13 = 该日及以后（实测语义）
        self.assertEqual(fc[0]["value"], "2026-01-01")

    def test_empty_when_no_since_or_missing_col(self):
        self.assertEqual(fz.build_date_since_filter(self.CTRLS, "下单日期", ""), [])
        self.assertEqual(fz.build_date_since_filter(self.CTRLS, "不存在的列", "2026-01-01"), [])


class TestAuthExpiry(unittest.TestCase):
    def test_detects_expired(self):
        self.assertTrue(fz._is_auth_expired({"state": 0, "exception": "帐号已退出，请重新登录"}))
        self.assertTrue(fz._is_auth_expired({"state": "0", "message": "请登录"}))

    def test_not_expired_on_success_or_other_error(self):
        self.assertFalse(fz._is_auth_expired({"state": 1, "data": {}}))
        self.assertFalse(fz._is_auth_expired({"state": 0, "exception": "无权限查看该表"}))
        self.assertFalse(fz._is_auth_expired("非字典"))


class TestLoginGuards(unittest.TestCase):
    def test_missing_credentials_raises(self):
        from ingest import login_zhiyun as lz
        for zy in ({}, {"base_url": "http://x"}, {"base_url": "http://x", "username": "u"}):
            with self.assertRaises(lz.LoginError):
                lz.login(zy)


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

    def test_runaway_pagination_raises(self):
        full = [{"i": 1}] * fz.PAGE_SIZE  # 永远回满页 → 必须撞上限而不是死循环
        with self.assertRaises(RuntimeError):
            fz.fetch_all_rows(lambda p, b: {"data": {"data": full}}, "ws1", "app1")

    def test_write_empty_records_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                fz.write_records_xlsx([], Path(td) / "x.xlsx")


class TestZhiyunDefaults(unittest.TestCase):
    """内置连接默认（2026-07-13 明昊拍板进公开库）：文件缺失也有完整连接信息；文件非空值覆盖默认。"""

    def _cfg(self, tmp):
        return {"data_dir": str(tmp)}

    def test_missing_file_yields_defaults(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            zy = fz._load_zhiyun_cfg(self._cfg(Path(td)), Path(td))
            self.assertEqual(zy["base_url"], fz.ZHIYUN_DEFAULTS["base_url"])
            self.assertEqual(zy["app_id"], fz.ZHIYUN_DEFAULTS["app_id"])
            for s in ("orders", "receipts", "project_detail", "inhouse"):
                self.assertTrue(zy["tables"][s]["worksheetId"], f"{s} 表ID应有默认值")
            self.assertEqual(zy["tables"]["inhouse"]["min_rows"], 1000)  # 权限护栏门槛随默认走
            self.assertFalse(zy.get("username"))  # 账号密码绝不内置

    def test_file_overrides_defaults_and_blank_ignored(self):
        import json as _json, tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "智云配置.json").write_text(_json.dumps({
                "username": "u1", "password": "p1", "base_url": "http://other:1",
                "app_id": "",  # 空值不覆盖默认
                "tables": {"orders": {"worksheetId": "custom-ws"},
                           "receipts": {"worksheetId": ""}}}), encoding="utf-8")
            zy = fz._load_zhiyun_cfg(self._cfg(Path(td)), Path(td))
            self.assertEqual(zy["base_url"], "http://other:1")            # 文件非空值胜出
            self.assertEqual(zy["app_id"], fz.ZHIYUN_DEFAULTS["app_id"])  # 空串不覆盖
            self.assertEqual(zy["tables"]["orders"]["worksheetId"], "custom-ws")
            self.assertEqual(zy["tables"]["receipts"]["worksheetId"],
                             fz.ZHIYUN_DEFAULTS["tables"]["receipts"]["worksheetId"])
            self.assertEqual(zy["username"], "u1")

    def test_save_session_creates_missing_file(self):
        """连接走内置默认（无文件）时登录成功也要能持久化 token，否则每轮更新重登。"""
        import json as _json, tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = self._cfg(Path(td))
            fz._save_session(cfg, Path(td), "TOK1", "ACC1")
            d = _json.loads((Path(td) / "智云配置.json").read_text(encoding="utf-8"))
            self.assertEqual((d["md_pss_id"], d["account_id"]), ("TOK1", "ACC1"))


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

    def test_blank_base_url_no_local(self):
        """服务器地址为空（正常合并流程出不来，守卫直接传入）→ 不抓、no_source。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            r = fz.fetch_source(self._cfg(Path(td)), "orders", root=Path(td),
                                zy={"base_url": "", "tables": {}})
            self.assertEqual(r["status"], "no_source")
            self.assertIn("服务器地址为空", r["detail"])

    def test_blank_base_url_with_local_fallback(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "下单.xlsx").write_bytes(b"PK\x03\x04")
            r = fz.fetch_source(self._cfg(Path(td)), "orders", root=Path(td),
                                zy={"base_url": "", "tables": {}})
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

    def test_min_rows_guard_blocks_permission_starved_account(self):
        """行数门槛：抓到的行数 < tables.<源>.min_rows（=账号行级权限不足，如亮晶号在
        任务表只看得到『我的任务』85行）→ 降级、绝不用残缺数据覆盖现有文件。"""
        import tempfile
        zy = self._zy()
        zy["tables"]["orders"]["min_rows"] = 100   # 桩只返回1行 < 100
        with tempfile.TemporaryDirectory() as td:
            old = Path(td) / "下单.xlsx"
            old.write_bytes(b"OLD")
            r = fz.fetch_source(self._cfg(Path(td)), "orders", root=Path(td),
                                post=self._post_ok, zy=zy)
            self.assertEqual(r["status"], "local_fallback")
            self.assertIn("门槛", r["detail"])
            self.assertEqual(old.read_bytes(), b"OLD")   # 现有文件原样保留

    def test_fetch_all_unreachable_server_fast_fallback(self):
        """连通性探测：内网不可达 → 四源整体快速降级（不逐源等超时）。"""
        import json as _json
        import tempfile
        orig = fz._server_reachable
        fz._server_reachable = lambda base_url, timeout=5: False
        try:
            with tempfile.TemporaryDirectory() as td:
                cfg = self._cfg(Path(td))
                (Path(td) / "下单.xlsx").write_bytes(b"PK\x03\x04")
                (Path(td) / "智云配置.json").write_text(_json.dumps(
                    {"base_url": "http://10.9.9.9", "username": "u", "password": "p",
                     "app_id": "a", "account_id": "acc",
                     "tables": {s: {"worksheetId": "w"} for s in fz.SOURCES}}), encoding="utf-8")
                res = fz.fetch_all(cfg, root=Path(td))
                self.assertEqual(set(res), set(fz.SOURCES))
                self.assertEqual(res["orders"]["status"], "local_fallback")   # 有本地文件
                self.assertEqual(res["receipts"]["status"], "no_source")      # 无本地文件
                self.assertIn("不可达", res["orders"]["detail"])
        finally:
            fz._server_reachable = orig

    def test_fetch_all_login_failure_fast_fallback_single_attempt(self):
        """登录失败：四源整体快速降级，且只试一次登录（不逐源重试——慢+密码错反复试有锁号风险）。"""
        import json as _json
        import tempfile
        from ingest import login_zhiyun
        calls = {"n": 0}
        def boom(zy, headless=True):
            calls["n"] += 1
            raise login_zhiyun.LoginError("账号或密码错误")
        orig_login, orig_reach = login_zhiyun.login, fz._server_reachable
        login_zhiyun.login, fz._server_reachable = boom, (lambda b, timeout=5: True)
        try:
            with tempfile.TemporaryDirectory() as td:
                cfg = self._cfg(Path(td))
                (Path(td) / "下单.xlsx").write_bytes(b"PK\x03\x04")
                (Path(td) / "智云配置.json").write_text(_json.dumps(
                    {"base_url": "http://x", "username": "u", "password": "bad",
                     "app_id": "a", "account_id": "acc", "md_pss_id": "",
                     "tables": {s: {"worksheetId": "w"} for s in fz.SOURCES}}), encoding="utf-8")
                res = fz.fetch_all(cfg, root=Path(td))
                self.assertEqual(calls["n"], 1)                       # 只登录一次
                self.assertEqual(res["orders"]["status"], "local_fallback")
                self.assertIn("登录失败", res["orders"]["detail"])
        finally:
            login_zhiyun.login, fz._server_reachable = orig_login, orig_reach

    def test_make_post_no_relogin_loop_after_failure(self):
        """共享 post：token 失效且重登失败后，后续调用不再反复起浏览器登录。"""
        from ingest import login_zhiyun
        calls = {"n": 0}
        def boom(zy, headless=True):
            calls["n"] += 1
            raise login_zhiyun.LoginError("密码错")
        orig = login_zhiyun.login
        login_zhiyun.login = boom
        try:
            import types, sys
            zy = {"base_url": "http://x", "account_id": "a", "md_pss_id": "DEAD",
                  "username": "u", "password": "bad"}
            # 桩掉 requests：永远返回 state==0 需登录
            class _R:
                status_code = 200
                def json(self): return {"state": 0, "exception": "请重新登录"}
                def raise_for_status(self): pass
            fake = types.ModuleType("requests")
            fake.post = lambda *a, **k: _R()
            sys.modules["requests"] = fake
            try:
                post = fz._make_post(zy, cfg={}, root=None)
                for _ in range(3):
                    with self.assertRaises(Exception):
                        post("Worksheet/GetFilterRows", {})
            finally:
                del sys.modules["requests"]
            self.assertEqual(calls["n"], 1)   # 三次调用只登录一次
        finally:
            login_zhiyun.login = orig

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
