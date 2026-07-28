#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.7.3 维护模式：on/off/expire/gitignore/R1 一键更新 dirty 护栏。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import maintenance_mode as mm  # noqa: E402
import updater  # noqa: E402


def _cfg(tmp: Path) -> dict:
    return {"data_dir": "数据", "db_path": "看板.db"}


class TestMaintenanceFlagBasics(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = _cfg(self.tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_flag_path_uses_loaders_data_dir(self):
        p = mm.flag_path(self.cfg, self.tmp)
        self.assertEqual(p, loaders.data_dir(self.cfg, self.tmp) / "maintenance.flag")
        self.assertTrue(str(p).endswith(str(Path("数据") / "maintenance.flag")) or p.name == "maintenance.flag")

    def test_turn_on_off_is_on_atomic(self):
        self.assertFalse(mm.is_on(self.cfg, self.tmp))
        path = mm.turn_on("update", self.cfg, self.tmp, pid=12345)
        self.assertTrue(path.is_file())
        self.assertTrue(mm.is_on(self.cfg, self.tmp))
        data = mm.read_flag(self.cfg, self.tmp)
        self.assertIsNotNone(data)
        self.assertEqual(data["reason"], "update")
        self.assertEqual(data["pid"], 12345)
        self.assertIn("ts", data)
        # 无残留 tmp
        leftovers = list((self.tmp / "数据").glob("maintenance.flag.tmp*"))
        self.assertEqual(leftovers, [])
        self.assertTrue(mm.turn_off(self.cfg, self.tmp))
        self.assertFalse(mm.is_on(self.cfg, self.tmp))
        self.assertFalse(mm.turn_off(self.cfg, self.tmp))  # 幂等

    def test_maybe_expire_timeout_forces_off(self):
        path = mm.turn_on("boot", self.cfg, self.tmp)
        # 伪造 mtime 为 11 分钟前
        old = time.time() - 11 * 60
        os.utime(path, (old, old))
        with mock.patch("maintenance_mode.alert_event", create=True):
            expired = mm.maybe_expire(max_minutes=10, cfg=self.cfg, root=self.tmp)
        self.assertTrue(expired)
        self.assertFalse(mm.is_on(self.cfg, self.tmp))

    def test_maybe_expire_fresh_keeps_on(self):
        mm.turn_on("restart", self.cfg, self.tmp)
        expired = mm.maybe_expire(max_minutes=10, cfg=self.cfg, root=self.tmp)
        self.assertFalse(expired)
        self.assertTrue(mm.is_on(self.cfg, self.tmp))

    def test_load_maintenance_html_contains_title(self):
        html = mm.load_maintenance_html(ROOT)
        self.assertIn("系统正在更新中", html)
        self.assertTrue((ROOT / "static" / "maintenance.html").is_file())


class TestR1GitignoreAndDirty(unittest.TestCase):
    """R1 铁证：flag 不得使 git porcelain 判脏阻断一键更新。"""

    def test_repo_gitignore_lists_flag(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(
            "数据/maintenance.flag" in gi or "数据/*.flag" in gi,
            ".gitignore 必须包含 数据/maintenance.flag 或 数据/*.flag",
        )

    def test_git_check_ignore_hits_flag_path(self):
        """仓库根：git check-ignore 应对 数据/maintenance.flag 命中。"""
        r = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-v", "数据/maintenance.flag"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, f"check-ignore 应命中: stdout={r.stdout!r} stderr={r.stderr!r}")
        self.assertTrue(r.stdout.strip(), "check-ignore 输出应非空")

    def test_is_dirty_false_when_only_ignored_flag(self):
        """临时 git 仓：仅 ignored flag 时 _is_dirty 为假（与生产一致：ignore 生效）。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True, timeout=15)
            subprocess.run(
                ["git", "config", "user.email", "t@example.com"],
                cwd=tmp,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "t"],
                cwd=tmp,
                check=True,
                capture_output=True,
            )
            (tmp / "数据").mkdir()
            (tmp / ".gitignore").write_text("数据/maintenance.flag\n数据/*.flag\n", encoding="utf-8")
            (tmp / "README").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore", "README"], cwd=tmp, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, check=True, capture_output=True)
            flag = tmp / "数据" / "maintenance.flag"
            flag.write_text('{"reason":"update","ts":"2026-01-01T00:00:00","pid":1}\n', encoding="utf-8")
            # check-ignore
            ci = subprocess.run(
                ["git", "-C", str(tmp), "check-ignore", "-v", "数据/maintenance.flag"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(ci.returncode, 0, ci.stdout + ci.stderr)
            self.assertFalse(updater._is_dirty(tmp), "仅 ignored flag 时 _is_dirty 必须为 False")
            # 对照：未 ignore 的 untracked 会脏
            (tmp / "数据" / "leak.txt").write_text("x", encoding="utf-8")
            self.assertTrue(updater._is_dirty(tmp), "未 ignore 的 untracked 应判脏（禁止把 _is_dirty 改成忽略全部 untracked）")
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


class TestPullFailDoesNotTurnOn(unittest.TestCase):
    """R3：pull 失败路径禁止 turn_on（apply_update 本身不调用 turn_on）。"""

    def test_apply_update_source_has_no_turn_on(self):
        src = (ROOT / "src" / "updater.py").read_text(encoding="utf-8")
        # apply_update 函数体不应调用 turn_on；turn_on 在 request_restart 之前由路由/挂钩调用
        # 保守：整文件允许 import maintenance_mode，但 apply_update 返回 ok=False 路径无 turn_on
        import ast

        tree = ast.parse(src)
        apply_fn = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "apply_update":
                apply_fn = node
                break
        self.assertIsNotNone(apply_fn)
        apply_src = ast.get_source_segment(src, apply_fn) or ""
        self.assertNotIn("turn_on", apply_src)
        self.assertNotIn("maintenance_mode", apply_src)


class TestRequestRestartOrder(unittest.TestCase):
    """开启：request_restart 之前 turn_on（路由层）。"""

    def test_config_api_turns_on_before_restart(self):
        src = (ROOT / "src" / "routes" / "config_api.py").read_text(encoding="utf-8")
        # 成功路径：turn_on 出现在 request_restart 之前
        i_on = src.find("turn_on")
        i_rs = src.find("request_restart")
        self.assertGreaterEqual(i_on, 0, "config_api 须 turn_on 维护")
        self.assertGreaterEqual(i_rs, 0)
        self.assertLess(i_on, i_rs, "turn_on 必须在 request_restart 之前")

    def test_serve_source_turn_off_before_uvicorn(self):
        src = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        # serve 内成功路径 turn_off 在 uvicorn.run 之前
        i_off = src.find("turn_off")
        i_uv = src.find("uvicorn.run")
        self.assertGreaterEqual(i_off, 0)
        self.assertGreaterEqual(i_uv, 0)
        self.assertLess(i_off, i_uv)

    def test_start_script_turn_on_before_serve(self):
        sh = (ROOT / "deploy" / "linux" / "start_with_rollback.sh").read_text(encoding="utf-8")
        # 实际执行行：turn_on 后紧接 run.py --serve（注释里可能先出现 run.py --serve）
        i_on = sh.find("turn_on(")
        if i_on < 0:
            i_on = sh.find("from maintenance_mode import turn_on")
        i_serve = sh.rfind('"$PY" run.py --serve')
        if i_serve < 0:
            i_serve = sh.rfind("run.py --serve")
        self.assertGreaterEqual(i_on, 0, "start_with_rollback 须 turn_on")
        self.assertGreaterEqual(i_serve, 0)
        self.assertLess(i_on, i_serve, "turn_on 须在 run.py --serve 执行行之前")


class TestHtmlMaintenanceResponse(unittest.TestCase):
    """flag on：HTML 导航 503+维护文案+no-store；API 仍 JSON 不被 HTML 劫持。"""

    def setUp(self):
        import shutil

        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        (self.tmp / "static").mkdir()
        shutil.copy(ROOT / "static" / "maintenance.html", self.tmp / "static" / "maintenance.html")
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = "数据"
        self.cfg["db_path"] = "看板.db"
        self.cfg["zhiyun_auto_fetch"] = False
        self.cfg["server_host"] = "127.0.0.1"
        self.cfg["serve_static"] = False

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_html_on_flag_returns_maintenance(self):
        import server
        from fastapi.testclient import TestClient

        mm.turn_on("manual", self.cfg, self.tmp)
        app = server.create_app(self.cfg, root=self.tmp)
        c = TestClient(app)
        r = c.get("/", headers={"Accept": "text/html"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("系统正在更新中", r.text)
        cc = (r.headers.get("cache-control") or "").lower()
        self.assertIn("no-store", cc)
        # API 不返回维护 HTML
        r2 = c.get("/api/v1/health", headers={"Accept": "application/json"})
        self.assertNotIn("系统正在更新中", r2.text)
        self.assertIn("json", (r2.headers.get("content-type") or "").lower())

    def test_healthcheck_script_still_8018_v1(self):
        text = (ROOT / "deploy" / "healthcheck.sh").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:8018", text)
        self.assertIn("/api/v1/health", text)
        self.assertNotRegex(text, r"BASE=.*:80[\"\s]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
