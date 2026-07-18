#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.11 R-01：buNames 有分页时 VM 必下发；有配置无分页时给 hint；BuNav 结构守卫。"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import bu  # noqa: E402
import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
from routes.cockpit import _bu_nav_meta  # noqa: E402

TODAY = datetime.date(2026, 7, 11)


def _seed(cfg, root: Path) -> None:
    import money

    conn = db.connect(cfg, root)
    conn.execute(
        "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
        (
            "P1",
            "SO1",
            "客户甲",
            "线1",
            "销售A",
            "2026-03-10",
            money.yuan_to_fen(1060.0),
            money.yuan_to_fen(300.0),
            "2026-03",
            "2026-03-10",
            "2026-03",
        ),
    )
    conn.execute(
        "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
        " VALUES(?,?,?,?,?,?,?,?,0)",
        ("O1", "SO1", "2026-03-01", money.yuan_to_fen(1000.0), "部门X", "销售A", "2026-03", "2026-03"),
    )
    conn.execute(
        "INSERT INTO std_回款(定位键,回款ID,到账日期,到账金额,客户,销售,归属月,原值_归属月,已删除)"
        " VALUES(?,?,?,?,?,?,?,?,0)",
        ("R1", "HK1", "2026-03-15", money.yuan_to_fen(800.0), "客户甲", "销售A", "2026-03", "2026-03"),
    )
    conn.commit()
    conn.close()


def _write_bucfg(cfg, root: Path, bus: list) -> None:
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus, "公共费用分摊启用": False}, ensure_ascii=False), encoding="utf-8")


class TestBuNavMeta(unittest.TestCase):
    def test_hint_when_config_but_no_pages(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = dict(loaders.load_config())
        cfg["data_dir"] = "data"
        (tmp / "data").mkdir(parents=True, exist_ok=True)
        _write_bucfg(cfg, tmp, [{"name": "示意BU甲", "负责人": [], "销售": ["销售A"], "分摊比例": None}])
        meta = _bu_nav_meta(cfg, tmp, {})
        self.assertEqual(meta["bu_config_count"], 1)
        self.assertIn("更新数据", meta["bu_nav_hint"])

    def test_no_hint_when_pages_present(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = dict(loaders.load_config())
        cfg["data_dir"] = "data"
        (tmp / "data").mkdir(parents=True, exist_ok=True)
        _write_bucfg(cfg, tmp, [{"name": "示意BU甲", "负责人": [], "销售": ["销售A"], "分摊比例": None}])
        meta = _bu_nav_meta(cfg, tmp, {"示意BU甲": {"name": "示意BU甲"}})
        self.assertEqual(meta["bu_config_count"], 1)
        self.assertEqual(meta["bu_nav_hint"], "")

    def test_zero_config_count(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = dict(loaders.load_config())
        cfg["data_dir"] = "data"
        (tmp / "data").mkdir(parents=True, exist_ok=True)
        meta = _bu_nav_meta(cfg, tmp, {})
        self.assertEqual(meta["bu_config_count"], 0)
        self.assertEqual(meta["bu_nav_hint"], "")


class TestBuNamesOnVmWhenPagesExist(unittest.TestCase):
    """buNames 分页已生成时，VM 必带 bu_names（导航渲染的数据前提）。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp
        cls.cfg = dict(loaders.load_config())
        cls.cfg["data_dir"] = "data"
        cls.cfg["zhiyun_auto_fetch"] = False
        (cls.root / "data").mkdir(parents=True, exist_ok=True)
        _seed(cls.cfg, cls.root)
        _write_bucfg(
            cls.cfg,
            cls.root,
            [{"name": "示意BU甲", "负责人": ["甲"], "销售": ["销售A"], "分摊比例": None}],
        )
        accounts.save_accounts(
            cls.cfg,
            cls.root,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管理员",
                    "权限": "管理员",
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
        conn = db.connect(cls.cfg, cls.root)
        summary = core.summary_from_conn(cls.cfg, conn, TODAY)
        pages = core.build_bu_pages(cls.cfg, conn, TODAY, "", cls.root)
        conn.close()
        self_assert = len(pages) >= 1
        if not self_assert:
            raise RuntimeError(f"build_bu_pages empty: {pages!r}")
        server._state["summary"] = summary
        server._state["bu_pages"] = pages
        server._state["built_at"] = "test-54p11"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.pages = pages

    def test_vm_cockpit_bu_names_when_configured(self):
        r = self.client.post(
            "/api/v1/login",
            json={"account": "overall", "password": accounts.DEFAULT_VIEW_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        vm = self.client.get("/api/v1/vm/cockpit")
        self.assertEqual(vm.status_code, 200, vm.text[:800])
        body = vm.json()
        names = body.get("bu_names") or []
        self.assertTrue(len(names) >= 1, f"expected bu_names non-empty, got {names!r}")
        self.assertIn("示意BU甲", names)
        self.assertFalse(body.get("bu_nav_hint") or "")
        self.assertGreaterEqual(int(body.get("bu_config_count") or 0), 1)

    def test_bunav_source_renders_when_names(self):
        """结构守卫：BuNav 在 list 非空时必有 data-testid=bu-nav。"""
        src = (ROOT / "frontend" / "src" / "components" / "BuNav.vue").read_text(encoding="utf-8")
        self.assertIn('data-testid="bu-nav"', src)
        self.assertIn('v-if="list.length"', src)
        self.assertIn("bu-nav-empty-hint", src)
        self.assertIn("bu_nav_hint", (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
