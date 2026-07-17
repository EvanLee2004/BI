#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·2：VM schema 快照 + VM 数字与 extract_numbers/fragments 同源一致。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import api_v1  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
import viewmodels  # noqa: E402

CONTRACTS = ROOT / "tests" / "contracts"
GOLDEN = ROOT / "golden" / "baseline_numbers.json"
FAKE = ROOT / "_golden_data"


def _build_summary():
    import core
    import db
    import ingest

    cfg = loaders.load_config(ROOT)
    cfg = dict(cfg)
    cfg["data_dir"] = "_golden_data"
    cfg["zhiyun_auto_fetch"] = False
    cfg["period_pin"] = {"year": 2026, "month": 7}
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, ROOT)
    try:
        ingest.build_std_db(
            cfg, today.year, conn=conn, today=today, trigger="test_vm", archive_backups=False
        )
        summary = core.summary_from_conn(cfg, conn, today)
        for fn in (
            core.attach_unassigned,
            core.attach_allocation_to_summary,
            core.attach_bu_orders,
        ):
            try:
                fn(cfg, conn, today, summary, ROOT) if fn is core.attach_unassigned else fn(
                    cfg, conn, today, summary
                )
            except TypeError:
                try:
                    fn(cfg, conn, today, summary)
                except Exception:
                    pass
            except Exception:
                pass
    finally:
        conn.close()
    return summary, cfg


class TestSchemaSnapshots(unittest.TestCase):
    def test_each_vm_schema_matches_snapshot(self):
        models = {
            "KpiCardsVM": viewmodels.KpiCardsVM,
            "TrendVM": viewmodels.TrendVM,
            "PLTableVM": viewmodels.PLTableVM,
            "ExpenseVM": viewmodels.ExpenseVM,
            "RankingsVM": viewmodels.RankingsVM,
            "ReceiptsVM": viewmodels.ReceiptsVM,
            "LedgerVM": viewmodels.LedgerVM,
            "CockpitVM": viewmodels.CockpitVM,
            "BUPageVM": viewmodels.BUPageVM,
        }
        for name, cls in models.items():
            snap = CONTRACTS / f"{name}.schema.json"
            self.assertTrue(snap.exists(), f"缺少快照 {snap}")
            current = cls.model_json_schema()
            expected = json.loads(snap.read_text(encoding="utf-8"))
            self.assertEqual(
                current,
                expected,
                f"{name} schema 变更须显式更新 tests/contracts/{name}.schema.json",
            )


class TestVmNumbersParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GOLDEN.exists() or not FAKE.exists():
            raise unittest.SkipTest("缺 golden 或 _golden_data")
        cls.golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        cls.summary, cls.cfg = _build_summary()

    def test_vm_numbers_match_extract(self):
        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        exp = api_v1.extract_numbers(self.summary)
        self.assertEqual(vm.numbers["meta_year_key"], exp["meta_year_key"])
        self.assertEqual(vm.numbers["period_keys"], exp["period_keys"])
        for pk in list(exp["periods"])[:3]:
            self.assertEqual(
                vm.numbers["periods"][pk].get("pretax_profit"),
                exp["periods"][pk].get("pretax_profit"),
            )
            self.assertEqual(
                vm.numbers["periods"][pk].get("revenue_net"),
                exp["periods"][pk].get("revenue_net"),
            )

    def test_vm_display_strings_from_views(self):
        """vue：HTML 字段空；legacy：与 build_cockpit_views 同源（任务书51·B1）。

        support.py 默认 setdefault KANBAN_FRONTEND=legacy，本用例显式切 vue/legacy。
        """
        import os

        views = api_v1.build_cockpit_views(self.summary, self.cfg)
        old = os.environ.get("KANBAN_FRONTEND")
        try:
            os.environ["KANBAN_FRONTEND"] = "vue"
            vm_vue = viewmodels.build_cockpit_vm(self.summary, self.cfg)
            self.assertEqual(viewmodels.frontend_mode(self.cfg), "vue")
            self.assertEqual(vm_vue.trend.svg_html, "")
            self.assertEqual(vm_vue.kpi.body_by_period, {})
            self.assertEqual(vm_vue.expense.trend_html, "")
            self.assertTrue(vm_vue.kpi.cards_by_period)

            os.environ["KANBAN_FRONTEND"] = "legacy"
            legacy_cfg = dict(self.cfg)
            legacy_cfg["frontend"] = "legacy"
            vm = viewmodels.build_cockpit_vm(self.summary, legacy_cfg)
            self.assertEqual(vm.trend.svg_html, views.get("trend_html") or "")
            self.assertEqual(vm.kpi.body_by_period, views.get("kpi_body") or {})
            self.assertEqual(vm.expense.trend_html, views.get("expense_trend_html") or "")
            if vm.expense.trend_html:
                self.assertIn("<path", vm.expense.trend_html)
        finally:
            if old is None:
                os.environ.pop("KANBAN_FRONTEND", None)
            else:
                os.environ["KANBAN_FRONTEND"] = old

    def test_vm_numbers_align_golden_sample(self):
        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        yk = self.golden["meta_year_key"]
        self.assertEqual(vm.numbers["meta_year_key"], yk)
        g_p = self.golden["periods"][yk]
        v_p = vm.numbers["periods"][yk]
        self.assertEqual(v_p.get("pretax_profit"), g_p.get("pretax_profit"))


class TestVmHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cls.summary, _ = _build_summary()

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
                {"账号": "all", "密码": "8888", "权限": "整体", "显示名": "整"},
            ],
        )
        server._state["summary"] = self.summary
        # 取一个真实 BU 名若有
        bus = list((self.summary.get("meta") or {}).get("bu_orders") or {}) or []
        server._state["bu_pages"] = {}
        self.app = server.create_app(self.cfg, root=self.tmp)
        from fastapi.testclient import TestClient

        self.TC = TestClient

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_vm_cockpit_requires_login(self):
        c = self.TC(self.app)
        self.assertEqual(c.get("/api/v1/vm/cockpit").status_code, 401)

    def test_vm_cockpit_ok(self):
        c = self.TC(self.app)
        c.post("/login", data={"account": "all", "password": "8888"}, follow_redirects=False)
        r = c.get("/api/v1/vm/cockpit")
        self.assertEqual(r.status_code, 200, r.text[:500])
        j = r.json()
        self.assertEqual(j["scope"], "整体")
        self.assertIn("kpi", j)
        self.assertIn("numbers", j)
        self.assertEqual(
            j["numbers"]["meta_year_key"],
            api_v1.extract_numbers(self.summary)["meta_year_key"],
        )

    def test_openapi_admin_only(self):
        c = self.TC(self.app)
        self.assertEqual(c.get("/openapi.json").status_code, 401)
        r = c.post("/admin/login", data={"account": "admin1", "password": "8888"}, follow_redirects=False)
        self.assertIn(r.status_code, (302, 303))
        r = c.get("/openapi.json")
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertIn("openapi", r.json())


if __name__ == "__main__":
    unittest.main()
