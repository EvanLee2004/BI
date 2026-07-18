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

    def test_xss_matter_seeded_not_raw_tag_in_shipped_path(self):
        """种一行恶意事项，走真实 /api/v1/vm/ledger + Vue 绑定路径断言。

        1) 数据层可保留尖括号文本（JSON 字符串）；
        2) 白名单列不含隐藏字段；
        3) 前端 LedgerTable 用文本插值（无 v-html/innerHTML）；
        4) html.escape 后不得再出现可解析的 <img ...> 标签串（等同 Vue mustache）。
        """
        import html as htmlmod

        import db_write

        evil = '<img src=x onerror=alert(1)>XSS'
        conn = db.connect(self.cfg, self.tmp)
        try:
            db_write.insert_std_records(
                conn,
                "std_费用明细",
                [
                    {
                        "定位键": "xss-seed-task50",
                        "收单月份": "2026-03",
                        "收单日期": "2026-03-15",
                        "含税金额": 1.0,
                        "业务BU": "数据",
                        "对应报表大类": "管理费用",
                        "预算明细费用类型": "办公费",
                        "预算归属部门": "财务",
                        "事项": evil,
                        "提单人": "不应出现",
                        "提单人部门": "隐",
                        "业务员": "测试员",
                        "配音费合同号": "隐合同",
                        "归属月": "2026-03",
                        "原值_归属月": "2026-03",
                    }
                ],
            )
            conn.commit()
        finally:
            conn.close()

        c = self._admin()
        r = c.get("/api/v1/vm/ledger", params={"page": 1, "page_size": 50, "q": "XSS"})
        self.assertEqual(r.status_code, 200, r.text[:300])
        j = r.json()
        cols = j.get("columns") or []
        for forbidden in db.VIEW_EXPENSE_HIDDEN:
            self.assertNotIn(forbidden, cols)
        rows = j.get("rows") or []
        self.assertTrue(rows, "应查到种入的恶意事项行")
        matter = None
        for row in rows:
            if "XSS" in str(row.get("事项") or ""):
                matter = str(row.get("事项") or "")
                # 响应不得带隐藏列键
                for forbidden in db.VIEW_EXPENSE_HIDDEN:
                    self.assertNotIn(forbidden, row)
                break
        self.assertIsNotNone(matter)
        self.assertIn("<img", matter)  # JSON 数据层是文本

        # 出货前端：禁止把事项灌进 HTML 插槽
        fe = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "LedgerTable.vue").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("v-html", fe)
        self.assertNotIn("innerHTML", fe)
        # Vue {{ }} ≈ html.escape + 文本节点：转义后不得残留可解析标签开角括号
        escaped = htmlmod.escape(matter)
        self.assertNotIn("<img", escaped)
        self.assertIn("&lt;img", escaped)
        # 属性串可作为纯文本残留，但整体不是 HTML 标签（无未转义的 <）
        self.assertNotIn("<", escaped)



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

    def test_vue_mode_skips_legacy_html_bodies(self):
        """任务书51·B1：vue 路径 body_by_period / profit_rank_body 为空（不生成 HTML）。

        注意：tests/support.py 默认 setdefault KANBAN_FRONTEND=legacy（回归壳）；
        本用例显式切 vue 并重建 VM。
        """
        import os
        import viewmodels as vm_mod

        old = os.environ.get("KANBAN_FRONTEND")
        os.environ["KANBAN_FRONTEND"] = "vue"
        try:
            self.assertEqual(vm_mod.frontend_mode(self.cfg), "vue")
            vm = vm_mod.build_cockpit_vm(self.summary, self.cfg)
            self.assertEqual(vm.kpi.body_by_period or {}, {})
            self.assertEqual(vm.pl.body_by_period or {}, {})
            self.assertEqual(vm.expense.body_by_period or {}, {})
            self.assertEqual(vm.rankings.profit_rank_body or {}, {})
            self.assertEqual(vm.trend.svg_html or "", "")
            self.assertEqual(vm.daily_html or "", "")
            self.assertTrue(vm.kpi.cards_by_period.get(self.yk))
            self.assertTrue(vm.pl.table_by_period.get(self.yk))
        finally:
            if old is None:
                os.environ.pop("KANBAN_FRONTEND", None)
            else:
                os.environ["KANBAN_FRONTEND"] = old

    def test_kpi_value_disps_in_legacy_html(self):
        """legacy 打包路径 body HTML 仍含 KPI 主数（与结构化串一致）。
        注：看端壳已删，但 packer 在 KANBAN_FRONTEND=legacy 时仍可造 HTML 供导出/对照。
        """
        import os
        import viewmodels as vm_mod

        old = os.environ.get("KANBAN_FRONTEND")
        os.environ["KANBAN_FRONTEND"] = "legacy"
        try:
            legacy_cfg = dict(self.cfg)
            legacy_cfg["frontend"] = "legacy"
            vm = vm_mod.build_cockpit_vm(self.summary, legacy_cfg)
            cards = vm.kpi.cards_by_period.get(self.yk) or []
            html = (vm.kpi.body_by_period or {}).get(self.yk) or ""
            self.assertTrue(html, "legacy 应生成 KPI HTML")
            for c in cards:
                self.assertIn(c["value_disp"], html, f"KPI {c['label']} 显示串不在 legacy HTML")
        finally:
            if old is None:
                os.environ.pop("KANBAN_FRONTEND", None)
            else:
                os.environ["KANBAN_FRONTEND"] = old

    def test_pl_amt_disps_in_legacy_html(self):
        import os
        import viewmodels as vm_mod

        old = os.environ.get("KANBAN_FRONTEND")
        os.environ["KANBAN_FRONTEND"] = "legacy"
        try:
            legacy_cfg = dict(self.cfg)
            legacy_cfg["frontend"] = "legacy"
            vm = vm_mod.build_cockpit_vm(self.summary, legacy_cfg)
            t = vm.pl.table_by_period.get(self.yk) or {}
            html = (vm.pl.body_by_period or {}).get(self.yk) or ""
            self.assertTrue(html, "legacy 应生成 PL HTML")
            for r in t.get("rows") or []:
                if r.get("is_pct"):
                    continue
                self.assertIn(r["amt_disp"], html, f"PL 行 {r['name']} 金额串缺失")
        finally:
            if old is None:
                os.environ.pop("KANBAN_FRONTEND", None)
            else:
                os.environ["KANBAN_FRONTEND"] = old


if __name__ == "__main__":
    unittest.main()
