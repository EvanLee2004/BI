# -*- coding: utf-8 -*-
"""2.7.2：写路径/运维路径全量 v1；旧路径 404；前端无旧调用。

POST 写库/刷新不触发真管道（只验路由表 + 旧 404）；GET 用 TestClient。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402

OLD_PATHS = [
    "/api/adjust",
    "/api/adjust/batch",
    "/api/adjust/{adj_id}/revoke",
    "/api/adjust/{adj_id}/rearm",
    "/api/adjust/expired/revoke_all",
    "/api/refresh",
    "/api/refresh_status",
    "/api/my_passwd",
    "/api/update/apply",
    "/api/health",
]

V1_PATHS = [
    "/api/v1/admin/adjust",
    "/api/v1/admin/adjust/batch",
    "/api/v1/admin/adjust/{adj_id}/revoke",
    "/api/v1/admin/adjust/{adj_id}/rearm",
    "/api/v1/admin/adjust/expired/revoke_all",
    "/api/v1/admin/refresh",
    "/api/v1/admin/refresh_status",
    "/api/v1/my_passwd",
    "/api/v1/admin/update/apply",
    "/api/v1/health",
]


def _route_paths(app) -> set[str]:
    out: set[str] = set()
    for r in app.routes:
        p = getattr(r, "path", None)
        if p:
            out.add(p)
    return out


class TestWritePathsV1Only(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import loaders
        import server
        from support import fake_bu_page, fake_main_frags, fake_views

        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "数据").mkdir()
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            cls.cfg,
            cls.tmp,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管理员",
                    "权限": "管理员",
                    "密码": server.DEFAULT_PW,
                },
                {
                    "账号": "overall",
                    "显示名": "整体",
                    "权限": "整体",
                    "密码": server.DEFAULT_VIEW_PW,
                },
            ],
        )
        server._state["user_html"] = "<html></html>"
        server._state["fragments"] = fake_main_frags("M")
        server._state["views"] = fake_views("M")
        server._state["bu_pages"] = {"BU甲": fake_bu_page("BU甲", "A")}
        server._state["admin_html"] = "x"
        server._state["has_data"] = True
        server._state["summary"] = {"meta": {"year_key": "2026年", "health": {}}, "periods": {}}
        server._state["refreshing"] = None
        server._state["last_refresh"] = None
        server._state["built_at"] = "2026-07-28 00:00:00"
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.server = server
        cls.paths = _route_paths(cls.app)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_route_table_v1_only(self):
        for p in OLD_PATHS:
            self.assertNotIn(p, self.paths, f"old route still registered: {p}")
        for p in V1_PATHS:
            self.assertIn(p, self.paths, f"v1 route missing: {p}")

    def test_old_get_404_health_and_refresh_status(self):
        c = self._client()
        self.assertEqual(c.get("/api/health").status_code, 404)
        self.assertEqual(c.get("/api/v1/health").status_code, 200)
        c.post("/api/v1/login", json={"account": "lushasha", "password": self.server.DEFAULT_PW})
        self.assertEqual(c.get("/api/refresh_status").status_code, 404)
        r = c.get("/api/v1/admin/refresh_status")
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertIn("running", r.json())

    def test_old_post_404_without_side_effects(self):
        """旧 POST 必须 404；不调用 v1 POST 写库/刷新（避免真管道）。"""
        c = self._client()
        c.post("/api/v1/login", json={"account": "lushasha", "password": self.server.DEFAULT_PW})
        for old in (
            "/api/adjust",
            "/api/adjust/batch",
            "/api/adjust/1/revoke",
            "/api/adjust/1/rearm",
            "/api/adjust/expired/revoke_all",
            "/api/refresh",
            "/api/update/apply",
            "/api/my_passwd",
        ):
            r = c.post(old, json={})
            self.assertEqual(r.status_code, 404, f"{old} → {r.status_code}")

    def test_my_passwd_v1_exists(self):
        c = self._client()
        c.post("/api/v1/login", json={"account": "overall", "password": self.server.DEFAULT_VIEW_PW})
        r = c.post("/api/v1/my_passwd", json={"old": "wrong", "new": "x"})
        self.assertIn(r.status_code, (400, 200), r.text[:200])


class TestFrontendNoOldWritePaths(unittest.TestCase):
    FORBIDDEN = [
        "'/api/adjust",
        '"/api/adjust',
        "`/api/adjust",
        "'/api/refresh'",
        '"/api/refresh"',
        "'/api/refresh_status'",
        '"/api/refresh_status"',
        "'/api/my_passwd'",
        '"/api/my_passwd"',
        "'/api/health'",
        '"/api/health"',
        "'/api/update/apply'",
        '"/api/update/apply"',
    ]

    def test_src_and_static(self):
        hits = []
        for base in (ROOT / "frontend/src", ROOT / "static"):
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if p.suffix not in {".ts", ".vue", ".js", ".html"}:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
                for needle in self.FORBIDDEN:
                    if needle in text:
                        hits.append(f"{p.relative_to(ROOT)}: {needle}")
        self.assertEqual(hits, [], "still calls old write paths:\n" + "\n".join(hits))

    def test_healthcheck_script(self):
        sh = (ROOT / "deploy/healthcheck.sh").read_text(encoding="utf-8")
        self.assertIn("/api/v1/health", sh)
        stripped = sh.replace("/api/v1/health", "")
        self.assertNotIn("/api/health", stripped)


class TestExportBarePathsGone(unittest.TestCase):
    """2.7.2 S4：裸 /export.* 与 /bu/*/export.* 装饰器已删；仅 v1。"""

    BARE = (
        "/export.png",
        "/export.html",
        "/export/pl.xlsx",
        "/bu/{name}/export.png",
        "/bu/{name}/export.html",
        "/bu/{name}/export/pl.xlsx",
    )
    V1 = (
        "/api/v1/export.png",
        "/api/v1/export.html",
        "/api/v1/export/pl.xlsx",
        "/api/v1/export/bu/{name}/png",
        "/api/v1/export/bu/{name}/html",
        "/api/v1/export/bu/{name}/pl.xlsx",
    )

    def test_export_py_decorators(self):
        src = (ROOT / "src/routes/export.py").read_text(encoding="utf-8")
        for p in self.BARE:
            self.assertNotIn(f'@app.get("{p}")', src, f"bare still registered: {p}")
        for p in self.V1:
            self.assertIn(f'@app.get("{p}")', src, f"v1 missing: {p}")

    def test_frontend_export_urls(self):
        top = (ROOT / "frontend/src/components/TopBarActions.vue").read_text(encoding="utf-8")
        pl = (ROOT / "frontend/src/components/PLTable.vue").read_text(encoding="utf-8")
        self.assertIn("/api/v1/export.html", top)
        self.assertIn("/api/v1/export/bu/", top)
        self.assertNotIn("`/bu/", top)
        self.assertIn("/api/v1/export/pl.xlsx", pl)
        self.assertIn("/api/v1/export/bu/", pl)
        self.assertNotIn("`/bu/", pl)

    def test_admin_api_ts_cookie_sid(self):
        api = (ROOT / "frontend/src/admin/api.ts").read_text(encoding="utf-8")
        self.assertIn("kanban_sid", api)
        self.assertNotIn("kanban_session", api)


class TestVersion272(unittest.TestCase):
    def test_version_file(self):
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(ver, "2.7.3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
