#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A5 红线：BU 账号取不到其他 BU 的费用明细（403 或空且不泄漏）。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestBuLedgerIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import loaders, server, bu as bu_mod, db as dbmod
        from fastapi.testclient import TestClient

        cls.root = Path(tempfile.mkdtemp())
        (cls.root / "数据").mkdir()
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "数据/看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        acc_path = cls.root / "数据" / "看板账号.json"
        acc_path.write_text(
            json.dumps(
                {
                    "accounts": [
                        {"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"},
                        {"账号": "bu_a", "密码": "8888", "权限": "BU", "可见BU": ["甲BU"], "显示名": "甲"},
                        {"账号": "bu_b", "密码": "8888", "权限": "BU", "可见BU": ["乙BU"], "显示名": "乙"},
                        {"账号": "all", "密码": "8888", "权限": "整体", "显示名": "全"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bu_mod.save_bu_config(
            cls.cfg,
            cls.root,
            [
                {"name": "甲BU", "负责人": [], "销售": ["销A"]},
                {"name": "乙BU", "负责人": [], "销售": ["销B"]},
            ],
        )
        conn = dbmod.connect(cls.cfg, cls.root)
        for i, (bu, amt) in enumerate([("甲BU", 100.0), ("乙BU", 200.0), ("甲BU", 50.0)]):
            conn.execute(
                "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
                "预算明细费用类型,预算归属部门,事项,归属月,原值_归属月,已删除)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                (
                    f"k{i}",
                    "1月",
                    "2026-01-0%d" % (i + 1),
                    amt,
                    bu,
                    "管理费用",
                    "办公",
                    "财务",
                    f"事项{i}",
                    "2026-01",
                    "2026-01",
                ),
            )
        conn.commit()
        conn.close()
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.TestClient = TestClient

    def _client_as(self, account, password="8888", admin=False):
        c = self.TestClient(self.app)
        path = "/admin/login" if admin else "/login"
        r = c.post(path, data={"account": account, "password": password}, follow_redirects=False)
        self.assertIn(r.status_code, (303, 302), f"login {account}: {r.status_code} {r.text[:200]}")
        return c

    def test_bu_a_cannot_see_bu_b(self):
        c = self._client_as("bu_a")
        r = c.get("/api/detail", params={"table": "费用明细", "bu": "乙BU"})
        self.assertEqual(r.status_code, 403, r.text)
        r = c.get("/api/detail", params={"table": "费用明细", "bu": "甲BU"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertGreaterEqual(d["total"], 1)
        for row in d["rows"]:
            self.assertEqual(row.get("业务BU"), "甲BU")
        r2 = c.get("/api/detail", params={"table": "费用明细"})
        self.assertEqual(r2.status_code, 200)
        for row in r2.json()["rows"]:
            self.assertEqual(row.get("业务BU"), "甲BU")

    def test_bu_cannot_open_other_tables(self):
        c = self._client_as("bu_b")
        r = c.get("/api/detail", params={"table": "收入明细"})
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_admin_sees_all(self):
        c = self._client_as("admin1", admin=True)
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 50})
        self.assertEqual(r.status_code, 200, r.text)
        bus = {row.get("业务BU") for row in r.json()["rows"]}
        self.assertIn("甲BU", bus)
        self.assertIn("乙BU", bus)


if __name__ == "__main__":
    unittest.main(verbosity=2)
