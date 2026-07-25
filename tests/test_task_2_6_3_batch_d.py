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
        m = re.search(r"m\.f\|\|\(m\.f=(\[[\s\S]*?\])\)", t)
        self.assertIsNotNone(m, "vite mapDeps array")
        files = re.findall(r'"([^"]+)"', m.group(1))
        # cockpit: import boot-cockpit + mapDeps([...])
        mm = re.search(
            r'import\("\./(boot-cockpit-[^"]+)"\),__vite__mapDeps\(\[([^\]]+)\]\)',
            t,
        )
        self.assertIsNotNone(mm, "cockpit branch")
        idxs = [int(x.strip()) for x in mm.group(2).split(",") if x.strip().isdigit()]
        deps = [files[i] for i in idxs if i < len(files)]
        self.assertTrue(any("boot-cockpit" in d for d in deps))
        self.assertFalse(any("element-plus" in d for d in deps), deps)
        # first screen gz estimate
        total = 0
        names = set(Path(d).name for d in deps)
        for p in dist.glob("*"):
            if p.name in names or p.name == Path(mm.group(1)).name:
                total += len(gzip.compress(p.read_bytes(), 6))
        for p in dist.glob("index-*.js"):
            total += len(gzip.compress(p.read_bytes(), 6))
        self.assertLessEqual(total, 260 * 1024, f"first screen gz={total}")


class TestD2LoginIpLockAndPasswordLen(unittest.TestCase):
    def test_lock_is_per_ip(self):
        login_guard.reset_all_for_tests()
        cfg = {"login_max_failures": 3, "login_lock_minutes": 5}
        for _ in range(3):
            login_guard.register_failure("lushasha", cfg, ip="1.1.1.1")
        self.assertTrue(login_guard.is_locked("lushasha", cfg, ip="1.1.1.1"))
        self.assertFalse(login_guard.is_locked("lushasha", cfg, ip="2.2.2.2"))
        login_guard.reset_all_for_tests()

    def test_password_min_8(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = loaders.load_config()
            cfg = dict(cfg)
            cfg["data_dir"] = str(tmp)
            accounts.seed_defaults(cfg, None)
            err = accounts.change_password(cfg, None, "lushasha", accounts.DEFAULT_ADMIN_PW, "1234567")
            self.assertIsNotNone(err)
            self.assertIn("8", err or "")
            err2 = accounts.change_password(cfg, None, "lushasha", accounts.DEFAULT_ADMIN_PW, "12345678")
            self.assertIsNone(err2)
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
            r1 = client.get("/bu/语言/export.html")
            r2 = client.get("/bu/__no_such_bu__/export.html")
            self.assertEqual(r1.status_code, r2.status_code)
            self.assertEqual(r1.status_code, 401)
            # 响应体完全一致（无法区分存在/不存在）
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
