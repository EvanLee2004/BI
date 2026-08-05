# -*- coding: utf-8 -*-
"""3.7.15 台账 CIFS B：拼装/校验/GET 无密/POST/旧配置/脚本 tmpdir。"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import ledger_cifs as lc  # noqa: E402
import loaders  # noqa: E402


class TestShouldApplyGate(unittest.TestCase):
    def test_path_only_no_apply(self):
        cfg = {lc.KEY_USERNAME: "u1"}
        payload = {
            lc.KEY_SERVER: "10.0.0.1",
            lc.KEY_SHARE: "s",
            lc.KEY_RELPATH: "a.xlsx",
            lc.KEY_USERNAME: "u1",  # same as cfg — no apply
        }
        self.assertFalse(lc.should_apply_credentials(payload, cfg))

    def test_password_triggers_apply(self):
        self.assertTrue(
            lc.should_apply_credentials({"ledger_smb_password": "x"}, {lc.KEY_USERNAME: "u"})
        )

    def test_username_change_triggers(self):
        cfg = {lc.KEY_USERNAME: "old"}
        self.assertTrue(
            lc.should_apply_credentials({lc.KEY_USERNAME: "new"}, cfg)
        )

    def test_password_set_uses_cfg_flag_without_read(self):
        self.assertTrue(lc.password_set_on_disk(cfg={lc.KEY_PASSWORD_SET: True}))

    def test_password_set_unreadable_nonempty_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="cred_unr_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        p = tmp / "c.cred"
        p.write_text("username=u\npassword=secret\n", encoding="utf-8")
        os.chmod(p, 0o000)
        try:
            # stat may work; read fails → True if size>0
            self.assertTrue(lc.password_set_on_disk(p))
        finally:
            os.chmod(p, 0o600)

    def test_use_sudo_default_off_for_repo_script(self):
        old = os.environ.get("KANBAN_CIFS_USE_SUDO")
        old_s = os.environ.get("KANBAN_CIFS_APPLY_SCRIPT")
        try:
            os.environ.pop("KANBAN_CIFS_USE_SUDO", None)
            os.environ["KANBAN_CIFS_APPLY_SCRIPT"] = str(
                ROOT / "deploy" / "linux" / "kanban-cifs-apply.sh"
            )
            self.assertFalse(lc.use_sudo_for_apply())
            os.environ["KANBAN_CIFS_USE_SUDO"] = "1"
            self.assertTrue(lc.use_sudo_for_apply())
        finally:
            if old is None:
                os.environ.pop("KANBAN_CIFS_USE_SUDO", None)
            else:
                os.environ["KANBAN_CIFS_USE_SUDO"] = old
            if old_s is None:
                os.environ.pop("KANBAN_CIFS_APPLY_SCRIPT", None)
            else:
                os.environ["KANBAN_CIFS_APPLY_SCRIPT"] = old_s


class TestAssembleAndValidate(unittest.TestCase):
    def test_assemble_posix_path(self):
        p = lc.assemble_ledger_share_path(
            mount_root="/mnt/kanban-ledger",
            relpath="lara.zhao/收单台账/收单台账.xlsx",
            server="192.168.10.151",
            share="财务部",
        )
        self.assertEqual(p, "/mnt/kanban-ledger/lara.zhao/收单台账/收单台账.xlsx")

    def test_reject_dotdot(self):
        with self.assertRaises(ValueError):
            lc.normalize_relpath("../etc/passwd")
        with self.assertRaises(ValueError):
            lc.assemble_ledger_share_path(relpath="a/../../b", mount_root="/mnt/kanban-ledger")

    def test_reject_absolute_relpath(self):
        with self.assertRaises(ValueError):
            lc.normalize_relpath("/abs/x.xlsx")

    def test_reject_empty_server(self):
        with self.assertRaises(ValueError):
            lc.normalize_server("")

    def test_parse_legacy_ok(self):
        d = lc.parse_legacy_share_path("/mnt/kanban-ledger/foo/bar.xlsx")
        self.assertIsNotNone(d)
        assert d is not None
        self.assertEqual(d[lc.KEY_RELPATH], "foo/bar.xlsx")
        self.assertEqual(d[lc.KEY_MOUNT_ROOT], "/mnt/kanban-ledger")

    def test_parse_legacy_gvfs_none(self):
        self.assertIsNone(
            lc.parse_legacy_share_path(
                "/run/user/1000/gvfs/smb-share:server=x,share=y/file.xlsx"
            )
        )


class TestSettingsPublicNoPassword(unittest.TestCase):
    def test_view_never_has_password_key(self):
        cfg = {
            lc.KEY_SERVER: "10.0.0.1",
            lc.KEY_SHARE: "share1",
            lc.KEY_RELPATH: "a/b.xlsx",
            lc.KEY_USERNAME: "u1",
            lc.KEY_MOUNT_ROOT: "/mnt/kanban-ledger",
            lc.KEY_SHARE_PATH: "/mnt/kanban-ledger/a/b.xlsx",
        }
        v = lc.settings_public_view(cfg)
        self.assertNotIn("password", v)
        self.assertNotIn("ledger_smb_password", v)
        self.assertIn("ledger_smb_password_set", v)
        self.assertEqual(v[lc.KEY_SERVER], "10.0.0.1")

    def test_legacy_only_fallback(self):
        cfg = {lc.KEY_SHARE_PATH: "/some/other/path/ledger.xlsx"}
        v = lc.settings_public_view(cfg)
        self.assertTrue(v.get("ledger_legacy_path_only") or v.get("ledger_migrate_hint"))


class TestHttpSettings3715(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import server

        cls.tmp = Path(tempfile.mkdtemp(prefix="t3715_cifs_"))
        shutil.copy2(ROOT / "config.json", cls.tmp / "config.json")
        (cls.tmp / "数据").mkdir()
        cls.cfg = loaders.load_config(cls.tmp)
        cls.server = server
        cls._orig = server.recompute
        server.recompute = lambda *a, **k: None
        accounts.seed_defaults(cls.cfg, cls.tmp)
        rows = accounts.load_accounts(cls.cfg, cls.tmp)
        rows.append(
            {
                "账号": "view_only",
                "显示名": "看",
                "权限": accounts.PERM_MAIN,
                "密码": accounts.DEFAULT_VIEW_PW,
            }
        )
        accounts.save_accounts(cls.cfg, cls.tmp, rows)
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.client = TestClient(cls.app, follow_redirects=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.recompute = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _login_admin(self):
        r = self.client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.cookies.get(self.server.SID_COOKIE)
        return {"Cookie": f"{self.server.SID_COOKIE}={sid}"}

    def _login_view(self):
        r = self.client.post(
            "/api/v1/login",
            json={"account": "view_only", "password": accounts.DEFAULT_VIEW_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.cookies.get(self.server.SID_COOKIE)
        return {"Cookie": f"{self.server.SID_COOKIE}={sid}"}

    def test_get_settings_no_password_key(self):
        hdr = self._login_admin()
        r = self.client.get("/api/v1/admin/settings", headers=hdr)
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertNotIn("password", j)
        self.assertNotIn("ledger_smb_password", j)
        self.assertIn("ledger_smb_password_set", j)
        self.assertIn("ledger_share_path", j)
        self.assertIn(lc.KEY_MOUNT_ROOT, j)

    def test_non_admin_403(self):
        hdr = self._login_view()
        r = self.client.get("/api/v1/admin/settings", headers=hdr)
        self.assertIn(r.status_code, (401, 403), r.text)
        r2 = self.client.post(
            "/api/v1/admin/settings",
            headers=hdr,
            json={lc.KEY_SERVER: "10.0.0.2", lc.KEY_SHARE: "s", lc.KEY_RELPATH: "a.xlsx"},
        )
        self.assertIn(r2.status_code, (401, 403), r2.text)

    def test_post_structured_updates_path_no_apply_without_user(self):
        hdr = self._login_admin()
        # 不触发 apply：不传 username/password
        with mock.patch("ledger_cifs.run_cifs_apply") as m:
            r = self.client.post(
                "/api/v1/admin/settings",
                headers=hdr,
                json={
                    lc.KEY_SERVER: "10.20.30.40",
                    lc.KEY_SHARE: "财务部",
                    lc.KEY_RELPATH: "team/台账.xlsx",
                    lc.KEY_MOUNT_ROOT: "/mnt/kanban-ledger",
                },
            )
            self.assertEqual(r.status_code, 200, r.text)
            j = r.json()
            self.assertEqual(
                j.get("ledger_share_path"),
                "/mnt/kanban-ledger/team/台账.xlsx",
            )
            m.assert_not_called()

    def test_post_password_triggers_apply(self):
        hdr = self._login_admin()
        with mock.patch("ledger_cifs.run_cifs_apply", return_value="ok") as m:
            r = self.client.post(
                "/api/v1/admin/settings",
                headers=hdr,
                json={
                    lc.KEY_SERVER: "10.20.30.40",
                    lc.KEY_SHARE: "财务部",
                    lc.KEY_RELPATH: "team/台账.xlsx",
                    lc.KEY_USERNAME: "fake_user",
                    "ledger_smb_password": "not-a-real-prod-secret-xx",
                },
            )
            self.assertEqual(r.status_code, 200, r.text)
            m.assert_called_once()
            # 响应与 note 不得回显密码
            self.assertNotIn("not-a-real-prod-secret-xx", r.text)
            self.assertNotIn("password=", r.text.lower())

    def test_post_dotdot_400(self):
        hdr = self._login_admin()
        r = self.client.post(
            "/api/v1/admin/settings",
            headers=hdr,
            json={
                lc.KEY_SERVER: "10.0.0.1",
                lc.KEY_SHARE: "s",
                lc.KEY_RELPATH: "../x.xlsx",
            },
        )
        self.assertEqual(r.status_code, 400, r.text)

    def test_legacy_path_only_save_still_works(self):
        hdr = self._login_admin()
        r = self.client.post(
            "/api/v1/admin/settings",
            headers=hdr,
            json={"ledger_share_path": "/mnt/kanban-ledger/legacy/only.xlsx"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("ledger_share_path"), "/mnt/kanban-ledger/legacy/only.xlsx")


class TestApplyScriptTmpdir(unittest.TestCase):
    def test_script_writes_cred_0600(self):
        script = ROOT / "deploy" / "linux" / "kanban-cifs-apply.sh"
        self.assertTrue(script.is_file())
        tmp = Path(tempfile.mkdtemp(prefix="cifs_cred_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cred = tmp / "cifs-ledger.cred"
        env = os.environ.copy()
        # 直接跑脚本
        import subprocess

        r = subprocess.run(
            [
                "bash",
                str(script),
                "--cred-file",
                str(cred),
                "--username",
                "test_user_fixture",
                "--password",
                "test_pw_fixture_not_prod",
                "--skip-mount",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(cred.is_file())
        mode = stat.S_IMODE(cred.stat().st_mode)
        self.assertEqual(mode, 0o600, oct(mode))
        text = cred.read_text(encoding="utf-8")
        self.assertIn("username=test_user_fixture", text)
        self.assertIn("password=test_pw_fixture_not_prod", text)
        # 无 password 时保留旧密
        r2 = subprocess.run(
            [
                "bash",
                str(script),
                "--cred-file",
                str(cred),
                "--username",
                "test_user_2",
                "--skip-mount",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        t2 = cred.read_text(encoding="utf-8")
        self.assertIn("username=test_user_2", t2)
        self.assertIn("password=test_pw_fixture_not_prod", t2)

    def test_run_cifs_apply_via_python(self):
        script = ROOT / "deploy" / "linux" / "kanban-cifs-apply.sh"
        tmp = Path(tempfile.mkdtemp(prefix="cifs_py_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cred = tmp / "c.cred"
        old = {
            "KANBAN_CIFS_CRED_PATH": os.environ.get("KANBAN_CIFS_CRED_PATH"),
            "KANBAN_CIFS_APPLY_SCRIPT": os.environ.get("KANBAN_CIFS_APPLY_SCRIPT"),
            "KANBAN_CIFS_SKIP_MOUNT": os.environ.get("KANBAN_CIFS_SKIP_MOUNT"),
            "KANBAN_CIFS_USE_SUDO": os.environ.get("KANBAN_CIFS_USE_SUDO"),
        }
        try:
            os.environ["KANBAN_CIFS_CRED_PATH"] = str(cred)
            os.environ["KANBAN_CIFS_APPLY_SCRIPT"] = str(script)
            os.environ["KANBAN_CIFS_SKIP_MOUNT"] = "1"
            os.environ["KANBAN_CIFS_USE_SUDO"] = "0"
            out = lc.run_cifs_apply(
                username="u_py",
                password="pw_py_fixture",
                server="1.2.3.4",
                share="sh",
                mount_root="/mnt/kanban-ledger",
            )
            self.assertTrue(out)
            self.assertTrue(cred.is_file())
            self.assertTrue(lc.password_set_on_disk(cred))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestNoRealSecretsInTree(unittest.TestCase):
    def test_no_lara_password_literals(self):
        # 结构守卫：源码夹具不含常见生产凭据模式（假 fixture 允许 test_ 前缀）
        bad = []
        for p in (ROOT / "src").rglob("*.py"):
            t = p.read_text(encoding="utf-8", errors="replace")
            if "password=亮" in t or "lara.zhao:P@" in t:
                bad.append(str(p))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
