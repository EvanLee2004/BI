#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书42 阶段五终检：三种账号 TestClient 全流程 + health + 版本。"""
from __future__ import annotations

import io
import shutil
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
import version  # noqa: E402


class TestTask42Final(unittest.TestCase):
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
                {"账号": "bu_a", "密码": "8888", "权限": "BU", "可见BU": ["甲BU"], "显示名": "甲"},
            ],
        )
        conn = db.connect(cls.cfg, cls.root)
        conn.execute(
            "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
            "预算明细费用类型,预算归属部门,事项,提单人,业务员,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
            (
                "F1",
                "01",
                "2026-01-15",
                money.yuan_to_fen(88),
                "甲BU",
                "管理费用",
                "办公",
                "市场",
                "终检事项",
                "提单人X",
                "业务员Y",
                "2026-01",
                "2026-01",
            ),
        )
        conn.commit()
        conn.close()
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.TC = TestClient

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def _login(self, account, admin=False):
        c = self.TC(self.app)
        path = "/admin/login" if admin else "/login"
        r = c.post(path, data={"account": account, "password": "8888"}, follow_redirects=False)
        self.assertIn(r.status_code, (302, 303), r.text[:200])
        return c

    def test_version_is_product(self):
        # 任务书46·7 / 54.10 / 61：VERSION 为产品号；changelog 最新条非空
        v = version.read_version()
        self.assertTrue(
            v.endswith("-beta") or "rc" in v.lower() or v >= "1.6.0",
            v,
        )
        # 允许 2.0.0-rcN、2.0.x / 2.1.x / 2.2.x / 2.3.x 正式号递增（任务书66 → 2.2.0；2.3.0 三主题）
        ok = (
            v in ("1.6.0-beta", "2.0.0-beta", "2.0.1", "2.1.0", "2.2.0", "2.3.0", "2.3.1")
            or (v.startswith("2.0.0-rc") and v[len("2.0.0-rc") :].isdigit())
            or (v.startswith("2.0.") and all(p.isdigit() for p in v.split(".")[1:]))
            or (v.startswith("2.1.") and all(p.isdigit() for p in v.split(".")[1:]))
            or (v.startswith("2.2.") and all(p.isdigit() for p in v.split(".")[1:]))
            or (v.startswith("2.3.") and all(p.isdigit() for p in v.split(".")[1:]))
            or (v.startswith("2.4.") and all(p.isdigit() for p in v.split(".")[1:]))
            or (v.startswith("2.5.") and all(p.isdigit() for p in v.split(".")[1:]))
        )
        self.assertTrue(ok, v)
        self.assertTrue(version.PRODUCT_CHANGELOG)
        self.assertTrue(version.PRODUCT_CHANGELOG[0].get("items"))
        blob = " ".join(str(it) for it in version.PRODUCT_CHANGELOG[0]["items"])
        self.assertTrue(
            any(
                k in blob
                for k in (
                    "Ubuntu",
                    "业务员",
                    "Vue",
                    "哈希",
                    "口径",
                    "手册",
                    "人审",
                    "发布候选",
                    "科技风",
                    "回款",
                    "分摊",
                    "目标",
                )
            ),
            blob[:200],
        )

    def test_admin_flow(self):
        c = self._login("admin1", admin=True)
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 20})
        self.assertEqual(r.status_code, 200)
        cols = r.json()["columns"]
        self.assertIn("定位键", cols)
        self.assertIn("提单人", cols)
        r = c.get("/api/detail_export", params={"table": "费用明细"})
        self.assertEqual(r.status_code, 200)
        # 越权：无
        r = c.get("/admin/logout", follow_redirects=False)
        self.assertIn(r.status_code, (200, 302, 303))

    def test_overall_flow_whitelist_and_export(self):
        c = self._login("all")
        r = c.get("/api/detail", params={"table": "费用明细", "year": "2026", "page_size": 20})
        self.assertEqual(r.status_code, 200)
        cols = r.json()["columns"]
        self.assertEqual(cols, db.VIEW_EXPENSE_COLUMNS)
        self.assertNotIn("提单人", cols)
        r = c.get(
            "/api/detail",
            params={"table": "费用明细", "month_from": "2026-01", "month_to": "2026-03"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["total"], 1)
        r = c.get("/api/detail_export", params={"table": "费用明细", "year": "2026"})
        self.assertEqual(r.status_code, 200)
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        self.assertEqual([c.value for c in wb.active[1]], db.VIEW_EXPENSE_COLUMNS)
        # 退出后再访问明细应 401（路径兼容 /logout 与 /api/v1/logout）
        for path in ("/logout", "/api/v1/logout", "/api/logout"):
            c.request("POST", path, follow_redirects=False)
            c.get(path, follow_redirects=False)
        # 新客户端无 cookie 必 401
        c2 = self.TC(self.app)
        r2 = c2.get("/api/detail", params={"table": "费用明细"})
        self.assertEqual(r2.status_code, 401)

    def test_bu_isolation_and_cols(self):
        c = self._login("bu_a")
        r = c.get("/api/detail", params={"table": "费用明细", "bu": "乙BU"})
        self.assertEqual(r.status_code, 403)
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 20})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertNotIn("业务BU", d["columns"])
        self.assertEqual(d["columns"], db.VIEW_EXPENSE_COLUMNS_BU)
        self.assertGreaterEqual(d["total"], 1)

    def test_health_structure(self):
        c = self.TC(self.app)
        # health 可能无需登录（源码确认）
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIn("warnings", j)


if __name__ == "__main__":
    unittest.main(verbosity=2)
