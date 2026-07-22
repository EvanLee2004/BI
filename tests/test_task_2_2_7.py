#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.7 门禁：VM 归档 + 历史 API + 导出 HTML 鉴权 + 源码守卫 + 停写页面_*.html。"""
from __future__ import annotations

import datetime
import json
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


class TestSourceGuards227(unittest.TestCase):
    def test_topbar_export_html(self):
        src = (ROOT / "frontend/src/components/TopBarActions.vue").read_text(encoding="utf-8")
        self.assertIn("/export.html", src)
        self.assertIn("exportHtml", src)
        self.assertNotIn("/export.png", src)
        self.assertIn("export-html-btn", src)

    def test_admin_layout_no_light_toggle(self):
        layout = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(encoding="utf-8")
        # 顶栏按钮文案/绑定已去；注释可提「浅色」历史
        self.assertNotIn("◑ 浅色", layout)
        self.assertNotIn("◐ 深色", layout)
        self.assertNotIn("@click=\"toggleTheme\"", layout)
        self.assertNotIn("function toggleTheme", layout)
        login = (ROOT / "frontend/src/admin/views/LoginView.vue").read_text(encoding="utf-8")
        self.assertNotIn("◑ 浅色", login)
        app = (ROOT / "frontend/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("ThemeToggle", app)
        self.assertIn("archive-banner", app)

    def test_history_opens_vue_archive(self):
        hv = (ROOT / "frontend/src/admin/views/HistoryView.vue").read_text(encoding="utf-8")
        self.assertIn("/?archive=", hv)
        self.assertNotIn("frameSrc.value = '/api/history/'", hv)

    def test_snapshot_page_disabled_in_source(self):
        arch = (ROOT / "src/ingest/archive.py").read_text(encoding="utf-8")
        self.assertIn("def snapshot_vm", arch)
        core = (ROOT / "src/core.py").read_text(encoding="utf-8")
        self.assertIn("snapshot_vm", core)
        self.assertNotIn("snapshot_page(cfg, html", core)

    def test_nginx_proxies_export_html(self):
        """生产 :80 必须反代 export.html，否则 try_files 落 SPA 匿名 200。"""
        conf = (ROOT / "deploy/linux/nginx-kanban.conf").read_text(encoding="utf-8")
        self.assertIn("export\\.(png|html)", conf)
        self.assertNotRegex(
            conf,
            r"location ~ \^\(/\(api\|admin\|login\|bu\|export\\\.png\)\(/\|\$\)",
            msg="不得只反代 export.png 而漏 export.html",
        )


class TestSnapshotVm(unittest.TestCase):
    def test_snapshot_vm_writes_json(self):
        from ingest import archive

        tmp = Path(tempfile.mkdtemp())
        cfg = {"data_dir": "数据", "backup_keep_days": 30}
        (tmp / "数据").mkdir(parents=True)
        day = datetime.date(2026, 7, 22)
        res = archive.snapshot_vm(
            cfg,
            cockpit_vm={
                "year_key": "2026年",
                "period_keys": ["2026年"],
                "kpi": {"cards_by_period": {"2026年": []}},
            },
            bu_vms={"语言": {"bu_name": "语言"}},
            today=day,
            root=tmp,
            built_at="2026-07-22 12:00:00",
            version="2.2.7",
        )
        self.assertEqual(res["status"], "ok", res)
        p = tmp / "数据" / "备份" / "vm_20260722.json"
        self.assertTrue(p.is_file(), p)
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["day"], "20260722")
        self.assertEqual(data["version"], "2.2.7")
        self.assertIn("period_keys", data["cockpit"])
        self.assertIn("kpi", data["cockpit"])
        self.assertIn("语言", data["bu"])

    def test_snapshot_page_no_longer_writes_html(self):
        from ingest import archive

        tmp = Path(tempfile.mkdtemp())
        cfg = {"data_dir": "数据", "backup_keep_days": 2}
        res = archive.snapshot_page(cfg, "<html>x</html>", datetime.date(2026, 7, 22), tmp)
        self.assertEqual(res["status"], "disabled")
        bdir = tmp / "数据" / "备份"
        if bdir.exists():
            self.assertEqual(list(bdir.glob("页面_*.html")), [])


