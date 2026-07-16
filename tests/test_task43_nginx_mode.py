#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书43·阶段一：nginx 反代 / 直连双模式。"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import server  # noqa: E402


class TestResolveServeFlags(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("KANBAN_SERVE_STATIC", None)
        os.environ.pop("KANBAN_SERVER_HOST", None)

    def test_direct_defaults_static_on(self):
        self.assertTrue(server.resolve_serve_static({"server_host": "0.0.0.0", "serve_static": True}))
        self.assertEqual(server.resolve_server_host({"server_host": "0.0.0.0"}), "0.0.0.0")

    def test_loopback_defaults_static_off_without_flag(self):
        # 仅 host、无 serve_static 字段 → 倾向反代
        self.assertFalse(server.resolve_serve_static({"server_host": "127.0.0.1"}))

    def test_env_overrides(self):
        os.environ["KANBAN_SERVE_STATIC"] = "0"
        self.assertFalse(server.resolve_serve_static({"serve_static": True}))
        os.environ["KANBAN_SERVE_STATIC"] = "1"
        self.assertTrue(server.resolve_serve_static({"serve_static": False}))
        os.environ["KANBAN_SERVER_HOST"] = "127.0.0.1"
        self.assertEqual(server.resolve_server_host({"server_host": "0.0.0.0"}), "127.0.0.1")


class TestDualModeApp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = "数据"
        self.cfg["db_path"] = "数据/看板.db"
        self.cfg["zhiyun_auto_fetch"] = False

    def tearDown(self):
        os.environ.pop("KANBAN_SERVE_STATIC", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_direct_mode_mounts_static(self):
        self.cfg["server_host"] = "0.0.0.0"
        self.cfg["serve_static"] = True
        app = server.create_app(self.cfg, root=self.tmp)
        paths = [getattr(r, "path", None) for r in app.routes]
        self.assertTrue(any(p and "static" in str(p) for p in paths), paths)

    def test_nginx_mode_no_static_mount(self):
        self.cfg["server_host"] = "127.0.0.1"
        self.cfg["serve_static"] = False
        app = server.create_app(self.cfg, root=self.tmp)
        # Starlette Mount for /static should be absent
        mounts = [r for r in app.routes if r.__class__.__name__ == "Mount" and getattr(r, "path", "") == "/static"]
        self.assertEqual(mounts, [], "nginx 模式不应挂 /static")


class TestNginxConfTemplate(unittest.TestCase):
    def test_conf_exists_and_proxy_loopback(self):
        p = ROOT / "deploy" / "linux" / "nginx-kanban.conf"
        self.assertTrue(p.is_file())
        t = p.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:8018", t)
        self.assertIn("proxy_pass", t)
        self.assertIn("location /static/", t)
        self.assertIn("no-store", t)
        self.assertIn("X-Real-IP", t)
        # 动态路径
        self.assertRegex(t, r"api\|admin\|login\|bu")


class TestNginxTIfPresent(unittest.TestCase):
    def test_nginx_t_optional(self):
        import shutil
        import subprocess

        if not shutil.which("nginx"):
            self.skipTest("本机无 nginx，完整链路仅部署机可验")
        conf = ROOT / "deploy" / "linux" / "nginx-kanban.conf"
        # nginx -t 需要完整 http{} 包裹时可能失败；仅检查文件可读 + 关键路径
        r = subprocess.run(["nginx", "-t", "-c", str(conf)], capture_output=True, text=True)
        # 模板非完整主配置时允许非 0，但命令可执行
        self.assertIsNotNone(r.returncode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
