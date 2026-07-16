#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书41：看端明细白名单 + 月区间真筛 + 卡头预算小字删除 + 尺寸/比例守卫。

活体浏览器验收留给 Claude；本文件用 TestClient + DOM/结构断言覆盖可验项。
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import server  # noqa: E402


HIDDEN = ("定位键", "收单月份", "归属月", "提单人", "提单人部门")
VIEW_COLS = list(db.VIEW_EXPENSE_COLUMNS)


def _fen(y):
    return money.yuan_to_fen(y)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = "数据"
        self.cfg["db_path"] = "数据/看板.db"
        self.cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"},
                {"账号": "all", "密码": "8888", "权限": "整体", "显示名": "姜总"},
                {"账号": "bu_a", "密码": "8888", "权限": "BU", "可见BU": ["甲BU"], "显示名": "甲"},
            ],
        )
        # 最小库 + 费用明细
        conn = db.connect(self.cfg, self.tmp)
        rows = [
            ("K1", "01", "2026-01-10", _fen(100), "甲BU", "管理费用", "办公费", "市场部", "事A", "提A", "提部", "业A", "", "2026-01"),
            ("K2", "02", "2026-02-10", _fen(200), "甲BU", "管理费用", "差旅费", "市场部", "事B", "提B", "提部", "业B", "", "2026-02"),
            ("K3", "04", "2026-04-10", _fen(300), "甲BU", "管理费用", "招待费", "市场部", "事C", "提C", "提部", "业C", "", "2026-04"),
            ("K4", "03", "2026-03-10", _fen(150), "乙BU", "管理费用", "办公费", "市场部", "事D", "提D", "提部", "业D", "", "2026-03"),
        ]
        for r in rows:
            conn.execute(
                "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
                "预算明细费用类型,预算归属部门,事项,提单人,提单人部门,业务员,配音费合同号,归属月,原值_归属月,已删除)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                r + (r[13],),
            )
        conn.commit()
        conn.close()
        self.app = server.create_app(self.cfg, root=self.tmp)
        from fastapi.testclient import TestClient

        self.TC = TestClient

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _login_view(self, account="all"):
        c = self.TC(self.app)
        r = c.post("/login", data={"account": account, "password": "8888"}, follow_redirects=False)
        self.assertIn(r.status_code, (302, 303), r.text[:200])
        return c


class TestViewWhitelist(unittest.TestCase):
    def test_whitelist_order(self):
        self.assertEqual(
            db.VIEW_EXPENSE_COLUMNS,
            [
                "收单日期",
                "事项",
                "含税金额",
                "对应报表大类",
                "预算明细费用类型",
                "业务员",
                "预算归属部门",
                "业务BU",
                "配音费合同号",
            ],
        )
        self.assertNotIn("业务BU", db.VIEW_EXPENSE_COLUMNS_BU)
        for h in HIDDEN:
            self.assertNotIn(h, db.VIEW_EXPENSE_COLUMNS)


class TestDetailAudience(_Base):
    def test_view_columns_whitelist(self):
        c = self._login_view()
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 50, "year": "2026"})
        self.assertEqual(r.status_code, 200, r.text)
        cols = r.json()["columns"]
        self.assertEqual(cols, VIEW_COLS)
        for h in HIDDEN:
            self.assertNotIn(h, cols)
        self.assertIn("业务员", cols)
        self.assertNotIn("提单人", cols)

    def test_admin_full_columns(self):
        conn = db.connect(self.cfg, self.tmp)
        d = db.query_detail(conn, "费用明细", year="2026", page_size=50, audience="admin")
        conn.close()
        self.assertIn("定位键", d["columns"])
        self.assertIn("提单人", d["columns"])
        self.assertIn("归属月", d["columns"])

    def test_export_follows_view(self):
        c = self._login_view()
        r = c.get("/api/detail_export", params={"table": "费用明细", "year": "2026"})
        self.assertEqual(r.status_code, 200, r.text)
        import openpyxl
        import io

        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb.active
        headers = [c.value for c in ws[1]]
        self.assertEqual(headers, VIEW_COLS)
        for h in HIDDEN:
            self.assertNotIn(h, headers)

    def test_month_range_q1(self):
        c = self._login_view()
        r = c.get(
            "/api/detail",
            params={
                "table": "费用明细",
                "month_from": "2026-01",
                "month_to": "2026-03",
                "page_size": 50,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        months = set()
        for row in d["rows"]:
            months.add(str(row.get("收单日期") or "")[:7])
        self.assertTrue(months)
        for m in months:
            self.assertGreaterEqual(m, "2026-01")
            self.assertLessEqual(m, "2026-03")
        self.assertEqual(d["total"], 3)  # K1 K2 K4

    def test_bu_omits_bu_col(self):
        conn = db.connect(self.cfg, self.tmp)
        d = db.query_detail(conn, "费用明细", year="2026", bu="甲BU", audience="view_bu", page_size=50)
        conn.close()
        self.assertNotIn("业务BU", d["columns"])
        self.assertEqual(d["columns"], db.VIEW_EXPENSE_COLUMNS_BU)


class TestBudgetTagGone(unittest.TestCase):
    def test_rc_card_template_slot_empty(self):
        import render

        self.assertEqual(render._budget_tag({"receipt": {"target": 1, "pct": 9999}}), "")

    def test_theme_kpi_vars(self):
        css = (ROOT / "static/css/theme.css").read_text(encoding="utf-8")
        self.assertIn("--fs-kpi", css)
        self.assertIn("0.45fr", css)
        self.assertIn("0.55fr", css)
        self.assertIn("mlMFrom", (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8"))
        self.assertIn("mlMTo", (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8"))
        js = (ROOT / "static/js/cockpit.js").read_text(encoding="utf-8")
        self.assertIn("month_from", js)
        self.assertIn("month_to", js)
        self.assertIn("_syncLedgerYm", js)


class TestUiNoAmountMath(unittest.TestCase):
    def test_cockpit_js_no_amount_ops(self):
        import re

        js = (ROOT / "static/js/cockpit.js").read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        self.assertNotRegex(code, r"\bparseFloat\b|\bNumber\s*\(")


if __name__ == "__main__":
    unittest.main(verbosity=2)
