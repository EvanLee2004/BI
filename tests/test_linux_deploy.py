#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书40：Linux 部署资产桩测（bash 脚本三态回滚 + cron 哨兵 + bash -n + 资产存在）。

真实 systemd / 系统 crontab / CIFS 挂载留部署机验（见交付报告「仅部署机可验」）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LINUX = ROOT / "deploy" / "linux"


class TestLinuxDeployAssets(unittest.TestCase):
    def test_assets_exist(self):
        # 五件套（任务书50·D.6）：service / 看门狗 / cron / nginx / README
        for name in (
            "kanban.service",
            "start_with_rollback.sh",
            "register_schedule.sh",
            "nginx-kanban.conf",
            "README.md",
        ):
            p = LINUX / name
            self.assertTrue(p.is_file(), f"缺 {p}")

    def test_bash_n_scripts(self):
        """语法级：bash -n 全部新脚本。"""
        if not shutil.which("bash"):
            self.skipTest("无 bash")
        for name in ("start_with_rollback.sh", "register_schedule.sh"):
            r = subprocess.run(["bash", "-n", str(LINUX / name)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"bash -n {name} 失败：{r.stderr}")

    def test_service_unit_has_restart_and_exec(self):
        text = (LINUX / "kanban.service").read_text(encoding="utf-8")
        self.assertIn("Restart=always", text)
        self.assertIn("RestartSec=3", text)
        self.assertIn("start_with_rollback.sh", text)
        self.assertIn("StartLimitBurst=5", text)
        # StartLimit* 须在 [Unit]（勿落 [Service]）
        unit = text.split("[Service]")[0]
        self.assertIn("StartLimitIntervalSec=120", unit)
        self.assertIn("StartLimitBurst=5", unit)

    def test_service_unit_prod_harden_lee_sandbox(self):
        """生产加固：User=lee（数据属主）+ 回环 env + D8 沙箱路径。"""
        text = (LINUX / "kanban.service").read_text(encoding="utf-8")
        self.assertIn("User=lee", text)
        self.assertIn("Group=lee", text)
        self.assertIn("KANBAN_SERVER_HOST=127.0.0.1", text)
        self.assertIn("KANBAN_SERVE_STATIC=0", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("PrivateTmp=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("ReadWritePaths=", text)
        self.assertIn("/opt/kanban/看板正式程序/数据", text)

    def test_nginx_security_headers_survive_cache_locations(self):
        """nginx 子 location 写 add_header 会冲掉 server 级头——入口与静态必须自带安全头。"""
        t = (LINUX / "nginx-kanban.conf").read_text(encoding="utf-8")
        self.assertIn("server_tokens off", t)
        self.assertIn("X-Content-Type-Options", t)
        self.assertIn("X-Frame-Options", t)
        self.assertIn("Referrer-Policy", t)
        # SPA 入口 location 内须重复（非仅 server 块）
        idx = t.find("location = /")
        self.assertGreater(idx, 0)
        chunk = t[idx : idx + 450]
        self.assertIn("X-Content-Type-Options", chunk)
        self.assertIn("Cache-Control", chunk)

    def test_ubuntu26_python_strategy_docs_and_scripts(self):
        """任务书50·D.6：26.04 + 系统 python3；脚本不写死 deadsnakes/python3.12 路径。"""
        readme = (LINUX / "README.md").read_text(encoding="utf-8")
        self.assertIn("26.04", readme)
        self.assertIn("0010", readme)
        for name in ("start_with_rollback.sh", "register_schedule.sh"):
            sh = (LINUX / name).read_text(encoding="utf-8")
            self.assertIn("python3", sh)
            self.assertNotIn("deadsnakes", sh)
            # 实际命令不得绑定小版本解释器路径（注释可提及策略）
            for line in sh.splitlines():
                s = line.strip()
                if s.startswith("#"):
                    continue
                self.assertNotIn("python3.12", s, f"{name} 非注释行写死小版本：{s}")
        madr = (ROOT / "docs" / "madr" / "0010_python_version_ubuntu26.md").read_text(encoding="utf-8")
        self.assertIn("SUPERSEDED", (ROOT / "docs" / "madr" / "0002_python_version_ubuntu22.md").read_text(encoding="utf-8"))
        self.assertIn("python3 -m venv", madr)
        self.assertIn("install-deps chromium", madr)
        hb = (ROOT / "docs" / "Ubuntu部署手册.md").read_text(encoding="utf-8")
        self.assertIn("Ubuntu 26.04", hb)
        self.assertIn("playwright install-deps chromium", hb)
        self.assertNotIn("ppa:deadsnakes", hb)


class TestStartWithRollbackThreeStates(unittest.TestCase):
    """包装脚本三态：42 重启 / 带标记崩溃回滚一次 / 无标记崩溃计数停。

    通过注入假 python（写 run.py 替身）+ 可写 git 仓桩测，不真起 HTTP 服务。
    """

    def _prep_repo(self, tmp: Path, run_script: str) -> Path:
        """tmp 下建迷你仓：假 run.py + 拷贝 start_with_rollback 逻辑用的结构。"""
        (tmp / "deploy" / "linux").mkdir(parents=True)
        # 用仓库真实脚本
        shutil.copy(LINUX / "start_with_rollback.sh", tmp / "deploy" / "linux" / "start_with_rollback.sh")
        (tmp / "run.py").write_text(run_script, encoding="utf-8")
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=tmp, check=True, capture_output=True)
        return tmp

    def test_exit_42_restarts_then_stop(self):
        """码 42：重启一次；第二次正常 0 退出循环外——用计数文件验证至少跑 2 次。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            # 第 1 次 exit 42，第 2 次 exit 0（看门狗遇 0 也会当非 42 累计；我们用 0 模拟「手动停」一次即 FAILS=1 继续…）
            # 为可观测：写 counter；第1次42，第2次写 done 并以 0 退出，但脚本对 0 会 FAILS+=1 再循环。
            # 更干净：第1次42，第2次写 .stop_marker 并以 42 以外且无 rollback——累计到5太慢。
            # 改为：假 run.py 第1次42，第2次创建 STOP 并 exit 1；同时把 MAX 逻辑无法改——改测「回滚」与「42 清零」两态。
            run_py = r"""
import sys
from pathlib import Path
c = Path("._start_count")
n = int(c.read_text()) if c.exists() else 0
n += 1
c.write_text(str(n))
if n == 1:
    sys.exit(42)
# 第二次：正常「启动成功」后立刻退出 0——看门狗会当异常累计；我们用环境变量把 MAX 行为改为：
# 直接写 done 并用 os._exit 无法打断外层。改为 exit 0 后脚本 sleep 再起——测 42 路径只要 count>=2。
sys.exit(0)
"""
            self._prep_repo(tmp, run_py)
            # 限制：改脚本拷贝版，注入 MAX_FAILS=1 使第2次非42即停
            sh = (tmp / "deploy" / "linux" / "start_with_rollback.sh").read_text(encoding="utf-8")
            sh = sh.replace("MAX_FAILS=5", "MAX_FAILS=1")
            # 缩短 sleep
            sh = sh.replace("sleep 2", "sleep 0").replace("sleep 3", "sleep 0")
            (tmp / "deploy" / "linux" / "start_with_rollback.sh").write_text(sh, encoding="utf-8")
            env = os.environ.copy()
            env["PYTHON"] = sys.executable
            env["LANG"] = "C.UTF-8"
            env["LC_ALL"] = "C.UTF-8"
            r = subprocess.run(
                ["bash", str(tmp / "deploy" / "linux" / "start_with_rollback.sh")],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=env,
            )
            count = int((tmp / "._start_count").read_text())
            self.assertGreaterEqual(count, 2, f"码42应触发重启，count={count}\n{r.stdout}\n{r.stderr}")
            self.assertTrue("更新后重启" in r.stdout or "42" in r.stdout, r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rollback_marker_resets_once(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            run_py = r"""
import sys
from pathlib import Path
c = Path("._start_count")
n = int(c.read_text()) if c.exists() else 0
n += 1
c.write_text(str(n))
# 始终非 42 崩溃；第1次有 .update_rollback 应被脚本删掉并 reset
sys.exit(1)
"""
            self._prep_repo(tmp, run_py)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True, check=True
            ).stdout.strip()
            # 造一个「更新后」commit，回滚点指向 base
            (tmp / "run.py").write_text(run_py + "\n# dirty\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=tmp, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "bad"], cwd=tmp, check=True, capture_output=True)
            (tmp / ".update_rollback").write_text(base + "\n", encoding="utf-8")

            sh = (tmp / "deploy" / "linux" / "start_with_rollback.sh").read_text(encoding="utf-8")
            sh = sh.replace("MAX_FAILS=5", "MAX_FAILS=1").replace("sleep 2", "sleep 0").replace("sleep 3", "sleep 0")
            (tmp / "deploy" / "linux" / "start_with_rollback.sh").write_text(sh, encoding="utf-8")
            env = os.environ.copy()
            env["PYTHON"] = sys.executable
            env["LANG"] = "C.UTF-8"
            env["LC_ALL"] = "C.UTF-8"
            r = subprocess.run(
                ["bash", str(tmp / "deploy" / "linux" / "start_with_rollback.sh")],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=env,
            )
            self.assertTrue("自动回滚" in r.stdout or "回滚" in r.stdout, r.stdout)
            self.assertFalse((tmp / ".update_rollback").exists(), "回滚后标记应删除")
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True, check=True
            ).stdout.strip()
            self.assertEqual(head, base, "应 reset 到回滚点")
            # 回滚后再崩（无标记）MAX_FAILS=1 → 退出
            self.assertNotEqual(r.returncode, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unmarked_crash_stops_after_max(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            run_py = "import sys\nsys.exit(7)\n"
            self._prep_repo(tmp, run_py)
            sh = (tmp / "deploy" / "linux" / "start_with_rollback.sh").read_text(encoding="utf-8")
            sh = sh.replace("MAX_FAILS=5", "MAX_FAILS=2").replace("sleep 2", "sleep 0").replace("sleep 3", "sleep 0")
            (tmp / "deploy" / "linux" / "start_with_rollback.sh").write_text(sh, encoding="utf-8")
            env = os.environ.copy()
            env["PYTHON"] = sys.executable
            env["LANG"] = "C.UTF-8"
            env["LC_ALL"] = "C.UTF-8"
            r = subprocess.run(
                ["bash", str(tmp / "deploy" / "linux" / "start_with_rollback.sh")],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=env,
            )
            self.assertIn("连续异常退出过多", r.stdout)
            self.assertNotEqual(r.returncode, 0)
            # 应跑满 MAX_FAILS 次
            self.assertEqual(r.stdout.count("第 "), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCronSentinel(unittest.TestCase):
    """cron 哨兵：生成条目数=时间点数；替换不吞别人的行。"""

    def test_strip_and_block_counts(self):
        import server

        other = "# my other job\n0 3 * * * /bin/true\n"
        stripped = server._strip_cron_sentinel(
            other + server.CRON_BEGIN + "\n0 9 * * * old\n" + server.CRON_END + "\n"
        )
        self.assertIn("my other job", stripped)
        self.assertIn("/bin/true", stripped)
        self.assertNotIn("old", stripped)
        self.assertNotIn(server.CRON_BEGIN, stripped)

        block = server._cron_block_for_times(["09:30", "12:00", "17:30"], root=ROOT)
        self.assertIn(server.CRON_BEGIN, block)
        self.assertIn(server.CRON_END, block)
        # 任务书60：哨兵段无刷新命令行（注释可提 --scheduled；禁止实际 cron 命令）
        cmd_lines = [ln for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        self.assertEqual(cmd_lines, [], msg=f"哨兵应无命令行，实际: {cmd_lines}")
        self.assertFalse(
            any((not ln.strip().startswith("#")) and "--scheduled" in ln for ln in block.splitlines())
        )
        # 时间点可出现在注释备忘中
        self.assertTrue("09:30" in block or "9:30" in block)

    def test_linux_sync_schedule_stubbed(self):
        import server

        calls = {"in": None, "out": None}

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""

            if cmd[:2] == ["crontab", "-l"]:
                R.stdout = "# keepme\n0 1 * * * /bin/echo keep\n" + server.CRON_BEGIN + "\nold\n" + server.CRON_END + "\n"
                return R()
            if cmd[:1] == ["crontab"] and cmd[1:] == ["-"]:
                calls["in"] = kwargs.get("input") or ""
                return R()
            return R()

        import subprocess as sp

        real = sp.run
        sp.run = fake_run
        try:
            note = server._linux_sync_schedule(["09:00", "18:00"], root=ROOT)
        finally:
            sp.run = real
        self.assertIn("cron", note.lower())
        self.assertTrue("ScheduleLoop" in note or "哨兵" in note or "同步" in note, note)
        text = calls["in"] or ""
        self.assertIn("keepme", text)
        self.assertIn("/bin/echo keep", text)
        # 任务书60：同步后哨兵内无非注释的 --scheduled 刷新命令
        self.assertFalse(
            any((not ln.strip().startswith("#")) and "--scheduled" in ln for ln in text.splitlines()),
            msg=text,
        )
        self.assertNotIn("old\n", text.replace(server.CRON_BEGIN, "").replace(server.CRON_END, ""))

    def test_register_script_uses_loaders(self):
        sh = (LINUX / "register_schedule.sh").read_text(encoding="utf-8")
        self.assertIn("loaders.load_config", sh)
        self.assertIn("BEGIN kanban-schedule", sh)
        self.assertNotIn("json.load(open('config.json'))", sh)


class TestFetchLedgerPosix(unittest.TestCase):
    """台账路径：POSIX 可达复制；不可达降级（CIFS 未挂载场景）。"""

    def test_posix_path_fetch_and_fallback(self):
        from ingest import fetch as fetch_mod

        tmp = Path(tempfile.mkdtemp())
        try:
            data = tmp / "数据"
            data.mkdir()
            # 假 config
            cfg = {
                "data_dir": "数据",
                "files": {"ledger": "收单台账.xlsx"},
                "ledger_share_path": str(tmp / "share" / "台账.xlsx"),
            }
            # 无共享、有本地
            (data / "收单台账.xlsx").write_bytes(b"PK\x03\x04local")
            r = fetch_mod.fetch_ledger(cfg, root=tmp)
            self.assertEqual(r["status"], "local_fallback")

            # 有共享
            (tmp / "share").mkdir()
            (tmp / "share" / "台账.xlsx").write_bytes(b"PK\x03\x04share")
            r2 = fetch_mod.fetch_ledger(cfg, root=tmp)
            self.assertEqual(r2["status"], "fetched")
            self.assertEqual((data / "收单台账.xlsx").read_bytes(), b"PK\x03\x04share")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