class TestHistoryAndExportHttp(unittest.TestCase):
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
        server._state["user_html"] = '<html><div class="wrap">USER-MAIN</div></html>'
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
        # fake_bu_page 可能无 summary；补上供 export 用
        for name, page in server._state["bu_pages"].items():
            if isinstance(page, dict) and not page.get("summary"):
                page["summary"] = {
                    "periods": {"2026年": {}},
                    "meta": {"year_key": "2026年"},
                    "trend": [],
                    "receipt_order_monthly": [],
                }
        server._state["admin_html"] = "ready"
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _admin(self):
        c = self._client()
        r = c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        self.assertEqual(r.status_code, 303, r.text[:300])
        return c

    def _login_view(self, account, pw=None):
        c = self._client()
        r = c.post("/login", data={"account": account, "password": pw or server.DEFAULT_VIEW_PW})
        return c, r

    def test_history_vm_404_and_200(self):
        from ingest import archive

        c = self._client()
        self.assertEqual(c.get("/api/history").status_code, 401)
        self.assertEqual(c.get("/api/history/20260722/vm").status_code, 401)

        admin = self._admin()
        self.assertEqual(admin.get("/api/history/19990101/vm").status_code, 404)
        archive.snapshot_vm(
            self.cfg,
            cockpit_vm={"year_key": "2026年", "period_keys": ["2026年"], "kpi": {}},
            today=datetime.date(2026, 7, 15),
            root=self.tmp,
            version="2.2.7",
        )
        r = admin.get("/api/history/20260715/vm")
        self.assertEqual(r.status_code, 200, r.text[:200])
        body = r.json()
        self.assertIn("cockpit", body)
        self.assertEqual(body["day"], "20260715")
        lst = admin.get("/api/history").json()
        days = [x["day"] for x in lst]
        self.assertIn("20260715", days)
        self.assertEqual(admin.get("/api/history/20260715").status_code, 410)
        self.assertEqual(admin.get("/api/history/2026-7-9/vm").status_code, 400)

    def test_export_html_auth_matrix(self):
        with mock.patch(
            "export_html.build_export_html",
            return_value=("<html data-export-vue=1>ok</html>", "fallback"),
        ):
            raw = self._client()
            self.assertEqual(raw.get("/export.html").status_code, 401)
            self.assertEqual(raw.get(f"/bu/{quote('BU甲')}/export.html").status_code, 401)
            self.assertEqual(raw.get(f"/bu/{quote('不存在')}/export.html").status_code, 404)

            admin = self._admin()
            r = admin.get("/export.html")
            self.assertEqual(r.status_code, 200, r.text[:300])
            self.assertIn("text/html", r.headers.get("content-type", ""))
            disp = (r.headers.get("x-filename") or "") + (r.headers.get("content-disposition") or "")
            self.assertIn(".html", disp.lower())
            self.assertEqual(admin.get(f"/bu/{quote('BU甲')}/export.html").status_code, 200)
            self.assertEqual(admin.get(f"/bu/{quote('不存在')}/export.html").status_code, 404)
            self.assertEqual(admin.get("/export.html", params={"blk": "1999年"}).status_code, 400)

            cmain, _ = self._login_view("overall")
            self.assertEqual(cmain.get("/export.html").status_code, 200)

            # PNG 兼容不 500
            orig = server._screenshot_png
            server._screenshot_png = lambda html, blk="", width=1440: b"\x89PNGFAKE"
            try:
                r = admin.get("/export.png")
                self.assertNotEqual(r.status_code, 500)
            finally:
                server._screenshot_png = orig

    def test_export_html_bu_isolation(self):
        with mock.patch(
            "export_html.build_export_html",
            return_value=("<html>bu</html>", "fallback"),
        ):
            cbu, _ = self._login_view("user_a")
            self.assertEqual(cbu.get("/export.html").status_code, 401)
            self.assertEqual(cbu.get(f"/bu/{quote('BU甲')}/export.html").status_code, 200)
            self.assertEqual(cbu.get(f"/bu/{quote('BU乙')}/export.html").status_code, 401)
            self.assertEqual(cbu.get(f"/bu/{quote('不存在')}/export.html").status_code, 404)


class TestVersion227(unittest.TestCase):
    def test_version_file(self):
        v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(v, "2.2.7")


if __name__ == "__main__":
    unittest.main()
