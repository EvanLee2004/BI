# -*- coding: utf-8 -*-
"""3.6.0 G3：密码哈希、无密回显、CSRF/Origin、安全头。"""

from __future__ import annotations

import unittest


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


class TestPublicRowNoPassword(unittest.TestCase):
    def test_no_password_field(self):
        import accounts

        row = accounts.public_row(
            {"账号": "a", "显示名": "甲", "权限": "管理员", "密码": "kanban2026"},
            with_password=True,
        )
        self.assertNotIn("密码", row)
        self.assertTrue(row.get("初始密码") or row.get("must_change_password"))


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

    def test_security_headers_include_csp(self):
        from security_headers import default_security_headers

        h = default_security_headers(https=True)
        self.assertIn("Content-Security-Policy", h)
        self.assertIn("Strict-Transport-Security", h)
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
