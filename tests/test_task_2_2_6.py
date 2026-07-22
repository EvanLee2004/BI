#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.6 门禁：下单未填部门 · 本页表筛批量归类 UX + POST /api/adjust/batch。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db
import loaders
import server  # noqa: E402


def _seed_orders(cfg, root):
    import money

    conn = db.connect(cfg, root)
    rows = [
        # 定位键, 订单号, 日期, 金额元, 部门, 销售, 已删除
        ("O1", "SO1", "2026-03-01", 1000.0, "部门B", "张三", 0),
        ("O2", "SO2", "2026-03-05", 2000.0, "", "李四", 0),  # 未填
        ("O3", "SO3", "2026-04-02", 3000.0, None, "王五", 0),  # 未填
        ("O4", "SO4", "2026-04-03", 0.0, "", "赵六", 0),  # 金额0 不算
        ("O5", "SO5", "2026-04-04", 500.0, "  ", "钱七", 0),  # 空白 → 未填
        ("O6", "SO6", "2026-04-05", 800.0, "", "孙八", 1),  # 已删
        ("O7", "SO7", "2026-05-06", 4000.0, "部门A", "周九", 0),
    ]
    for k, o, d, a, dep, sal, rm in rows:
        fen = money.yuan_to_fen(a) or 0
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (k, o, d, fen, dep, sal, d[:7], d[:7], rm),
        )
    conn.commit()
    return conn


class TestOrderDeptViewSource226(unittest.TestCase):
    """源码契约：无顶栏销售筛选；确认含「仅当前页」；走 bulk API。"""

    def setUp(self):
        self.src = (ROOT / "frontend/src/admin/views/OrderDeptView.vue").read_text(encoding="utf-8")

    def test_no_toolbar_sales_filter_label(self):
        self.assertNotIn("本页销售筛选", self.src)
        # 顶栏不应再有 salesFilter 绑定（函数名 salesFilterOptions 是表头选项，允许）
        self.assertNotIn("v-model=\"salesFilter\"", self.src)
        self.assertNotIn("const salesFilter", self.src)

    def test_confirm_says_current_page_only(self):
        self.assertIn("仅当前页", self.src)
        self.assertIn("笔数", self.src)
        self.assertIn("金额合计", self.src)
        self.assertIn("不会处理其它页", self.src)

    def test_batch_uses_filtered_rows_and_bulk_api(self):
        self.assertIn("filteredRows", self.src)
        self.assertIn("/api/adjust/batch", self.src)
        self.assertIn("定位键列表", self.src)
        self.assertIn("对本页表筛结果批量归入", self.src)
        self.assertIn("批量归入部门", self.src)

    def test_single_save_still_uses_adjust(self):
        self.assertIn("'/api/adjust'", self.src)
        self.assertIn("saveOne", self.src)


class TestUnfilledDeptWhereUnchanged(unittest.TestCase):
    def test_constant_still_requires_nonzero_amount(self):
        from db.constants import UNFILLED_DEPT_WHERE

        w = UNFILLED_DEPT_WHERE
        self.assertIn("部门", w)
        self.assertIn("下单预估额", w)
        self.assertIn("<>0", w.replace(" ", ""))
        self.assertIn("IS NULL", w)


class TestAdjustBatchApi226(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        _seed_orders(cls.cfg, cls.root).close()
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None, **k: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "ready"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def test_batch_requires_login(self):
        r = self.anon.post(
            "/api/adjust/batch",
            json={
                "目标表": "std_下单",
                "字段": "部门",
                "新值": "部门A",
                "定位键列表": ["O2"],
            },
        )
        self.assertEqual(r.status_code, 401)

    def test_batch_empty_list_400(self):
        r = self.client.post(
            "/api/adjust/batch",
            headers=self.hdr,
            json={
                "目标表": "std_下单",
                "字段": "部门",
                "新值": "部门A",
                "定位键列表": [],
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_batch_missing_key_400_no_write(self):
        before = self.client.get("/api/adjustments", headers=self.hdr).json()
        r = self.client.post(
            "/api/adjust/batch",
            headers=self.hdr,
            json={
                "目标表": "std_下单",
                "字段": "部门",
                "新值": "部门A",
                "原因": "测·预检失败",
                "类型": "改值",
                "定位键列表": ["O2", "NO_SUCH_KEY"],
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        after = self.client.get("/api/adjustments", headers=self.hdr).json()
        self.assertEqual(len(after), len(before), "策略A：预检失败整批不写库")

    def test_batch_dept_ok_writes_adjustments(self):
        """成功批量：写台账 count=2（recompute 在本测中 mock，不验 unfilled 实落）。"""
        r = self.client.post(
            "/api/adjust/batch",
            headers=self.hdr,
            json={
                "目标表": "std_下单",
                "字段": "部门",
                "新值": "部门A",
                "原因": "异常处理·批量归类·本页表筛",
                "类型": "改值",
                "定位键列表": ["O2", "O5"],
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("status"), "ok")
        self.assertEqual(body.get("count"), 2)
        self.assertEqual(len(body.get("adj_ids") or []), 2)
        adjs = self.client.get("/api/adjustments", headers=self.hdr).json()
        by_key = {
            a["定位键"]: a
            for a in adjs
            if a.get("字段") == "部门" and a.get("状态") == "生效"
        }
        self.assertEqual(by_key["O2"]["新值"], "部门A")
        self.assertEqual(by_key["O5"]["新值"], "部门A")


class TestVersionBump226(unittest.TestCase):
    def test_version_files(self):
        """2.2.6 条目保留在 changelog；产品 VERSION 可继续前进（≥2.2.6）。"""
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        # 语义：当前至少 2.2.6；2.2.7+ 也通过
        parts = [int(x) for x in ver.split(".")[:3]]
        self.assertGreaterEqual(parts, [2, 2, 6], ver)
        self.assertIn("2.2.6", (ROOT / "src/version.py").read_text(encoding="utf-8"))
        self.assertIn("## [2.2.6]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
