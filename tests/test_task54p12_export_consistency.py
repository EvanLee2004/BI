#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.12 R-15：明细导出 xlsx 行数/合计与 /api/detail 页面一致；不含工资列/工资行。"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import bu as bu_mod  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import server  # noqa: E402


class TestExportConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.root = Path(tempfile.mkdtemp())
        (cls.root / "数据").mkdir()
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "数据/看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            cls.cfg,
            cls.root,
            [
                {"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"},
                {"账号": "all", "密码": "8888", "权限": "整体", "显示名": "姜总"},
            ],
        )
        bu_mod.save_bu_config(
            cls.cfg,
            cls.root,
            [{"name": "甲BU", "负责人": [], "销售": ["销A"]}],
        )
        conn = db.connect(cls.cfg, cls.root)
        samples = [
            ("e1", "甲BU", "工资", 1000.0, "工资事项"),
            ("e2", "甲BU", "管理费用", 200.0, "办公"),
            ("e3", "甲BU", "市场费用", 300.0, "投放"),
        ]
        for i, (k, bu, cat, amt, matter) in enumerate(samples):
            conn.execute(
                "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
                "预算明细费用类型,预算归属部门,事项,归属月,原值_归属月,已删除)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                (
                    k,
                    "1月",
                    f"2026-01-{i + 1:02d}",
                    money.yuan_to_fen(amt),
                    bu,
                    cat,
                    "细类",
                    "部门",
                    matter,
                    "2026-01",
                    "2026-01",
                ),
            )
        conn.commit()
        conn.close()
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.TestClient = TestClient

    def _login_admin(self):
        c = self.TestClient(self.app)
        r = c.post("/admin/login", data={"account": "admin1", "password": "8888"}, follow_redirects=False)
        self.assertIn(r.status_code, (302, 303), r.text[:200])
        return c

    def test_export_matches_detail_and_no_salary(self):
        import openpyxl

        c = self._login_admin()
        params = {"table": "费用明细", "page_size": 50, "year": "2026"}
        r_page = c.get("/api/detail", params=params)
        self.assertEqual(r_page.status_code, 200, r_page.text[:300])
        page = r_page.json()
        page_rows = page["rows"]
        page_cols = page["columns"]
        self.assertNotIn("工资", {row.get("对应报表大类") for row in page_rows})
        self.assertEqual(len(page_rows), 2, "应仅管理+市场两行")

        r_x = c.get("/api/detail_export", params={"table": "费用明细", "year": "2026"})
        self.assertEqual(r_x.status_code, 200, r_x.text[:200])
        self.assertIn(
            "spreadsheetml",
            r_x.headers.get("content-type", ""),
        )
        wb = openpyxl.load_workbook(io.BytesIO(r_x.content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        self.assertGreaterEqual(len(rows), 2)
        headers = [str(h) for h in rows[0]]
        # 列与页面一致
        self.assertEqual(headers, [str(c) for c in page_cols])
        data = rows[1:]
        self.assertEqual(len(data), len(page_rows))
        # 合计：含税金额
        if "含税金额" in headers:
            idx = headers.index("含税金额")
            exp_sum = 0.0
            for row in page_rows:
                v = row.get("含税金额")
                try:
                    exp_sum += float(v or 0)
                except (TypeError, ValueError):
                    pass
            got_sum = 0.0
            for row in data:
                try:
                    got_sum += float(row[idx] or 0)
                except (TypeError, ValueError):
                    pass
            self.assertAlmostEqual(got_sum, exp_sum, places=2)
        # 无工资字样于大类列
        if "对应报表大类" in headers:
            ci = headers.index("对应报表大类")
            cats = {str(row[ci] or "") for row in data}
            self.assertNotIn("工资", cats)
        wb.close()

    def test_favicon_and_error_html(self):
        c = self.TestClient(self.app)
        r = c.get("/favicon.ico")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.content) > 20)
        r2 = c.get("/this-path-does-not-exist-54p12", headers={"Accept": "text/html"})
        self.assertEqual(r2.status_code, 404)
        self.assertIn("text/html", r2.headers.get("content-type", ""))
        self.assertIn("找不到", r2.text)
        r3 = c.get("/this-path-does-not-exist-54p12", headers={"Accept": "application/json"})
        self.assertEqual(r3.status_code, 404)
        self.assertIn("detail", r3.json())


if __name__ == "__main__":
    unittest.main()
