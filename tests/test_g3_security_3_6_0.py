# -*- coding: utf-8 -*-
"""3.6.0 G3 / 小修：明文密码 SSOT、CSRF fail-closed、安全头。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestPasswordKdf(unittest.TestCase):
    def test_hash_and_verify(self):
        from password_kdf import hash_password, is_hashed, verify_password

        h = hash_password("secret-中文")
        self.assertTrue(is_hashed(h))
        self.assertTrue(verify_password(h, "secret-中文"))
        self.assertFalse(verify_password(h, "wrong"))

    def test_legacy_plain_still_verifies(self):
        from password_kdf import verify_password

        self.assertTrue(verify_password("8888", "8888"))
        self.assertFalse(verify_password("8888", "9999"))


class TestPublicRowPlaintextSsot(unittest.TestCase):
    def test_with_password_returns_plain(self):
        import accounts

        row = accounts.public_row(
            {"账号": "a", "显示名": "甲", "权限": "管理员", "密码": "kanban2026"},
            with_password=True,
        )
        self.assertEqual(row.get("密码"), "kanban2026")
        self.assertTrue(row.get("初始密码") or row.get("must_change_password"))

    def test_without_password_omits_field(self):
        import accounts

        row = accounts.public_row(
            {"账号": "a", "显示名": "甲", "权限": "管理员", "密码": "kanban2026"},
            with_password=False,
        )
        self.assertNotIn("密码", row)

    def test_set_password_writes_plain_not_hash(self):
        import accounts

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        cfg = {"data_dir": str(tmp), "db_path": "看板.db"}
        (tmp / "看板账号.json").write_text(
            '{"accounts":[{"账号":"u1","显示名":"U","权限":"整体","密码":"8888","密码版本":1}]}',
            encoding="utf-8",
        )
        err = accounts.set_password(cfg, tmp, "u1", "new-plain-9")
        self.assertIsNone(err)
        acc = accounts.find_account(cfg, tmp, "u1")
        assert acc is not None
        self.assertEqual(acc["密码"], "new-plain-9")
        self.assertFalse(str(acc["密码"]).startswith("pbkdf2_sha256$"))
        row = accounts.public_row(acc, with_password=True)
        self.assertEqual(row["密码"], "new-plain-9")


class TestCsrfAndHeaders(unittest.TestCase):
    def test_origin_mismatch_fails(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="https://evil.example",
            referer=None,
            host="localhost:8018",
        )
        self.assertFalse(ok)
        self.assertIn("origin", reason)

    def test_same_origin_ok(self):
        from csrf_guard import csrf_ok

        ok, _ = csrf_ok(
            method="POST",
            origin="http://localhost:8018",
            referer=None,
            host="localhost:8018",
        )
        self.assertTrue(ok)

    def test_missing_origin_referer_fail_closed(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin=None,
            referer=None,
            host="example.com",
            client_host="203.0.113.9",
        )
        self.assertFalse(ok)
        self.assertIn("missing_origin", reason)

    def test_bad_csrf_token_fails(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin=None,
            referer=None,
            host="localhost:8018",
            csrf_header="aaa",
            csrf_cookie="bbb",
            client_host="203.0.113.9",
        )
        self.assertFalse(ok)

    def test_valid_token_ok(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin=None,
            referer=None,
            host="localhost:8018",
            csrf_header="same-tok",
            csrf_cookie="same-tok",
            client_host="203.0.113.9",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "token_ok")

    def test_testclient_allowlisted(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin=None,
            referer=None,
            host="testserver",
            client_host="testclient",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "allowlisted")

    def test_ops_loopback_allowlisted(self):
        from csrf_guard import OPS_HEADER_VALUE, csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin=None,
            referer=None,
            host="127.0.0.1:8018",
            client_host="127.0.0.1",
            ops_header=OPS_HEADER_VALUE,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "allowlisted")

    def test_security_headers_include_csp(self):
        from security_headers import default_security_headers

        h = default_security_headers(https=True)
        self.assertIn("Content-Security-Policy", h)
        self.assertIn("Strict-Transport-Security", h)
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")

    def test_middleware_no_silent_pass_on_missing_origin(self):
        src = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "middleware_stack.py"
        )
        text = src.read_text(encoding="utf-8")
        self.assertNotIn("no_cross_site_signal", text)
        self.assertIn("check_error", text)


if __name__ == "__main__":
    unittest.main()
