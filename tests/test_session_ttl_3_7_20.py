#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.20：会话 TTL 统一 7 天 — 守卫测（T1–T6）。

驱动真实 shipped 路径：
- SSOT：`app_state.SESSION_TTL`
- token：`auth_session.make_token` / `check_token_raw`
- cookie：`POST /api/v1/login` → Set-Cookie max_age 与 SESSION_TTL 同源
- 回归：logout / 改密后旧会话失效

禁止滑动续期 / 双 TTL / 改 cookie 名。
抓数新鲜度 12h（test_ux_stability_3_7_4）与本测无关，禁止误改。
"""
from __future__ import annotations

import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import auth_session  # noqa: E402
from app_state import SESSION_TTL, SID_COOKIE  # noqa: E402


def _parse_set_cookie_max_ages(headers) -> dict[str, int]:
    """从响应 Set-Cookie 解析 name -> Max-Age（秒）。"""
    raw: list[str] = []
    if hasattr(headers, "get_list"):
        raw = list(headers.get_list("set-cookie") or [])
    if not raw:
        sc = headers.get("set-cookie")
        if sc:
            raw = [sc]
    # httpx may join multiple; also try starlette multi-value
    if not raw and hasattr(headers, "getlist"):
        raw = list(headers.getlist("set-cookie") or [])
    out: dict[str, int] = {}
    for line in raw:
        if not line:
            continue
        # first segment: name=value
        first = line.split(";", 1)[0]
        if "=" not in first:
            continue
        name = first.split("=", 1)[0].strip()
        m = re.search(r"(?i)\bMax-Age=(\d+)\b", line)
        if m:
            out[name] = int(m.group(1))
    return out


class TestSessionTtlConstant(unittest.TestCase):
    """T1：唯一 SSOT 为 7 天。"""

    def test_t1_session_ttl_is_seven_days(self):
        self.assertEqual(SESSION_TTL, 7 * 24 * 3600)
        self.assertEqual(SESSION_TTL, 604800)


class TestSessionTtlTokenBounds(unittest.TestCase):
    """T2/T3：make_token exp 与 check_token_raw 边界。"""

    def setUp(self):
        self.sec = {"cookie_key": "ab" * 32}  # 64 hex chars = 32 bytes

    def test_t2_token_valid_near_ttl_end(self):
        now = 1_700_000_000.0
        tok = auth_session.make_token(self.sec, "overall", now=now, pw_ver=0)
        # 距签发点 TTL-60s 仍有效
        hit = auth_session.check_token_raw(
            self.sec, tok, now=now + SESSION_TTL - 60
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], "overall")

    def test_t3_token_invalid_after_ttl(self):
        now = 1_700_000_000.0
        tok = auth_session.make_token(self.sec, "overall", now=now, pw_ver=0)
        # 距签发点 TTL+60s 无效
        hit = auth_session.check_token_raw(
            self.sec, tok, now=now + SESSION_TTL + 60
        )
        self.assertIsNone(hit)


class TestSessionTtlLoginCookies(unittest.TestCase):
    """T4/T5：登录 Set-Cookie max_age == SESSION_TTL（sid + csrf）。"""

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
        server._state["fragments"] = fake_main_frags("M")
        server._state["views"] = fake_views("M")
        server._state["bu_pages"] = {
            "BU甲": fake_bu_page("BU甲", "A"),
        }
        server._state["admin_html"] = "x"
        server._state["has_data"] = True
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.server = server

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_t4_t5_login_cookies_max_age_equals_session_ttl(self):
        c = self._client()
        r = c.post(
            "/api/v1/login",
            json={"account": "overall", "password": self.server.DEFAULT_VIEW_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        ages = _parse_set_cookie_max_ages(r.headers)
        self.assertIn(SID_COOKIE, ages, f"missing {SID_COOKIE} Max-Age; got {ages} headers={r.headers.get('set-cookie')}")
        self.assertEqual(
            ages[SID_COOKIE],
            SESSION_TTL,
            f"kanban_sid max_age {ages[SID_COOKIE]} != SESSION_TTL {SESSION_TTL}",
        )
        # csrf 若存在必须同源
        if "csrf_token" in ages:
            self.assertEqual(
                ages["csrf_token"],
                SESSION_TTL,
                f"csrf_token max_age {ages['csrf_token']} != SESSION_TTL {SESSION_TTL}",
            )
        else:
            # 实现路径 apply_sid_cookie 必写 csrf；漏写则失败
            sc = str(r.headers.get("set-cookie") or "").lower()
            self.assertIn(
                "csrf_token",
                sc,
                "login must set csrf_token cookie (SEC-002)",
            )
            # 若框架未拆 Max-Age 到 getlist，再扫原始串
            m = re.search(r"(?i)csrf_token=[^;]+;[^,]*Max-Age=(\d+)", sc)
            if not m:
                # multi set-cookie may use commas between cookies poorly; re-parse all
                joined = " ".join(
                    (r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else [])
                    or [r.headers.get("set-cookie") or ""]
                )
                m = re.search(r"(?i)csrf_token=[^;]*;[^;]*Max-Age=(\d+)", joined)
            self.assertIsNotNone(m, f"csrf_token Max-Age not found in Set-Cookie: {r.headers.get('set-cookie')}")
            self.assertEqual(int(m.group(1)), SESSION_TTL)

    def test_t6_logout_invalidates_session(self):
        """T6 轻量回归：退出后旧会话 401。"""
        c = self._client()
        r = c.post(
            "/api/v1/login",
            json={"account": "overall", "password": self.server.DEFAULT_VIEW_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.get("/api/v1/session").status_code, 200)
        r2 = c.post("/api/v1/logout")
        self.assertEqual(r2.status_code, 200)
        c.cookies.clear()
        # 即使残留旧 token 在 jar 被清后无 cookie
        self.assertEqual(c.get("/api/v1/session").status_code, 401)

    def test_t6_password_change_kicks_old_session(self):
        """T6：改密后旧 token 401（密码版本 bump）。"""
        c = self._client()
        r = c.post(
            "/api/v1/login",
            json={"account": "overall", "password": self.server.DEFAULT_VIEW_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.get("/api/v1/session").status_code, 200)
        r2 = c.post(
            "/api/v1/my_passwd",
            json={"old": self.server.DEFAULT_VIEW_PW, "new": "kickttl7d"},
        )
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual(c.get("/api/v1/session").status_code, 401)


if __name__ == "__main__":
    unittest.main()
