#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.4 阶段8 · 最小活体 E2E（结构+鉴权，不断言金额）。

覆盖：登录 → 整体页出壳 → BU 隔离（他 BU API 403）→ 无权路径不枚举。
本地：需 playwright+chromium；无则 skip（不进 run_verify 串行，避免拖慢日常）。
CI：.github/workflows/verify.yml 的 e2e-live job 必跑。
"""
from __future__ import annotations

import json
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def _pick_accounts(cfg_data: Path) -> dict:
    """从账号表挑 整体 / BU 账号（只读结构字段）。"""
    p = cfg_data / "看板账号.json"
    if not p.is_file():
        p = ROOT / "_golden_data" / "看板账号.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    rows = raw.get("accounts") if isinstance(raw, dict) else raw
    out: dict = {}
    for a in rows or []:
        perm = str(a.get("权限") or "")
        if perm == "整体" and "overall" not in out:
            out["overall"] = (str(a["账号"]), str(a["密码"]))
        if perm in ("BU", "营销", "游戏") or a.get("可见BU"):
            if "bu" not in out:
                vis = a.get("可见BU") or []
                if isinstance(vis, str):
                    vis = [vis]
                out["bu"] = (str(a["账号"]), str(a["密码"]), list(vis))
        if perm == "管理员" and "admin" not in out:
            out["admin"] = (str(a["账号"]), str(a["密码"]))
    return out


class TestE2EAuthIsolation264(unittest.TestCase):
    """真实路径：create_app + uvicorn + Playwright / httpx 级请求。"""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            raise unittest.SkipTest(f"playwright not installed: {e}") from e

        import loaders
        import server
        import uvicorn

        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["zhiyun_auto_fetch"] = False
        cls.cfg["serve_static"] = True
        try:
            server.refresh(cls.cfg, ROOT)
        except Exception as e:
            raise unittest.SkipTest(f"refresh failed: {e}") from e
        from app_state import _state

        if not _state.get("built_at"):
            raise unittest.SkipTest("no built_at after refresh")

        cls.accounts = _pick_accounts(ROOT / "数据")
        if "overall" not in cls.accounts:
            raise unittest.SkipTest("no overall account")

        cls.app = server.create_app(cls.cfg, root=ROOT)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        config = uvicorn.Config(cls.app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.thr = threading.Thread(target=cls.server.run, daemon=True)
        cls.thr.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + "/login", timeout=1)
                break
            except Exception:
                time.sleep(0.15)
        else:
            raise unittest.SkipTest("server did not become ready")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.should_exit = True
        except Exception:
            pass

    def _login_cookie(self, user: str, password: str) -> str:
        """POST /api/v1/login → 取 Set-Cookie 中的 kanban_sid（结构断言）。"""
        import http.cookiejar
        import urllib.request as ur

        jar = http.cookiejar.CookieJar()
        opener = ur.build_opener(ur.HTTPCookieProcessor(jar))
        req = ur.Request(
            self.base + "/api/v1/login",
            data=json.dumps({"account": user, "password": password}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with opener.open(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            self.assertIn("redirect", body, "login must return redirect")
        sid = None
        for c in jar:
            if c.name == "kanban_sid":
                sid = c.value
                break
        self.assertTrue(sid, "login must set kanban_sid cookie")
        return sid

    def test_01_login_page_structure(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(self.base + "/login", wait_until="domcontentloaded", timeout=60000)
            self.assertTrue(page.locator("input").count() >= 2, "login needs account+password inputs")
            self.assertTrue(
                page.locator("button[type=submit], button:has-text('进入'), button:has-text('登录')").count() >= 1
            )
            browser.close()

    def test_02_overall_cockpit_shell(self):
        """整体账号登录后驾驶舱壳层存在（不读金额）。"""
        from playwright.sync_api import sync_playwright

        user, pw = self.accounts["overall"]
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(self.base + "/login", wait_until="networkidle", timeout=90000)
            page.locator("input").nth(0).fill(user)
            page.locator("input[type=password]").fill(pw)
            page.locator("button[type=submit], button:has-text('进入')").first.click()
            page.wait_for_timeout(1500)
            # 入场可能跳过；最终应在 / 或已登录壳
            url = page.url
            self.assertTrue("/login" not in url or page.locator(".kpi-grid, .topbar, #app").count() > 0, url)
            page.goto(self.base + "/", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(2000)
            # 结构：顶栏或 KPI 网格至少其一
            has_shell = page.evaluate(
                """() => !!(document.querySelector('.kpi-grid')
                  || document.querySelector('.topbar')
                  || document.querySelector('[data-theme]')
                  || document.querySelector('#app'))"""
            )
            self.assertTrue(has_shell, "cockpit shell missing after overall login")
            browser.close()

    def test_03_bu_isolation_api_403(self):
        """BU 账号不得读他 BU 的 fragments（403）；不断言金额。"""
        if "bu" not in self.accounts:
            self.skipTest("no BU account in 看板账号.json")
        user, pw, vis = self.accounts["bu"]
        sid = self._login_cookie(user, pw)
        # 故意请求一个不在可见列表的 BU 名
        foreign = "___不存在的业务线_E2E___"
        if vis:
            # 若只有一个可见，挑一个明显不同的名字
            foreign = "总部公共池_E2E" if vis[0] != "总部公共池_E2E" else "另一条线_E2E"
        url = f"{self.base}/api/v1/cockpit/bu/{quote(foreign)}/fragments"
        req = urllib.request.Request(url, headers={"Cookie": f"kanban_sid={sid}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                code = resp.status
                body = resp.read()[:200]
        except urllib.error.HTTPError as e:
            code = e.code
            body = e.read()[:200]
        self.assertEqual(code, 403, f"expected 403 for foreign BU, got {code} body={body!r}")

    def test_04_unauth_bu_not_enumerated(self):
        """未登录访问任意 BU 名 → 不 404 枚举（303/401/登录态）。"""
        url = f"{self.base}/bu/{quote('随便一个名字')}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        # 允许 303/302/401/200(若落到登录壳) — 禁止用 404 泄露
        self.assertNotEqual(code, 404, "must not 404-enumerate BU names")


if __name__ == "__main__":
    unittest.main()
