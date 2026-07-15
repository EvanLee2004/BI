#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""④ 一键更新 + 看门狗测试。跑：.venv/bin/python tests/test_update.py

守卫点（明昊 2026-07-12 拍板：版本检测 git fetch 比对 + 按钮 git pull --ff-only + 看门狗重启 + 护栏）：
- updater.check_update（真实临时 git 仓库）：已最新/落后可更新/脏工作区拒绝/分叉拒绝/非仓库不支持
- updater.apply_update：落后+干净→ff 拉取成功 HEAD 前进；脏/分叉/已最新→拒绝不拉
- RESTART_EXIT_CODE=42（须与 看门狗启动.bat 一致）；request_restart 不在测试里真跑
- `/api/update/check`、`/api/update/apply`：仅管理员会话；apply 成功→触发重启+C3 留痕「更新」，失败不重启
- 控制台含一键更新 UI 锚点（checkUpdate/applyUpdate/vuAvail）
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders
import server
import updater  # noqa: E402

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _run(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None, capture_output=True, text=True, env=_ENV)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def _commit(cwd, fname, content, msg):
    (Path(cwd) / fname).write_text(content, encoding="utf-8")
    _run("add", "-A", cwd=cwd)
    _run("commit", "-m", msg, cwd=cwd)


@unittest.skipUnless(shutil.which("git"), "无 git 可执行文件")
class TestUpdaterGit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.origin = self.tmp / "origin.git"
        self.local = self.tmp / "local"
        self.helper = self.tmp / "helper"
        _run("init", "--bare", str(self.origin))
        _run("clone", str(self.origin), str(self.local))
        _run("checkout", "-b", "main", cwd=self.local)
        _commit(self.local, "f.txt", "v1", "init")
        _run("push", "-u", "origin", "main", cwd=self.local)
        _run("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.origin)  # 裸库默认分支=main
        _run("clone", str(self.origin), str(self.helper))
        _run("checkout", "main", cwd=self.helper)  # 确保 helper 在 main

    def _origin_advance(self, msg="feat: 新增功能A"):
        """helper 提交并推到 origin，让 local 落后。"""
        _commit(self.helper, "f.txt", "v2\n" + msg, msg)
        _run("push", "origin", "main", cwd=self.helper)

    def test_up_to_date(self):
        d = updater.check_update(self.local)
        self.assertTrue(d["supported"])
        self.assertFalse(d["available"])
        self.assertEqual(d["behind"], 0)
        self.assertIn("最新", d["reason"])

    def test_behind_can_update_then_apply(self):
        self._origin_advance("feat: 加了一个大功能")
        d = updater.check_update(self.local)
        self.assertTrue(d["available"])
        self.assertEqual(d["behind"], 1)
        self.assertEqual(d["ahead"], 0)
        self.assertTrue(d["can_update"])
        self.assertTrue(any("大功能" in s for s in d["log"]))
        before = _run("rev-parse", "HEAD", cwd=self.local)
        res = updater.apply_update(self.local)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["pulled"], 1)
        after = _run("rev-parse", "HEAD", cwd=self.local)
        self.assertNotEqual(before, after)
        # 拉完就是最新
        self.assertFalse(updater.check_update(self.local)["available"])

    def test_dirty_refuses(self):
        self._origin_advance()
        (self.local / "scratch.txt").write_text("未提交改动", encoding="utf-8")
        d = updater.check_update(self.local)
        self.assertTrue(d["available"])  # 确实有新版本
        self.assertTrue(d["dirty"])
        self.assertFalse(d["can_update"])  # 但脏工作区不给自动更新
        res = updater.apply_update(self.local)
        self.assertFalse(res["ok"])
        self.assertIn("未提交", res["reason"])

    def test_diverged_refuses(self):
        self._origin_advance()
        _commit(self.local, "mine.txt", "本地独有", "本地未推送提交")  # local 也 ahead
        d = updater.check_update(self.local)
        self.assertEqual(d["ahead"], 1)
        self.assertGreaterEqual(d["behind"], 1)
        self.assertFalse(d["can_update"])
        res = updater.apply_update(self.local)
        self.assertFalse(res["ok"])
        self.assertIn("分叉", res["reason"])

    def test_not_a_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        d = updater.check_update(plain, do_fetch=False)
        self.assertFalse(d["supported"])
        self.assertFalse(d["available"])
        self.assertFalse(updater.apply_update(plain)["ok"])

    def test_custom_remote_gitee(self):
        """对标非默认远端（模拟部署机 update_remote=gitee）：另一个远端领先时能检测/拉取。"""
        gitee = self.tmp / "gitee.git"
        _run("init", "--bare", str(gitee))
        _run("remote", "add", "gitee", str(gitee), cwd=self.local)
        _run("push", "gitee", "main", cwd=self.local)  # 先推上去，此时齐平
        _run("symbolic-ref", "HEAD", "refs/heads/main", cwd=gitee)
        g2 = self.tmp / "g2"
        _run("clone", str(gitee), str(g2))
        _run("checkout", "main", cwd=g2)
        _commit(g2, "f.txt", "v2", "feat: gitee 专属更新")
        _run("push", "origin", "main", cwd=g2)  # g2 的 origin=gitee，推进 gitee
        # 对标 origin(=GitHub 那个 bare)=齐平；对标 gitee=落后可更新
        self.assertFalse(updater.check_update(self.local, remote="origin")["available"])
        d = updater.check_update(self.local, remote="gitee")
        self.assertTrue(d["available"])
        self.assertEqual(d["remote"], "gitee")
        self.assertTrue(any("gitee 专属" in s for s in d["log"]))
        res = updater.apply_update(self.local, remote="gitee")
        self.assertTrue(res["ok"], res)

    # ---------- 依赖自动同步（拉取引入新 pip 包时避免重启缺包崩溃） ----------
    def _stub_pip(self, rc, out="", err=""):
        """替换 updater._run_pip，记录是否被调用；返回 (calls_list, restore_fn)。"""
        calls = []
        orig = updater._run_pip

        def fake(root):
            calls.append(str(root))
            return rc, out, err

        updater._run_pip = fake
        self.addCleanup(lambda: setattr(updater, "_run_pip", orig))
        return calls

    def test_deps_changed_installs_and_marks_rollback(self):
        # helper 新增 requirements.txt（依赖变化）并推
        _commit(self.helper, "requirements.txt", "openpyxl==3.1.5\nnewpkg==1.0\n", "deps: 加 newpkg")
        _run("push", "origin", "main", cwd=self.helper)
        before = _run("rev-parse", "--short", "HEAD", cwd=self.local)
        calls = self._stub_pip(0)  # 装成功
        res = updater.apply_update(self.local)
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["deps"]["changed"])
        self.assertEqual(len(calls), 1)  # requirements 变了→装了一次
        # 成功→写了回滚点标记，内容=更新前 commit
        self.assertEqual(updater.read_rollback_marker(self.local), before)

    def test_deps_install_fail_rolls_back_and_no_restart(self):
        _commit(self.helper, "requirements.txt", "openpyxl==3.1.5\nbadpkg==9.9\n", "deps: 加装不上的包")
        _run("push", "origin", "main", cwd=self.helper)
        before = _run("rev-parse", "HEAD", cwd=self.local)
        self._stub_pip(1, err="ERROR: No matching distribution for badpkg==9.9")
        res = updater.apply_update(self.local)
        self.assertFalse(res["ok"])  # 装失败=更新失败
        self.assertTrue(res["rolled_back"])  # 已回滚这次拉取
        self.assertIn("回滚", res["reason"])
        self.assertEqual(_run("rev-parse", "HEAD", cwd=self.local), before)  # HEAD 退回更新前
        self.assertEqual(updater.read_rollback_marker(self.local), "")  # 失败不留回滚点

    def test_deps_unchanged_skips_pip(self):
        self._origin_advance("feat: 只改代码不动依赖")  # 只改 f.txt，无 requirements.txt
        calls = self._stub_pip(0)
        res = updater.apply_update(self.local)
        self.assertTrue(res["ok"], res)
        self.assertFalse(res["deps"]["changed"])
        self.assertEqual(len(calls), 0)  # 依赖没变→不装

    def test_rollback_marker_roundtrip(self):
        self.assertEqual(updater.read_rollback_marker(self.local), "")
        updater.write_rollback_marker(self.local, "abc1234")
        self.assertEqual(updater.read_rollback_marker(self.local), "abc1234")
        self.assertTrue(updater.rollback_marker_path(self.local).exists())
        updater.clear_rollback_marker(self.local)
        self.assertEqual(updater.read_rollback_marker(self.local), "")
        self.assertFalse(updater.rollback_marker_path(self.local).exists())


