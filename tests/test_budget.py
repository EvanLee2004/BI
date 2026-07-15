#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""年度预算（P-A）+ 管理端业绩目标矩阵页签。"""

from __future__ import annotations

import json
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
import schema  # noqa: E402
import server  # noqa: E402
from profit import build_budget_block  # noqa: E402


def mem_conn():
    conn = sqlite3.connect(":memory:")
    for ddl in list(schema.STD_TABLES.values()) + list(schema.HUMAN_TABLES.values()):
        conn.execute(ddl)
    return conn


class TestBudgetDb(unittest.TestCase):
    def test_set_get_and_history(self):
        conn = mem_conn()
        db.set_budget(conn, "2026", "下单年预算", 8000_0000, "明昊")
        db.set_budget(conn, "2026", "下单年预算", 9000_0000, "陆总")  # 年中改一次
        rows = db.get_budget(conn, "2026")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["金额"], 9000_0000)
        self.assertEqual(rows[0]["经手人"], "陆总")
        hist = conn.execute("SELECT 旧值,新值 FROM manual_预算历史 ORDER BY id").fetchall()
        self.assertEqual(hist, [(None, 8000_0000), (8000_0000, 9000_0000)])

    def test_load_budget_shape_and_scope(self):
        conn = mem_conn()
        db.set_budget(conn, "2026", "回款年预算", 100.0, "明昊")
        db.set_budget(conn, "2026", "回款年预算", 999.0, "明昊", 范围="语言")  # BU 目标
        self.assertEqual(db.load_budget(conn), {"2026": {"回款年预算": 100.0}})
        self.assertEqual(db.load_budget(conn, scope="语言"), {"2026": {"回款年预算": 999.0}})

    def test_empty(self):
        conn = mem_conn()
        self.assertEqual(db.load_budget(conn), {})
        self.assertEqual(db.get_budget(conn), [])


class TestBudgetBlock(unittest.TestCase):
    YEAR_P = {"orders": 500.0, "receipts": 300.0, "gross_margin_pct": 40.0}

    def test_none_when_not_filled(self):
        self.assertIsNone(build_budget_block(None, 2026, self.YEAR_P))
        self.assertIsNone(build_budget_block({}, 2026, self.YEAR_P))
        self.assertIsNone(build_budget_block({"2025": {"下单年预算": 1}}, 2026, self.YEAR_P))  # 别的年份不串

    def test_pct(self):
        b = build_budget_block({"2026": {"下单年预算": 1000.0, "回款年预算": 600.0}}, 2026, self.YEAR_P)
        self.assertAlmostEqual(b["order"]["pct"], 50.0)
        self.assertAlmostEqual(b["receipt"]["pct"], 50.0)
        self.assertEqual(b["order"]["done"], 500.0)

    def test_partial_and_zero_target(self):
        b = build_budget_block({"2026": {"回款年预算": 0.0}}, 2026, self.YEAR_P)
        self.assertIsNone(b["order"])  # 没填下单 → 该项 None
        self.assertIsNone(b["receipt"]["pct"])  # 目标 0 → 完成率 None 不除零


class TestRenderSwitch(unittest.TestCase):
    def test_no_budget_renders_identical(self):
        """红线：没填预算时，回款卡 HTML 与传 None 完全一致（页面一分不变）。"""
        import render

        series = [("1月", 10.0, 20.0, 50.0), ("2月", 12.0, 24.0, 50.0)]
        self.assertEqual(render.render_receipts(series, None), render.render_receipts(series))
        self.assertNotIn("预算", render.render_receipts(series, None))

    def test_budget_renders_line_and_tag(self):
        import render

        series = [("1月", 10.0, 20.0, 50.0), ("2月", 12.0, 24.0, 50.0)]
        budget = {
            "year": 2026,
            "order": {"target": 1200.0, "done": 600.0, "pct": 50.0},
            "receipt": {"target": 2400.0, "done": 600.0, "pct": 25.0},
        }
        html = render.render_receipts(series, budget)
        self.assertIn("月均预算", html)  # 图上预算线（2400/12=200万/月）
        self.assertIn("回款年预算", html)
        self.assertIn("25.0%", html)
        self.assertIn("下单年预算", html)


