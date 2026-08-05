# -*- coding: utf-8 -*-
"""P4 AUTH/SEC：BU 空态裁剪、CIFS 无密码 argv、明细 403、CSRF 签发。"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestAuth001EmptyBuNames(unittest.TestCase):
    def test_empty_bu_vm_uses_visible_names_helper(self):
        src = (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8")
        self.assertIn("_visible_bu_names", src)
        self.assertIn("AUTH-001", src)
        # 定位 BU 空态：先取 names 再组 empty out
        self.assertIn('names, label = _visible_bu_names()', src)
        m = __import__("re").search(
            r'names, label = _visible_bu_names\(\)[\s\S]*?"scope":\s*"bu"[\s\S]*?"empty":\s*True[\s\S]*?return JSONResponse\(out\)',
            src,
        )
        self.assertTrue(m, "BU empty summary branch with visible names")
        body = m.group(0)
        self.assertIn('"bu_names": names', body)
        self.assertNotIn(
            'list((_state.get("bu_pages") or {}).keys())',
            body,
            "空态不得泄露全公司 bu_names",
        )


class TestSec001CifsNoPasswordArgv(unittest.TestCase):
    def test_run_cifs_apply_uses_env_not_argv(self):
        import ledger_cifs

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["env"] = kwargs.get("env") or {}

            class R:
                returncode = 0
                stdout = "ok"
                stderr = ""

            return R()

        with mock.patch.object(ledger_cifs, "apply_script_path", return_value="/bin/true"):
            with mock.patch.object(ledger_cifs, "use_sudo_for_apply", return_value=False):
                with mock.patch.object(ledger_cifs.subprocess, "run", side_effect=fake_run):
                    with mock.patch.object(ledger_cifs, "cred_path", return_value=Path("/tmp/x.cred")):
                        with mock.patch.object(Path, "is_file", return_value=True):
                            ledger_cifs.run_cifs_apply(
                                username="u",
                                password="s3cret-pw",
                                server="s",
                                share="sh",
                                mount_root="/mnt/x",
                                dry_run=True,
                            )
        cmd = " ".join(str(x) for x in captured["cmd"])
        self.assertNotIn("s3cret-pw", cmd)
        self.assertNotIn("--password ", cmd + " ")
        self.assertIn("--password-from-env", cmd)
        self.assertEqual(captured["env"].get("KANBAN_CIFS_PASSWORD"), "s3cret-pw")


class TestAuth003DetailForbidden(unittest.TestCase):
    def test_logged_in_non_expense_is_403(self):
        import authz
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as cm:
            authz.resolve_expense_view_access(
                user=None,
                vacc={"账号": "bu1", "权限": "BU", "可见BU": ["甲"]},
                bu=None,
                cfg={},
                force_whitelist=False,
                table="收入明细",
            )
        self.assertEqual(cm.exception.status_code, 403)


class TestSec002CsrfCookieOnLogin(unittest.TestCase):
    def test_apply_sid_sets_csrf_cookie(self):
        src = (ROOT / "src" / "session_ctx.py").read_text(encoding="utf-8")
        self.assertIn("csrf_token", src)
        self.assertIn("SEC-002", src)


if __name__ == "__main__":
    unittest.main()