class TestUpdateConstants(unittest.TestCase):
    def test_restart_code(self):
        self.assertEqual(updater.RESTART_EXIT_CODE, 42)
        # 看门狗脚本里也必须是 42
        bat = (ROOT / "看门狗启动.bat").read_text(encoding="utf-8")
        self.assertIn("42", bat)
        self.assertIn("run.py --serve", bat)


class TestUpdateApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        import accounts

        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "权限": "管理员", "密码": server.DEFAULT_PW, "显示名": "管"},
                {"账号": "overall", "权限": "整体", "密码": server.DEFAULT_VIEW_PW, "显示名": "整"},
            ],
        )
        server._state["user_html"] = "<html>U</html>"
        server._state["admin_html"] = "<html>A</html>"
        self.app = server.create_app(self.cfg, root=self.tmp)
        self.client = TestClient(self.app, follow_redirects=False)
        r = self.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        self.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}
        # 打桩：不真跑 git / 不真重启
        self._orig = (updater.check_update, updater.apply_update, updater.request_restart)
        self.restarted = []
        updater.request_restart = lambda delay=1.0: self.restarted.append(True)

    def tearDown(self):
        updater.check_update, updater.apply_update, updater.request_restart = self._orig

    def test_check_requires_admin(self):
        anon = self._anon()
        self.assertEqual(anon.get("/api/update/check").status_code, 401)
        self.assertEqual(anon.post("/api/update/apply").status_code, 401)

    def _anon(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_check_passthrough(self):
        seen = {}

        def _stub(root=None, remote="origin", do_fetch=True):
            seen["remote"] = remote
            return {"supported": True, "available": True, "behind": 2, "can_update": True}

        updater.check_update = _stub
        d = self.client.get("/api/update/check", headers=self.hdr).json()
        self.assertTrue(d["available"])
        self.assertEqual(d["behind"], 2)
        self.assertEqual(seen["remote"], "origin")  # 默认对标 origin（config update_remote）

    def test_apply_ok_restarts_and_audits(self):
        updater.apply_update = lambda root=None, remote="origin": {"ok": True, "pulled": 3, "from": "aaa", "to": "bbb"}
        d = self.client.post("/api/update/apply", headers=self.hdr).json()
        self.assertTrue(d["ok"])
        self.assertTrue(d.get("restarting"))
        self.assertTrue(self.restarted)  # 触发了重启
        au = self.client.get("/api/config_changes?category=更新", headers=self.hdr).json()
        joined = str(au.get("changes", []))
        self.assertIn("一键更新", joined)
        self.assertIn("bbb", joined)

    def test_apply_refused_no_restart(self):
        updater.apply_update = lambda root=None, remote="origin": {"ok": False, "reason": "已是最新版本"}
        d = self.client.post("/api/update/apply", headers=self.hdr).json()
        self.assertFalse(d["ok"])
        self.assertNotIn("restarting", d)
        self.assertFalse(self.restarted)

    def test_console_has_update_ui(self):
        html = server.admin_ui_source()
        for anchor in ("checkUpdate", "applyUpdate", "vuAvail", "检查更新"):
            self.assertIn(anchor, html)


class TestRunPipMirror(unittest.TestCase):
    """_run_pip 走国内 pip 镜像（config.pip_mirror）：非空加 -i，空/缺失不加。mock subprocess.run 记录参数。"""

    def _call_with_cfg(self, cfg_json: str | None):
        """临时 root：requirements.txt + 可选 config.json；mock subprocess.run 抓命令行。"""
        tmp = tempfile.mkdtemp(prefix="piptest_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (Path(tmp) / "requirements.txt").write_text("fastapi==0.1\n", encoding="utf-8")
        if cfg_json is not None:
            (Path(tmp) / "config.json").write_text(cfg_json, encoding="utf-8")
        captured = {}

        class _R:
            returncode, stdout, stderr = 0, "ok", ""

        orig = updater.subprocess.run

        def fake(cmd, **kw):
            captured["cmd"] = list(cmd)
            return _R()

        updater.subprocess.run = fake
        self.addCleanup(lambda: setattr(updater.subprocess, "run", orig))
        rc, out, err = updater._run_pip(tmp)
        self.assertEqual(rc, 0)
        return captured["cmd"]

    def test_mirror_added_when_configured(self):
        cmd = self._call_with_cfg('{"data_dir": "数据", "pip_mirror": "https://pypi.tuna.tsinghua.edu.cn/simple"}')
        self.assertIn("-i", cmd)
        self.assertEqual(cmd[cmd.index("-i") + 1], "https://pypi.tuna.tsinghua.edu.cn/simple")
        self.assertEqual(cmd[:4], [sys.executable, "-m", "pip", "install"])

    def test_no_mirror_when_blank(self):
        cmd = self._call_with_cfg('{"data_dir": "数据", "pip_mirror": ""}')
        self.assertNotIn("-i", cmd)

    def test_no_mirror_when_field_missing(self):
        cmd = self._call_with_cfg('{"data_dir": "数据"}')
        self.assertNotIn("-i", cmd)

    def test_no_mirror_when_config_missing(self):
        # root 没有 config.json（如测试临时 git 仓库）→ 读配置失败不挡装依赖，退回 pip 默认源
        cmd = self._call_with_cfg(None)
        self.assertNotIn("-i", cmd)

    def test_factory_default_is_tsinghua(self):
        cfg = loaders.load_config(ROOT)
        self.assertEqual(cfg.get("pip_mirror"), "https://pypi.tuna.tsinghua.edu.cn/simple")


if __name__ == "__main__":
    unittest.main(verbosity=2)
