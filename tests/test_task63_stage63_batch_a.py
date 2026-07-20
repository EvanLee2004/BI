#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书63 批次A：F-02 批量原子 / H-04 分摊·去税历史 / H-03 撤销审计。

跑：.venv/bin/python tests/run_test.py tests/test_task63_stage63_batch_a.py
红线：既有测试只增不改；golden 零 diff。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402


class TestF02BatchAtomicity(unittest.TestCase):
    """F-02：批量第 2 条非法 → 第 1 条未落库、HTTP 4xx。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        # 建空库（connect 会 create_all）
        c = db.connect(cls.cfg, cls.root)
        c.close()
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "<html>ADMIN</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.cookie = r.cookies.get(server.COOKIE)
        cls.hdr = {"Cookie": f"{server.COOKIE}={cls.cookie}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def _conn(self):
        return db.connect(self.cfg, self.root)

    def test_manual_batch_second_illegal_no_partial_write(self):
        """合法 + 未知项目：整批 400，库无任何手填行。"""
        conn = self._conn()
        before = conn.execute("SELECT COUNT(*) FROM manual_手填").fetchone()[0]
        conn.close()

        r = self.client.post(
            "/api/manual_batch",
            headers=self.hdr,
            json={
                "归属月": "2026-07",
                "items": [
                    {"项目": "营销人力成本", "金额": 1000},
                    {"项目": "不存在的手填项XYZ", "金额": 2000},
                ],
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("未知手填项目", r.text)

        conn = self._conn()
        after = conn.execute("SELECT COUNT(*) FROM manual_手填").fetchone()[0]
        hit = conn.execute(
            "SELECT 金额 FROM manual_手填 WHERE 归属月=? AND 项目=?",
            ("2026-07", "营销人力成本"),
        ).fetchone()
        conn.close()
        self.assertEqual(after, before)
        self.assertIsNone(hit)

    def test_manual_batch_all_valid_commits(self):
        r = self.client.post(
            "/api/manual_batch",
            headers=self.hdr,
            json={
                "归属月": "2026-08",
                "items": [
                    {"项目": "营销人力成本", "金额": 111},
                    {"项目": "营销人力成本", "金额": 222},  # 覆盖同键，仍一次事务
                ],
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "ok")
        conn = self._conn()
        row = conn.execute(
            "SELECT 金额 FROM manual_手填 WHERE 归属月=? AND 项目=?",
            ("2026-08", "营销人力成本"),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(int(row[0]), 22200)  # 222 元 → 分

    def test_budget_batch_second_illegal_no_partial_write(self):
        conn = self._conn()
        before = conn.execute("SELECT COUNT(*) FROM manual_预算").fetchone()[0]
        conn.close()

        r = self.client.post(
            "/api/budget_batch",
            headers=self.hdr,
            json={
                "items": [
                    {"年份": "2026", "指标": "下单年预算", "金额": 1000000, "范围": "全公司"},
                    {"年份": "2026", "指标": "不存在的预算指标XYZ", "金额": 1, "范围": "全公司"},
                ],
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("未知预算指标", r.text)

        conn = self._conn()
        after = conn.execute("SELECT COUNT(*) FROM manual_预算").fetchone()[0]
        hit = conn.execute(
            "SELECT 金额 FROM manual_预算 WHERE 年份=? AND 指标=? AND 范围=?",
            ("2026", "下单年预算", "全公司"),
        ).fetchone()
        conn.close()
        self.assertEqual(after, before)
        self.assertIsNone(hit)

    def test_budget_batch_all_valid_commits(self):
        r = self.client.post(
            "/api/budget_batch",
            headers=self.hdr,
            json={
                "items": [
                    {"年份": "2027", "指标": "下单年预算", "金额": 5000000, "范围": "全公司"},
                ],
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        conn = self._conn()
        row = conn.execute(
            "SELECT 金额 FROM manual_预算 WHERE 年份=? AND 指标=? AND 范围=?",
            ("2027", "下单年预算", "全公司"),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(int(row[0]), 500000000)  # 500 万 元 → 分


class TestH04AllocDetaxHistory(unittest.TestCase):
    """H-04：改→删→再设后历史表行数与旧/新值正确。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = loaders.load_config()
        self.conn = db.connect(self.cfg, Path(self.tmp))

    def tearDown(self):
        self.conn.close()

    def test_alloc_ratio_history_set_delete_set(self):
        db.set_alloc_ratio(self.conn, "2026-07", "游戏", 30, "tester")
        db.set_alloc_ratio(self.conn, "2026-07", "游戏", None, "tester")  # 删
        db.set_alloc_ratio(self.conn, "2026-07", "游戏", 40, "tester")
        rows = self.conn.execute(
            "SELECT 旧值,新值 FROM manual_分摊比例历史 WHERE 归属月=? AND BU=? ORDER BY id",
            ("2026-07", "游戏"),
        ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0], None)
        self.assertEqual(float(rows[0][1]), 30.0)
        self.assertEqual(float(rows[1][0]), 30.0)
        self.assertIsNone(rows[1][1])  # 删除 新值=NULL
        self.assertIsNone(rows[2][0])  # 删后再生：旧值空
        self.assertEqual(float(rows[2][1]), 40.0)
        # 生效表只剩最新
        self.assertEqual(db.get_alloc_ratios(self.conn, "2026-07"), {"游戏": 40.0})

    def test_detax_rate_history_set_delete_set(self):
        db.set_detax_rate(self.conn, "房租", 9, "tester")
        db.set_detax_rate(self.conn, "房租", None, "tester")
        db.set_detax_rate(self.conn, "房租", 6, "tester")
        rows = self.conn.execute(
            "SELECT 旧值,新值 FROM manual_去税率历史 WHERE 费用类别=? ORDER BY id",
            ("房租",),
        ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[0][0])
        self.assertEqual(float(rows[0][1]), 9.0)
        self.assertEqual(float(rows[1][0]), 9.0)
        self.assertIsNone(rows[1][1])
        self.assertIsNone(rows[2][0])
        self.assertEqual(float(rows[2][1]), 6.0)
        self.assertEqual(db.load_detax_rates(self.conn), {"房租": 6.0})


