#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.3 批次 D：首包分片 / 登录 IP 锁 / 鉴权顺序 / PROFILE / 密码 8 位。"""
from __future__ import annotations

import gzip
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import loaders  # noqa: E402
import login_guard  # noqa: E402


class TestD1CockpitNoElementPlus(unittest.TestCase):
    def test_dist_cockpit_deps_no_element_plus(self):
        dist = ROOT / "frontend" / "dist" / "assets"
        if not dist.is_dir():
            self.skipTest("no frontend/dist")
        idx = next(dist.glob("index-*.js"), None)
        self.assertIsNotNone(idx)
        t = idx.read_text(encoding="utf-8", errors="replace")
        # 2.6.5：async 分包后 mapDeps 形态可变；仍须 boot-cockpit 且首屏无 element-plus
        boot_m = re.search(r'import\("\./(boot-cockpit-[^"]+)"\)', t)
        self.assertIsNotNone(boot_m, "cockpit branch boot-cockpit import")
        boot_name = boot_m.group(1)
        boot_js = dist / boot_name
        self.assertTrue(boot_js.is_file(), boot_name)
        boot_txt = boot_js.read_text(encoding="utf-8", errors="replace")
        # 看端 boot 包体不得拉 element-plus（管理端 bootstrap 另包）
        self.assertNotIn("element-plus", boot_txt)
        self.assertNotIn("ElementPlus", boot_txt)
        # first screen gz：boot + 其静态 import + css + index
        names = {boot_name, idx.name}
        for imp in re.findall(r'from"\./([^"]+)"', boot_txt):
            names.add(Path(imp).name)
        for p in dist.glob("boot-cockpit-*.css"):
            names.add(p.name)
        total = 0
        for p in dist.glob("*"):
            if p.name in names:
                total += len(gzip.compress(p.read_bytes(), 6))
        # 2.6.5 收口线 90.8KB；兼容旧 260KB 上限
        self.assertLessEqual(total, 260 * 1024, f"first screen gz={total}")
        self.assertLessEqual(total, 90800, f"first screen gz={total} > 90800")
        # 证据
        Path(
            "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-c31b43ef0cf9/implementer/first_paint_gz.txt"
        ).write_text(f"{total}\n", encoding="utf-8")


class TestD2LoginIpLockAndPasswordLen(unittest.TestCase):
    def test_lock_is_per_ip(self):
        login_guard.reset_all_for_tests()
        cfg = {"login_max_failures": 3, "login_lock_minutes": 5}
        for _ in range(3):
            login_guard.register_failure("lushasha", cfg, ip="1.1.1.1")
        self.assertTrue(login_guard.is_locked("lushasha", cfg, ip="1.1.1.1"))
        self.assertFalse(login_guard.is_locked("lushasha", cfg, ip="2.2.2.2"))
        login_guard.reset_all_for_tests()

    def test_password_nonempty_free_length(self):
        """2.6.12：密码非空即可；短密成功；空密失败。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = loaders.load_config()
            cfg = dict(cfg)
            cfg["data_dir"] = str(tmp)
            accounts.seed_defaults(cfg, None)
            err = accounts.change_password(cfg, None, "lushasha", accounts.DEFAULT_ADMIN_PW, "")
            self.assertIsNotNone(err)
            self.assertIn("空", err or "")
            err2 = accounts.change_password(cfg, None, "lushasha", accounts.DEFAULT_ADMIN_PW, "1234567")
            self.assertIsNone(err2)
            err3 = accounts.set_password(cfg, None, "lushasha", "ab")
            self.assertIsNone(err3)
            err4 = accounts.set_password(cfg, None, "lushasha", "   ")
            self.assertIsNotNone(err4)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestD3AuthBeforeExistence(unittest.TestCase):
    def test_export_same_response_missing_and_forbidden(self):
        from fastapi.testclient import TestClient
        import server

        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy2(ROOT / "config.json", tmp / "config.json")
            (tmp / "数据").mkdir()
            cfg = loaders.load_config(tmp)
            accounts.seed_defaults(cfg, tmp)
            app = server.create_app(cfg, root=tmp)
            client = TestClient(app, follow_redirects=False)
            # 未登录：存在 BU 与不存在 BU 同一 401
            # 未登录：存在 BU 与不存在 BU 同 401（先鉴权，不 404 泄露）
            r1 = client.get("/bu/语言/export.html")
            r2 = client.get("/bu/__no_such_bu__/export.html")
            self.assertEqual(r1.status_code, 401)
            self.assertEqual(r2.status_code, 401)
            self.assertEqual(r1.content, r2.content)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestD4KanbanProfile(unittest.TestCase):
    def test_profile_env_applied(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy2(ROOT / "config.json", tmp / "config.json")
            os.environ["KANBAN_PROFILE"] = "dev"
            cfg = loaders.load_config(tmp, strict=False)
            self.assertEqual(cfg.get("_active_profile"), "dev")
            self.assertEqual(cfg.get("data_dir"), "_golden_data")
            self.assertFalse(cfg.get("zhiyun_auto_fetch"))
        finally:
            os.environ.pop("KANBAN_PROFILE", None)
            shutil.rmtree(tmp, ignore_errors=True)


class TestD5DocstringFen(unittest.TestCase):
    def test_loaders_std_docstring_says_fen(self):
        p = ROOT / "src" / "db" / "loaders_std.py"
        t = p.read_text(encoding="utf-8")
        self.assertIn("int 分", t)
        # 旧误写应已去掉（本函数 docstring）
        m = re.search(r"def load_ledger[\s\S]{0,400}", t)
        self.assertIsNotNone(m)
        self.assertNotIn("元 float", m.group(0))


if __name__ == "__main__":
    unittest.main()
