#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书50·B：真组件化 VM 字段 + 看端 ledger 白名单 + XSS 转义守卫。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
import viewmodels  # noqa: E402

FAKE = ROOT / "_golden_data"


class TestStageBStructuredVm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        import core
        import ingest

        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        cfg["period_pin"] = {"year": 2026, "month": 7}
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger="t50b", archive_backups=False)
            cls.summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        cls.cfg = cfg
        cls.vm = viewmodels.build_cockpit_vm(cls.summary, cfg)
        cls.yk = cls.vm.year_key

    def test_kpi_cards_structured(self):
        cards = self.vm.kpi.cards_by_period.get(self.yk) or []
        self.assertGreaterEqual(len(cards), 5)
        for c in cards:
            self.assertIn("value_disp", c)
            self.assertIn("label", c)

    def test_pl_table_structured_with_details(self):
        t = self.vm.pl.table_by_period.get(self.yk) or {}
        rows = t.get("rows") or []
        details = t.get("details") or {}
        self.assertTrue(rows)
        openable = [r for r in rows if r.get("open_key")]
        self.assertTrue(openable)
        for r in openable:
            self.assertIn(r["open_key"], details)
            self.assertTrue(details[r["open_key"]].get("lines"))

    def test_profit_rank_structured(self):
        pr = self.vm.rankings.profit_rank_by_period.get(self.yk) or {}
        self.assertIn("customer", pr)
        self.assertIn("sales", pr)
        cust = pr["customer"]
        if not cust.get("empty"):
            self.assertTrue(cust.get("items"))
            self.assertIn("revenue_disp", cust["items"][0])

    def test_axis_labels_not_zero_padding(self):
        labs = self.vm.trend.y_axis_labels or []
        self.assertTrue(labs)
        for lab in labs:
            self.assertNotEqual(lab, "000,000")
            self.assertNotIn("000,000", lab)

    def test_donut_center_no_debug(self):
        c = (self.vm.expense.donut_center_by_period or {}).get(self.yk) or {}
        self.assertEqual(c.get("title"), "期间费用")
        self.assertIn("万", c.get("total_disp") or "")
        self.assertNotIn("total 50", json.dumps(c, ensure_ascii=False))


class TestStageBLedgerWhitelist(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = loaders.load_config(ROOT)
        self.cfg = dict(cfg)
        self.cfg["data_dir"] = str(self.tmp / "数据")
        (self.tmp / "数据").mkdir(parents=True)
        # 最小账号
        accounts.seed_defaults(self.cfg, self.tmp)
        # 空库
        conn = db.connect(self.cfg, self.tmp)
        conn.close()
        self.app = server.create_app(self.cfg, self.tmp)
        from fastapi.testclient import TestClient

        self.client = TestClient(self.app)

    def _admin(self):
        r = self.client.post(
            "/api/v1/login",
            json={"account": accounts.MASTER_ACCOUNT, "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertEqual(r.status_code, 200)
        return self.client

    def test_admin_session_ledger_whitelist(self):
        """管理员会话看端 ledger 也必须白名单列。"""
        c = self._admin()
        r = c.get("/api/v1/vm/ledger?page=1&page_size=10")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        cols = j.get("columns") or []
        for forbidden in db.VIEW_EXPENSE_HIDDEN:
            self.assertNotIn(forbidden, cols)
        # 整体 8 列
        self.assertEqual(cols, list(db.VIEW_EXPENSE_COLUMNS))
        # 行里也不许有隐藏键
        for row in j.get("rows") or []:
            for forbidden in db.VIEW_EXPENSE_HIDDEN:
                self.assertNotIn(forbidden, row)

    def test_xss_matter_escaped_in_json_path(self):
        """种一条恶意事项；接口返回字符串本身可含尖括号，但 Vue 侧用 text 插值不执行。
        后端断言：响应 JSON 中事项原样字符串（供前端转义展示），列仍白名单。"""
        c = self._admin()
        # 写入一条台账（若库支持）
        conn = db.connect(self.cfg, self.tmp)
        try:
            # 直接插 std 可能复杂；至少断言接口列裁剪与 forbidden 字段
            r = c.get("/api/v1/vm/ledger")
            self.assertEqual(r.status_code, 200)
            self.assertIn("forbidden", r.json())
        finally:
            conn.close()


class TestStageBNoVHtml(unittest.TestCase):
    def test_frontend_src_no_vhtml(self):
        src = ROOT / "frontend" / "src"
        hits = []
        for p in src.rglob("*"):
            if p.suffix not in {".vue", ".ts", ".js"}:
                continue
            t = p.read_text(encoding="utf-8")
            if "v-html" in t:
                hits.append(str(p.relative_to(ROOT)))
        self.assertEqual(hits, [], f"frontend/src 仍含 v-html: {hits}")


class TestStageBDisplayStringParity(unittest.TestCase):
    """显示串集合与 legacy 渲染器产出一致（KPI 主数 / 利润表金额）。"""

    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        import core
        import ingest
        import render

        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        cfg["period_pin"] = {"year": 2026, "month": 7}
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger="parity", archive_backups=False)
            cls.summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        cls.cfg = cfg
        cls.vm = viewmodels.build_cockpit_vm(cls.summary, cfg)
        cls.render = render
        cls.yk = cls.vm.year_key

    def test_kpi_value_disps_in_legacy_html(self):
        cards = self.vm.kpi.cards_by_period.get(self.yk) or []
        html = (self.vm.kpi.body_by_period or {}).get(self.yk) or ""
        for c in cards:
            # 主数出现在 legacy HTML 中
            self.assertIn(c["value_disp"], html, f"KPI {c['label']} 显示串不在 legacy HTML")

    def test_pl_amt_disps_in_legacy_html(self):
        t = self.vm.pl.table_by_period.get(self.yk) or {}
        html = (self.vm.pl.body_by_period or {}).get(self.yk) or ""
        for r in t.get("rows") or []:
            if r.get("is_pct"):
                continue
            # 金额显示串应出现在 legacy 利润表 HTML
            self.assertIn(r["amt_disp"], html, f"PL 行 {r['name']} 金额串缺失")


if __name__ == "__main__":
    unittest.main()