class TestH03RevokeAudit(unittest.TestCase):
    """H-03：revoke/rearm/revoke_all 写 manual_配置变更 审计。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        conn = db.connect(cls.cfg, cls.root)
        conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
            " VALUES('K63','SO63','客','传统营销','2026-07-15',100000,0,'2026-07','2026-07-15','2026-07',0)"
        )
        conn.commit()
        conn.close()
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "<html>ADMIN</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def _conn(self):
        return db.connect(self.cfg, self.root)

    def test_revoke_writes_audit_with_reason(self):
        conn = self._conn()
        aid = db.add_adjustment(conn, "明昊", "std_收入明细", "K63", "交付额", "2000", "待撤", "改值")
        conn.close()

        r = self.client.post(
            f"/api/adjust/{aid}/revoke",
            headers=self.hdr,
            json={"reason": "源头已更正"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "ok")

        conn = self._conn()
        rows = conn.execute(
            "SELECT 操作账号,类别,摘要 FROM manual_配置变更 WHERE 类别=? ORDER BY id DESC LIMIT 5",
            ("调整",),
        ).fetchall()
        conn.close()
        self.assertTrue(rows, "应有调整类审计")
        acc, cat, tip = rows[0]
        self.assertTrue(acc)
        self.assertEqual(cat, "调整")
        self.assertIn(f"撤销调整#{aid}", tip)
        self.assertIn("源头已更正", tip)
        self.assertIn("std_收入明细", tip)

    def test_rearm_writes_audit(self):
        conn = self._conn()
        # 直接插一条过期疑似，便于 rearm
        conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "2026-07-01 10:00:00",
                "明昊",
                "std_收入明细",
                "K63",
                "交付额",
                "100000",
                "150000",
                "坚持测",
                "改值",
                "过期疑似",
            ),
        )
        conn.commit()
        aid = conn.execute("SELECT id FROM adj_调整记录 WHERE 状态='过期疑似' ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()

        r = self.client.post(
            f"/api/adjust/{aid}/rearm",
            headers=self.hdr,
            json={"reason": "仍用我的数"},
        )
        self.assertEqual(r.status_code, 200, r.text)

        conn = self._conn()
        tip = conn.execute(
            "SELECT 摘要 FROM manual_配置变更 WHERE 类别='调整' AND 摘要 LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%坚持调整#{aid}%",),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(tip)
        self.assertIn("仍用我的数", tip[0])

    def test_revoke_all_expired_writes_audit(self):
        conn = self._conn()
        conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "2026-07-02 10:00:00",
                "明昊",
                "std_收入明细",
                "K63",
                "客户",
                "客A",
                "客B",
                "批撤",
                "改值",
                "过期疑似",
            ),
        )
        conn.commit()
        conn.close()

        r = self.client.post(
            "/api/adjust/expired/revoke_all",
            headers=self.hdr,
            json={"reason": "一键听源头"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        n = int(r.json().get("revoked") or 0)
        if n > 0:
            conn = self._conn()
            tip = conn.execute(
                "SELECT 摘要 FROM manual_配置变更 WHERE 类别='调整' AND 摘要 LIKE '%批量撤销%' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            self.assertIsNotNone(tip)
            self.assertIn("一键听源头", tip[0])

    def test_ledger_view_prompt_reason(self):
        """管理端 LedgerView 撤销/坚持/批量走 prompt + reason。"""
        src = (ROOT / "frontend/src/admin/views/LedgerView.vue").read_text(encoding="utf-8")
        self.assertIn("ElMessageBox.prompt", src)
        self.assertIn("reason", src)
        self.assertIn("/api/adjust/expired/revoke_all", src)


if __name__ == "__main__":
    unittest.main()
