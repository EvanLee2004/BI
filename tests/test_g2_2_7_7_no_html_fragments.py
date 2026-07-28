#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G2 · 2.7.7：刷新停建 HTML 驾驶舱碎片；fragments API 404；FE 零调用。

真路径：do_recompute / do_full 不调 build_dashboard_fragments；
GET /api/v1/cockpit/fragments* → 404；VM 路径仍有业务数据。
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402

FAKE = ROOT / "_golden_data"


def _cfg_tmp(tmp: Path) -> dict:
    cfg = dict(loaders.load_config(ROOT))
    cfg["data_dir"] = "_golden_data" if FAKE.exists() else "数据"
    cfg["zhiyun_auto_fetch"] = False
    cfg["period_pin"] = {"year": 2026, "month": 7}
    cfg["serve_spa"] = False
    return cfg


class TestG2RefreshNoBuildFragments(unittest.TestCase):
    """do_recompute 不得调用 build_dashboard_fragments。"""

    def setUp(self):
        if not FAKE.exists():
            self.skipTest("缺 _golden_data")
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = _cfg_tmp(self.tmp)
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {
                    "账号": accounts.MASTER_ACCOUNT,
                    "显示名": "管理员",
                    "权限": accounts.PERM_ADMIN,
                    "密码": accounts.DEFAULT_ADMIN_PW,
                },
                {
                    "账号": "overall",
                    "显示名": "整体",
                    "权限": "整体",
                    "密码": accounts.DEFAULT_VIEW_PW,
                },
            ],
        )

    def test_do_recompute_does_not_call_build_dashboard_fragments(self):
        import refresh_pipeline
        import render

        # 先 full 一次建立 records/summary（允许 full 内部路径；本测锁 recompute）
        with mock.patch.object(
            render, "build_dashboard_fragments", wraps=render.build_dashboard_fragments
        ) as spy_full:
            # 冷启动 full 可能仍经 generate；G2 后 generate 也不建，spy 应为 0
            refresh_pipeline.do_full(self.cfg, ROOT, "g2_test")
            full_calls = spy_full.call_count

        # 确保有 records
        self.assertTrue(server._state.get("summary") or server._state.get("records") is not None)

        with mock.patch.object(render, "build_dashboard_fragments") as spy:
            t0 = time.perf_counter()
            refresh_pipeline.do_recompute(self.cfg, ROOT, rebuild_std=False)
            elapsed = time.perf_counter() - t0
            self.assertEqual(
                spy.call_count,
                0,
                f"do_recompute 仍调用 build_dashboard_fragments {spy.call_count} 次",
            )
        # 刷新耗时写证据路径（stdout 捕获）
        print(f"G2_REFRESH_ELAPSED_SEC={elapsed:.4f} full_build_calls_after_g2={full_calls}")

        # VM 仍有数据
        summary = server._state.get("summary")
        self.assertIsNotNone(summary)
        import viewmodels

        vm = viewmodels.build_cockpit_vm(summary, self.cfg)
        yk = vm.year_key or (summary.get("meta") or {}).get("year_key")
        cards = (vm.kpi.cards_by_period or {}).get(yk) or []
        self.assertGreaterEqual(len(cards), 1, "刷新后 VM KPI 应有卡")

    def test_do_full_generate_does_not_build_fragments_for_publish(self):
        """do_full/generate 刷新路径不 publish HTML fragments 包。"""
        import refresh_pipeline
        import render

        with mock.patch.object(render, "build_dashboard_fragments") as spy:
            refresh_pipeline.do_full(self.cfg, ROOT, "g2_full")
            self.assertEqual(
                spy.call_count,
                0,
                f"do_full 仍调用 build_dashboard_fragments {spy.call_count} 次",
            )
        fr = server._state.get("fragments")
        # 允许 None 或空 dict；不得有预拼 KPI HTML 正文
        if fr:
            self.assertFalse(
                (fr.get("kpi_views") or "").strip(),
                "state.fragments 不应再持有预拼 kpi_views",
            )


class TestG2FragmentsApi404(unittest.TestCase):
    """fragments 死 API → 404；VM 仍 200。"""

    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        import core
        import db
        import ingest

        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "数据").mkdir()
        cfg = _cfg_tmp(cls.tmp)
        accounts.save_accounts(
            cfg,
            cls.tmp,
            [
                {
                    "账号": "overall",
                    "显示名": "整体",
                    "权限": "整体",
                    "密码": accounts.DEFAULT_VIEW_PW,
                },
                {
                    "账号": "admin1",
                    "显示名": "管",
                    "权限": "管理员",
                    "密码": accounts.DEFAULT_ADMIN_PW,
                },
            ],
        )
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            ingest.build_std_db(
                cfg, today.year, conn=conn, today=today, trigger="g2_http", archive_backups=False
            )
            summary = core.summary_from_conn(cfg, conn, today)
            bu_pages = core.build_bu_pages(cfg, conn, today, "", ROOT)
        finally:
            conn.close()
        server._state["summary"] = summary
        server._state["has_data"] = True
        server._state["built_at"] = "g2-test"
        server._state["fragments"] = {"kpi_views": "SHOULD_NOT_SERVE"}
        server._state["views"] = {"year_key": (summary.get("meta") or {}).get("year_key") or ""}
        server._state["bu_pages"] = bu_pages or {}
        server._state["admin_html"] = "ready"
        cls.cfg = cfg
        cls.app = server.create_app(cfg, root=cls.tmp)
        from fastapi.testclient import TestClient

        cls.Client = TestClient

    def _login(self, account="overall", password=None):
        pw = password or accounts.DEFAULT_VIEW_PW
        c = self.Client(self.app, follow_redirects=False)
        r = c.post("/login", data={"account": account, "password": pw})
        # form login may 303
        self.assertIn(r.status_code, (200, 303, 302), r.text[:200])
        return c

    def test_main_fragments_404(self):
        c = self._login()
        r = c.get("/api/v1/cockpit/fragments")
        self.assertEqual(r.status_code, 404, r.text[:300])

    def test_bu_fragments_404(self):
        c = self._login()
        pages = server._state.get("bu_pages") or {}
        if not pages:
            self.skipTest("无 BU 页")
        name = next(iter(pages))
        from urllib.parse import quote

        r = c.get(f"/api/v1/cockpit/bu/{quote(name)}/fragments")
        self.assertEqual(r.status_code, 404, r.text[:300])

    def test_vm_cockpit_still_200_with_kpi(self):
        c = self._login()
        r = c.get("/api/v1/vm/cockpit")
        self.assertEqual(r.status_code, 200, r.text[:400])
        body = r.json()
        self.assertNotEqual(body.get("empty"), True)
        cards = (body.get("kpi") or {}).get("cards_by_period") or {}
        self.assertTrue(cards, "VM 应有 KPI cards_by_period")


class TestG2FrontendZeroFragmentsCall(unittest.TestCase):
    def test_frontend_src_no_fragments_api(self):
        fe = ROOT / "frontend" / "src"
        bad = []
        for p in fe.rglob("*"):
            if p.suffix not in {".ts", ".vue", ".js"}:
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            if "cockpit/fragments" in t or "/fragments" in t and "cockpit" in t:
                bad.append(str(p.relative_to(ROOT)))
        self.assertEqual(bad, [], "前端仍引用 fragments API:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
