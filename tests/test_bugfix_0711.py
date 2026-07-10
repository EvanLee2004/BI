#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-07-11 bug 排查修复回归（台账见 软件工程文档/4_管理过程/11_bug排查与修复台账_20260711.md）。
BUG-01 渲染层转义 / BUG-03 调整定位键失配计数 / BUG-04 日期合理性校验 / BUG-05 export.png 节流。
跑：.venv/bin/python tests/test_bugfix_0711.py"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import charts, loaders, render, schema, server  # noqa: E402
from ingest import adjust  # noqa: E402

EVIL = '<img src=x onerror=alert(1)>"&'


class TestEscaping(unittest.TestCase):
    """BUG-01：台账自由文本进 HTML 必须转义（正文与属性都不许出现裸 <img / 裸引号截断）。"""

    def test_hbar_rows_escapes_group_and_fine(self):
        html = render._hbar_rows([(EVIL, 100.0, [(EVIL, 60.0), ("正常项", 40.0)])], "dept")
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        # data-cat 属性里引号必须转义，否则属性被截断
        self.assertNotIn('data-cat="dept:<', html)

    def test_dept_budget_escapes_name(self):
        html = render.render_dept_budget(
            {"year": 2026, "rows": [{"dept": EVIL, "pct": 50.0, "used": 1.0, "target": 2.0}]})
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_detail_block_escapes_attrs(self):
        html = render._detail_block(f"dept:{EVIL}", EVIL, "inner")
        self.assertNotIn('<img', html)
        self.assertIn("&lt;img", html)

    def test_drow_escapes_name(self):
        html = render._drow(EVIL, -1.0, "")
        self.assertNotIn("<img", html)

    def test_donut_tip_double_escaped(self):
        """data-tip 经 getAttribute 解一层、innerHTML 再解析一层 → 名称须双层转义，<br> 恢复单层。"""
        html = charts.donut([(EVIL, 100.0, "var(--blue)")], "c", "v",
                            detail={EVIL: [(EVIL, 100.0)]})
        self.assertNotIn("<img", html)
        self.assertIn("&amp;lt;img", html)          # 名称双层：属性解码后仍是 &lt;img
        self.assertIn("&lt;br&gt;", html)           # <br> 单层：属性解码后恢复 <br> 供 innerHTML 换行
        self.assertNotIn('data-tip="<', html)

    def test_normal_names_render_unchanged(self):
        html = render._hbar_rows([("市场部", 100.0, [("差旅费", 100.0)])], "dept")
        self.assertIn("市场部", html)
        self.assertIn("差旅费", html)


class TestAdjustMissing(unittest.TestCase):
    """BUG-03：定位键失配的调整单列 missing 计数（不再混进 skipped 静默）。"""

    def test_missing_counted_and_kept_active(self):
        conn = sqlite3.connect(":memory:")
        schema.create_all(conn)
        conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("2026-07-11 10:00:00", "明昊", "std_费用明细", "键已失配", "含税金额", "100", "0", "测试", "剔除", "生效"))
        conn.commit()
        rep = adjust.apply_adjustments(conn, "2026-07-11 10:00:00")
        self.assertEqual(rep["missing"], 1)
        self.assertEqual(rep["skipped"], 0)
        self.assertEqual(rep["applied"], 0)
        # 调整记录保持"生效"待人工看，不被改状态
        st = conn.execute("SELECT 状态 FROM adj_调整记录").fetchone()[0]
        self.assertEqual(st, "生效")

    def test_missing_bubbles_to_reasons(self):
        reasons = server._run_reasons({"fetch": {"status": "fetched"},
                                       "adjust": {"missing": 2, "expired": 0}})
        self.assertTrue(any("失配" in r for r in reasons))


class TestDateSanity(unittest.TestCase):
    """BUG-04：非日期长数字串不许被硬解析成假日期。"""

    def test_invalid_month_day_rejected(self):
        self.assertIsNone(loaders.parse_date_parts("20261345"))      # 13月45日
        self.assertIsNone(loaders.parse_date_parts("2026-13-01"))
        self.assertIsNone(loaders.parse_date_parts("2026-00"))
        self.assertIsNone(loaders.parse_date_parts("1234567890123"))  # 订单号误填（→ 5678月）

    def test_valid_dates_still_parse(self):
        self.assertEqual(loaders.parse_date_parts("20260105"), (2026, 1, 5))
        self.assertEqual(loaders.parse_date_parts("2026/1/5"), (2026, 1, 5))
        self.assertEqual(loaders.parse_date_parts("2026-12-31"), (2026, 12, 31))
        self.assertEqual(loaders.parse_date_parts("2026-07"), (2026, 7, 1))
        self.assertEqual(loaders.parse_date_parts("20260105093000"), (2026, 1, 5))  # 日期+时间连写


class TestExportThrottle(unittest.TestCase):
    """BUG-05：导出截图互斥——已有一张在生成时，连发返回 429 而不是再起一个无头浏览器。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.tmp = tempfile.mkdtemp()
        cfg = loaders.load_config()
        server._state["user_html"] = "<html><body>x</body></html>"
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        cls.client = TestClient(server.create_app(cfg, root=Path(cls.tmp)), follow_redirects=False)

    def test_busy_returns_429(self):
        self.assertTrue(server._EXPORT_LOCK.acquire(blocking=False))
        try:
            r = self.client.get("/export.png")
            self.assertEqual(r.status_code, 429)
        finally:
            server._EXPORT_LOCK.release()


if __name__ == "__main__":
    unittest.main(verbosity=2)