class TestBudgetMatrixAdminUi(unittest.TestCase):
    """管理端业绩目标独立矩阵页签（数据调整子页签，不跟人工填写筛选）。"""

    def test_console_matrix_structure(self):
        tpl = server.admin_ui_source()
        # 独立页签 + 独立年份 + 矩阵表 + 独立保存
        self.assertIn('data-t="业绩目标"', tpl)
        self.assertIn("showBudget()", tpl)
        self.assertIn('id="budget"', tpl)
        self.assertIn('id="tgY"', tpl)
        self.assertIn('id="bMatrix"', tpl)
        self.assertIn("budgetSave()", tpl)
        self.assertIn("保存业绩目标", tpl)
        # 显示名「年目标」；存储键仍写 data-item=下单年预算
        self.assertIn("下单年目标", tpl)
        self.assertIn("回款年目标", tpl)
        self.assertIn('k:"下单年预算"', tpl)
        self.assertIn('k:"回款年预算"', tpl)
        # 人工填写页不再挂业绩目标区块
        self.assertNotIn("🎯 业绩目标（优先）", tpl)
        self.assertNotIn("业绩目标金额请填", tpl)
        self.assertNotIn("跟随顶部", tpl)
        self.assertNotIn('id="bTbl"', tpl)
        self.assertNotIn('id="bY"', tpl)
        self.assertNotIn('id="bScope"', tpl)
        # 矩阵渲染不读人工填写 mY/mScope
        i = tpl.find("async function bLoad(")
        self.assertNotEqual(i, -1)
        body = tpl[i : i + 2500]
        self.assertIn('getElementById("tgY")', body)
        self.assertNotIn('getElementById("mY")', body)
        self.assertNotIn('getElementById("mScope")', body)
        self.assertIn("/api/bu_config", body)
        self.assertIn("b-sum-tip", tpl)
        self.assertIn("bUpdateSumTips", tpl)


class TestBudgetBatchMultiScope(unittest.TestCase):
    """一次 budget_batch 含全公司+某 BU，读回互不串。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp
        cls.cfg = dict(loaders.load_config())
        cls.cfg["data_dir"] = str(cls.tmp / "数据")
        (cls.tmp / "数据").mkdir(parents=True, exist_ok=True)
        accounts.save_accounts(
            cls.cfg,
            cls.tmp,
            [
                {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
            ],
        )
        conn = db.connect(cls.cfg, root=cls.tmp)
        conn.close()
        # 桩重算：只验写库与读回，不跑完整管道
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>u</html>"
        server._state["admin_html"] = server._admin_page("<html>u</html>", {}, cls.cfg)
        server._state["summary"] = {"meta": {}, "periods": {}}
        cls.app = server.create_app(cls.cfg, root=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _admin(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        return c

    def test_batch_company_and_bu_independent(self):
        c = self._admin()
        # 全公司 20000 万 → 元；BU「数据」 8000 万
        co_yuan = 20000 * 10000
        bu_yuan = 8000 * 10000
        r = c.post(
            "/api/budget_batch",
            json={
                "items": [
                    {"年份": "2026", "指标": "下单年预算", "金额": co_yuan, "范围": "全公司"},
                    {"年份": "2026", "指标": "下单年预算", "金额": bu_yuan, "范围": "数据"},
                    {"年份": "2026", "指标": "回款年预算", "金额": 1000 * 10000, "范围": "全公司"},
                ]
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("count"), 3)

        rows = c.get("/api/budget?year=2026").json()
        by = {(x["指标"], x["范围"]): x["金额"] for x in rows if x["指标"] != "费用年预算"}
        self.assertEqual(by[("下单年预算", "全公司")], co_yuan)
        self.assertEqual(by[("下单年预算", "数据")], bu_yuan)
        self.assertEqual(by[("回款年预算", "全公司")], 1000 * 10000)
        # 互不串：数据 BU 无回款
        self.assertNotIn(("回款年预算", "数据"), by)

        # 管理端静态展示名：万元显示文案在 JS；存储键仍是 下单年预算
        page = server.admin_ui_source()
        self.assertIn("下单年目标", page)
        self.assertIn('k:"下单年预算"', page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
