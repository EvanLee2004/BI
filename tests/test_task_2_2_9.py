#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.9 门禁：方案 A 静态可交互快照导出 + 顶栏今日日期 + OFFLINE 无残壳。"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts
import bu
import loaders
import server
from support import fake_bu_page, fake_main_frags, fake_views  # noqa: E402


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


def _write_accts(cfg, root, rows):
    accounts.save_accounts(cfg, root, rows)


def _std_accts():
    return [
        {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
        {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
        {"账号": "user_a", "显示名": "甲负责人", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
        {"账号": "user_b", "显示名": "乙负责人", "权限": "BU乙", "密码": server.DEFAULT_VIEW_PW},
    ]


class TestSourceGuards229(unittest.TestCase):
    def test_topbar_today_date(self):
        app = (ROOT / "frontend/src/App.vue").read_text(encoding="utf-8")
        bu = (ROOT / "frontend/src/components/BUPage.vue").read_text(encoding="utf-8")
        for src, label in ((app, "App"), (bu, "BUPage")):
            self.assertIn("tb-today", src, label)
            self.assertIn("localTodayYmd", src, label)
            self.assertIn("本机今日日期", src, label)

    def test_snapshot_mode_in_store(self):
        store = (ROOT / "frontend/src/stores/cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("snapshotMode", store)
        self.assertIn("loadSnapshot", store)
        self.assertIn("__KANBAN_SNAPSHOT__", store)
        self.assertIn("kanban_snapshot", store)

    def test_topbar_hides_export_in_snapshot(self):
        src = (ROOT / "frontend/src/components/TopBarActions.vue").read_text(encoding="utf-8")
        self.assertIn("snapshotMode", src)
        self.assertIn("export.html", src)
        self.assertIn("/api/export.html", src)

    def test_bu_only_snapshot_hides_overall_back(self):
        """BU 专用包 / 无 can_main 不得提供「← 整体」入口，避免 loadMain 挂上空壳或 403。"""
        bu = (ROOT / "frontend/src/components/BUPage.vue").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/stores/cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("showOverallBack", bu)
        self.assertIn('v-if="showOverallBack"', bu)
        self.assertIn("snapshotCanGoOverall", bu)
        self.assertIn("function snapshotCanGoOverall", store)
        # 2.3.4：在线必须读 session.can_main（纯 BU 账号不显示按钮）
        self.assertIn("can_main", bu)
        self.assertIn("fetchSession", bu)
        self.assertIn("canMain", bu)
        # loadMain 对 BU 包 / 空 cockpit 必须 early return（禁止挂空整体）
        self.assertIn("snapshotCanGoOverall()", store)
        self.assertRegex(
            store,
            r"if\s*\(\s*!snapshotCanGoOverall\(\)\s*\)\s*\{?\s*return",
            msg="loadMain must no-op when snapshot cannot go overall",
        )
        # scope===BU 时 snapshotCanGoOverall 为 false
        self.assertTrue(
            "=== 'BU'" in store or '=== "BU"' in store,
            "snapshotCanGoOverall must treat pack.scope === 'BU' as no overall",
        )

    def test_export_main_path_is_snapshot_not_fallback(self):
        exp = (ROOT / "src/export_html.py").read_text(encoding="utf-8")
        self.assertIn("assemble_export_pack", exp)
        self.assertIn("build_snapshot_export_html", exp)
        self.assertIn("kanban_snapshot", exp)
        self.assertIn('return html, "snapshot"', exp)
        # 退役函数存在但 raise（禁止残壳/冻页假成功）
        self.assertIn("已退役", exp)
        self.assertIn("fallback_export_html", exp)
        routes = (ROOT / "src/routes/export.py").read_text(encoding="utf-8")
        self.assertIn("assemble_export_pack", routes)
        self.assertNotIn("prefer_playwright=True", routes)


class TestAssemblePack(unittest.TestCase):
    def test_overall_pack_has_all_bus(self):
        from export_html import assemble_export_pack

        pack = assemble_export_pack(
            scope="整体",
            blk="2026年",
            version="2.2.9",
            cockpit_vm={
                "year_key": "2026年",
                "period_keys": ["2026年", "2026年3月"],
                "kpi": {"cards_by_period": {"2026年": [{"title": "收入", "value_disp": "1"}]}},
            },
            bu_vms={
                "BU甲": {"bu_name": "BU甲", "year_key": "2026年", "period_keys": ["2026年"], "kpi": {}},
                "BU乙": {"bu_name": "BU乙", "year_key": "2026年", "period_keys": ["2026年"], "kpi": {}},
            },
        )
        self.assertEqual(pack["kind"], "kanban_snapshot")
        self.assertEqual(pack["schema"], 1)
        self.assertEqual(pack["scope"], "整体")
        self.assertEqual(pack["version"], "2.2.9")
        self.assertEqual(pack["default_period"], "2026年")
        self.assertTrue(pack["cockpit"])
        self.assertEqual(set(pack["bu"].keys()), {"BU甲", "BU乙"})
        self.assertIn("period_keys", pack["cockpit"])

    def test_bu_pack_isolation(self):
        from export_html import assemble_export_pack

        pack = assemble_export_pack(
            scope="BU",
            bu_name="BU甲",
            blk="2026年",
            version="2.2.9",
            bu_vms={
                "BU甲": {"bu_name": "BU甲", "year_key": "2026年", "period_keys": ["2026年"], "marker": "ONLY_A"},
                "BU乙": {"bu_name": "BU乙", "year_key": "2026年", "period_keys": ["2026年"], "marker": "ONLY_B"},
            },
        )
        self.assertEqual(pack["scope"], "BU")
        self.assertEqual(pack["bu_export_name"], "BU甲")
        self.assertEqual(pack["cockpit"], {})
        self.assertEqual(list(pack["bu"].keys()), ["BU甲"])
        raw = json.dumps(pack, ensure_ascii=False)
        self.assertNotIn("BU乙", raw)
        self.assertNotIn("ONLY_B", raw)
        self.assertIn("ONLY_A", raw)

    def test_bu_pack_empty_cockpit_means_no_overall_shell(self):
        """契约：BU 导出 pack.scope=BU 且 cockpit={}，前端靠此禁「← 整体」/ loadMain。"""
        from export_html import assemble_export_pack, build_export_html

        pack = assemble_export_pack(
            scope="BU",
            bu_name="游戏",
            blk="2026年",
            version="2.2.9",
            bu_vms={
                "游戏": {
                    "bu_name": "游戏",
                    "year_key": "2026年",
                    "period_keys": ["2026年"],
                    "kpi": {"cards_by_period": {"2026年": [{"title": "收入", "value_disp": "1"}]}},
                }
            },
        )
        self.assertEqual(pack["scope"], "BU")
        self.assertEqual(pack.get("cockpit") or {}, {})
        self.assertFalse(bool(pack["cockpit"]))
        # 与前端 snapshotCanGoOverall 同源条件：scope=BU → 不可回整体
        can_overall = str(pack.get("scope") or "") != "BU" and bool(
            (pack.get("cockpit") or {}).get("period_keys")
            or (pack.get("cockpit") or {}).get("year_key")
        )
        self.assertFalse(can_overall)
        html, mode = build_export_html(pack=pack, version="2.2.9", root=ROOT)
        self.assertEqual(mode, "snapshot")
        m = re.search(r"window\.__KANBAN_SNAPSHOT__ = (\{.*\});\s*</script>", html)
        self.assertIsNotNone(m)
        emb = json.loads(m.group(1))
        self.assertEqual(emb["scope"], "BU")
        self.assertEqual(emb.get("cockpit") or {}, {})
        self.assertEqual(list(emb["bu"].keys()), ["游戏"])


class TestSnapshotHtmlBody(unittest.TestCase):
    def test_build_contains_snapshot_not_fallback(self):
        from export_html import assemble_export_pack, build_export_html

        pack = assemble_export_pack(
            scope="整体",
            blk="2026年",
            version="2.2.9",
            cockpit_vm={"year_key": "2026年", "period_keys": ["2026年"], "kpi": {}},
            bu_vms={"语言": {"bu_name": "语言", "year_key": "2026年", "period_keys": ["2026年"], "kpi": {}}},
        )
        html, mode = build_export_html(pack=pack, version="2.2.9", root=ROOT)
        self.assertEqual(mode, "snapshot")
        self.assertIn("__KANBAN_SNAPSHOT__", html)
        self.assertIn("kanban_snapshot", html)
        self.assertIn('data-export-scheme="A"', html)
        self.assertIn('data-kanban-export="snapshot"', html)
        self.assertNotIn('data-export-fallback="1"', html)
        self.assertIn("语言", html)
        # 播放器已内联
        self.assertIn('type="module"', html)
        self.assertGreater(len(html), 100_000)


class TestExportHttp229(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(
            self.cfg,
            self.tmp,
            [
                {"name": "BU甲", "销售": ["销售A"]},
                {"name": "BU乙", "销售": ["销售B"]},
            ],
        )
        _write_accts(self.cfg, self.tmp, _std_accts())
        server._state["user_html"] = "ready"
        server._state["fragments"] = fake_main_frags("USER-MAIN")
        server._state["views"] = fake_views("USER-MAIN")
        server._state["summary"] = {
            "periods": {"2026年": {}, "2026年3月": {}},
            "meta": {"year_key": "2026年"},
            "trend": [],
            "receipt_order_monthly": [],
        }
        server._state["has_data"] = True
        server._state["bu_pages"] = {
            "BU甲": fake_bu_page("BU甲", "PAGE-A"),
            "BU乙": fake_bu_page("BU乙", "PAGE-B"),
        }
        for _name, page in server._state["bu_pages"].items():
            if isinstance(page, dict) and not page.get("summary"):
                page["summary"] = {
                    "periods": {"2026年": {}},
                    "meta": {"year_key": "2026年"},
                    "trend": [],
                    "receipt_order_monthly": [],
                }
        server._state["admin_html"] = "ready"
        self.app = server.create_app(self.cfg, root=self.tmp)
        self._prev_offline = os.environ.get("KANBAN_OFFLINE")
        os.environ["KANBAN_OFFLINE"] = "1"

    def tearDown(self):
        if self._prev_offline is None:
            os.environ.pop("KANBAN_OFFLINE", None)
        else:
            os.environ["KANBAN_OFFLINE"] = self._prev_offline

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _login_view(self, account, pw=None):
        c = self._client()
        c.post("/login", data={"account": account, "password": pw or server.DEFAULT_VIEW_PW})
        return c

    def _admin(self):
        c = self._client()
        r = c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        self.assertEqual(r.status_code, 303, r.text[:300])
        return c

    def test_export_auth_matrix(self):
        raw = self._client()
        self.assertEqual(raw.get("/export.html").status_code, 401)
        self.assertEqual(raw.get("/api/export.html").status_code, 401)
        self.assertEqual(raw.get(f"/bu/{quote('BU甲')}/export.html").status_code, 401)
        self.assertEqual(raw.get(f"/bu/{quote('不存在')}/export.html").status_code, 404)

        admin = self._admin()
        for path in ("/export.html", "/api/export.html"):
            r = admin.get(path)
            self.assertEqual(r.status_code, 200, f"{path}: {r.text[:400]}")
            self.assertIn("text/html", r.headers.get("content-type", ""))
            body = r.text
            self.assertIn("kanban_snapshot", body)
            self.assertIn("__KANBAN_SNAPSHOT__", body)
            self.assertNotIn('data-export-fallback="1"', body)
            disp = (r.headers.get("x-filename") or "") + (r.headers.get("content-disposition") or "")
            self.assertIn(".html", disp.lower(), path)

        self.assertEqual(admin.get(f"/bu/{quote('BU甲')}/export.html").status_code, 200)
        self.assertEqual(admin.get(f"/bu/{quote('不存在')}/export.html").status_code, 404)
        self.assertEqual(admin.get("/export.html", params={"blk": "1999年"}).status_code, 400)

        cmain = self._login_view("overall")
        self.assertEqual(cmain.get("/export.html").status_code, 200)
        self.assertEqual(cmain.get("/api/export.html").status_code, 200)

    def test_export_bu_isolation_body(self):
        cbu = self._login_view("user_a")
        self.assertEqual(cbu.get("/export.html").status_code, 401)
        r = cbu.get(f"/bu/{quote('BU甲')}/export.html")
        self.assertEqual(r.status_code, 200, r.text[:300])
        body = r.text
        self.assertIn("kanban_snapshot", body)
        self.assertIn("BU甲", body)
        # pack JSON 不得含他 BU 键
        m = re.search(r"window\.__KANBAN_SNAPSHOT__ = (\{.*\});\s*</script>", body)
        self.assertIsNotNone(m, "missing pack script")
        pack = json.loads(m.group(1))
        self.assertEqual(pack["scope"], "BU")
        self.assertEqual(list(pack["bu"].keys()), ["BU甲"])
        self.assertEqual(pack.get("cockpit") or {}, {})
        self.assertNotIn("BU乙", json.dumps(pack, ensure_ascii=False))
        self.assertEqual(cbu.get(f"/bu/{quote('BU乙')}/export.html").status_code, 401)
        self.assertEqual(cbu.get(f"/bu/{quote('不存在')}/export.html").status_code, 404)

    def test_offline_export_not_residual_shell(self):
        """KANBAN_OFFLINE=1 仍须真快照，禁止 fallback 残壳假成功。"""
        self.assertEqual(os.environ.get("KANBAN_OFFLINE"), "1")
        c = self._login_view("overall")
        r = c.get("/api/export.html")
        self.assertEqual(r.status_code, 200, r.text[:500])
        body = r.text
        self.assertIn("kanban_snapshot", body)
        self.assertIn('data-export-scheme="A"', body)
        self.assertNotIn('data-export-fallback="1"', body)
        self.assertNotIn("Vue 结构降级壳", body)

    def test_overall_pack_in_http_body(self):
        c = self._login_view("overall")
        r = c.get("/api/export.html", params={"blk": "2026年"})
        self.assertEqual(r.status_code, 200)
        m = re.search(r"window\.__KANBAN_SNAPSHOT__ = (\{.*\});\s*</script>", r.text)
        self.assertIsNotNone(m)
        pack = json.loads(m.group(1))
        self.assertEqual(pack["kind"], "kanban_snapshot")
        self.assertEqual(pack["scope"], "整体")
        self.assertEqual(set(pack["bu"].keys()), {"BU甲", "BU乙"})
        self.assertTrue(isinstance(pack.get("cockpit"), dict))


class TestVersion229(unittest.TestCase):
    def test_version_file(self):
        # 2.2.9 历史条目必须保留；当前产品号可继续递增（2.3.0+）
        v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(v, r"^2\.(2|3|4|5|6)\.\d+$")
        self.assertIn("2.2.9", (ROOT / "src/version.py").read_text(encoding="utf-8"))
        self.assertIn("## [2.2.9]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
