#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""② 多次更新时间测试。跑：.venv/bin/python tests/test_schedule.py

守卫点（明昊 2026-07-12 拍板：单一每日时间 → 可添加/删除多个时间点，各到点各更新一次）：
- normalize_schedule_times：接受 list/单串/分隔串；HH:MM 校验；去重、升序；空/非法/超上限 → ValueError
- get_schedule_times：优先 schedule_times，缺失从旧 schedule_time 单值推导，坏值兜底 09:30
- sync_schedule：仅 Linux crontab；非 Linux no-op（任务书54 退役 Windows schtasks/.bat）
- /api/settings：GET 回 schedule_times；POST 列表→config 写 schedule_times + schedule_time(=最早)；
  兼容旧单值 schedule_time；列表含非法 → 400
- 控制台含多时间点 UI 锚点（schedTimes / schedAdd / saveSchedule）
"""

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders
import server  # noqa: E402


class TestNormalizeTimes(unittest.TestCase):
    def test_list_dedup_sort(self):
        self.assertEqual(server.normalize_schedule_times(["17:30", "09:30", "09:30"]), ["09:30", "17:30"])

    def test_single_and_separated_strings(self):
        self.assertEqual(server.normalize_schedule_times("09:30"), ["09:30"])
        self.assertEqual(server.normalize_schedule_times("09:30、12:00,17:30"), ["09:30", "12:00", "17:30"])

    def test_invalid_time_raises(self):
        for bad in (["25:00"], ["9点半"], ["9:5"], ["24:00"], ["12:60"]):
            with self.assertRaises(ValueError):
                server.normalize_schedule_times(bad)

    def test_empty_raises(self):
        for empty in ([], "", ["  "], None):
            with self.assertRaises(ValueError):
                server.normalize_schedule_times(empty)

    def test_too_many_raises(self):
        many = [f"{h:02d}:00" for h in range(server.MAX_SCHEDULE_TIMES + 1)]
        with self.assertRaises(ValueError):
            server.normalize_schedule_times(many)
        # 刚好上限个 → 通过
        ok = [f"{h:02d}:00" for h in range(server.MAX_SCHEDULE_TIMES)]
        self.assertEqual(len(server.normalize_schedule_times(ok)), server.MAX_SCHEDULE_TIMES)


class TestGetTimes(unittest.TestCase):
    def test_prefers_schedule_times(self):
        self.assertEqual(
            server.get_schedule_times({"schedule_times": ["12:00", "09:30"], "schedule_time": "08:00"}),
            ["09:30", "12:00"],
        )

    def test_falls_back_to_single(self):
        self.assertEqual(server.get_schedule_times({"schedule_time": "08:15"}), ["08:15"])

    def test_bad_values_default(self):
        self.assertEqual(server.get_schedule_times({}), ["09:30"])
        self.assertEqual(server.get_schedule_times({"schedule_times": ["坏"], "schedule_time": "坏"}), ["09:30"])


class TestSyncScheduleLinuxOnly(unittest.TestCase):
    """任务书54·D：无 win32/schtasks 辅助；非 Linux 返回 cron 提示。"""

    def test_no_win_helpers(self):
        self.assertFalse(hasattr(server, "_win_task_names"))
        self.assertFalse(hasattr(server, "_win_sync_schedule"))
        self.assertFalse(hasattr(server, "SCHTASK_NAME"))
        src = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        # 可执行路径不得再调 Windows 计划任务（注释允许提「已退役」）
        self.assertNotIn('["schtasks"', src)
        self.assertNotIn("subprocess.run([\"schtasks\"", src)
        self.assertNotIn('plat == "win32"', src)
        self.assertNotIn("def _win_sync_schedule", src)

    def test_sync_schedule_non_linux_message(self):
        import sys

        if sys.platform.startswith("linux"):
            self.skipTest("本机是 Linux，测 no-op 需非 linux")
        msg = server.sync_schedule(["09:30", "17:30"])
        self.assertIn("cron", msg.lower())
        self.assertIn("09:30", msg)


class TestSettingsApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        self.root = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        shutil.copy2(ROOT / "config.json", self.root / "config.json")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "<html>ADMIN</html>"
        self.app = server.create_app(self.cfg, root=self.root)
        self.client = TestClient(self.app, follow_redirects=False)
        r = self.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        self.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    def _raw(self):
        return json.loads((self.root / "config.json").read_text(encoding="utf-8"))

    def _override(self):
        p = self.root / "数据" / loaders.LOCAL_CONFIG_NAME
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def test_get_returns_times_list(self):
        d = self.client.get("/api/settings", headers=self.hdr).json()
        self.assertIn("schedule_times", d)
        self.assertIsInstance(d["schedule_times"], list)
        self.assertTrue(d["schedule_times"])

    def test_post_multi_times(self):
        before_cfg = self._raw()  # 存下 config.json 原样
        r = self.client.post("/api/settings", headers=self.hdr, json={"schedule_times": ["17:30", "09:30", "12:00"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["schedule_times"], ["09:30", "12:00", "17:30"])
        # F-01 修复：写覆盖文件、旧 schedule_time=最早时间点；**config.json 一字不动**
        ov = self._override()
        self.assertEqual(ov["schedule_times"], ["09:30", "12:00", "17:30"])
        self.assertEqual(ov["schedule_time"], "09:30")
        self.assertEqual(self._raw(), before_cfg)  # config.json 未被程序改动（git 工作区保持干净）
        # 内存 cfg 已更新
        self.assertEqual(self.cfg["schedule_times"], ["09:30", "12:00", "17:30"])
        self.assertEqual(self.cfg["schedule_time"], "09:30")

    def test_legacy_single_still_works(self):
        before_cfg = self._raw()
        r = self.client.post("/api/settings", headers=self.hdr, json={"schedule_time": "08:45"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["schedule_times"], ["08:45"])
        ov = self._override()
        self.assertEqual(ov["schedule_time"], "08:45")
        self.assertEqual(ov["schedule_times"], ["08:45"])
        self.assertEqual(self._raw(), before_cfg)  # config.json 未变

    def test_config_json_never_dirtied_by_settings(self):
        """F-01 守卫：多次改各类设置后，config.json 逐字节不变（部署机 git 工作区不脏→一键更新可用）。"""
        before = (self.root / "config.json").read_text(encoding="utf-8")
        for body in (
            {"schedule_times": ["10:00"]},
            {"backup_keep_days": 200},
            {"ledger_share_path": r"\\srv\share\台账.xlsx"},
            {"zhiyun_auto_fetch": True},
        ):
            self.assertEqual(self.client.post("/api/settings", headers=self.hdr, json=body).status_code, 200, body)
        self.assertEqual((self.root / "config.json").read_text(encoding="utf-8"), before)
        # 但效果都落进了覆盖文件
        ov = self._override()
        self.assertEqual(ov["backup_keep_days"], 200)
        self.assertEqual(ov["ledger_share_path"], r"\\srv\share\台账.xlsx")

    def test_ledger_path_via_settings(self):
        """台账路径经设置页填→GET 回显、落覆盖文件、load_config 合并生效。"""
        p = r"\\财务服务器\共享\收单台账.xlsx"
        self.client.post("/api/settings", headers=self.hdr, json={"ledger_share_path": p})
        self.assertEqual(self.client.get("/api/settings", headers=self.hdr).json()["ledger_share_path"], p)
        self.assertEqual(loaders.load_config(self.root)["ledger_share_path"], p)  # 合并后生效

    def test_invalid_in_list_400(self):
        for bad in ({"schedule_times": ["09:30", "25:00"]}, {"schedule_times": []}, {"schedule_times": ["9点"]}):
            r = self.client.post("/api/settings", headers=self.hdr, json=bad)
            self.assertEqual(r.status_code, 400, f"{bad} 应 400")

    def test_audit_records_time_change(self):
        self.client.post("/api/settings", headers=self.hdr, json={"schedule_times": ["09:30", "18:00"]})
        d = self.client.get("/api/config_changes?category=设置", headers=self.hdr).json()
        joined = json.dumps(d.get("changes", []), ensure_ascii=False)
        self.assertIn("更新时间", joined)
        self.assertIn("18:00", joined)

    def test_console_has_multi_time_ui(self):
        html = server.admin_ui_source()
        self.assertIn("scheduleTimes", html)
        self.assertIn("09:30", html)


class TestRegisterScheduleScriptReadsMergedConfig(unittest.TestCase):
    """守卫 F-02：register_schedule.sh 时间点必须来自合并配置（loaders.load_config）。
    管理端保存的 schedule_times 只写 数据/本地配置.json 覆盖层（铁律19）。"""

    def _merged_times(self, root):
        c = loaders.load_config(root=root)
        return c.get("schedule_times") or [c.get("schedule_time") or "09:30"]

    def test_overlay_times_win_over_factory(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy(ROOT / "config.json", tmp / "config.json")
            cfg0 = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
            ov = loaders._local_config_path(tmp, cfg0)
            ov.parent.mkdir(parents=True, exist_ok=True)
            ov.write_text(
                json.dumps({"schedule_times": ["09:00", "12:00", "17:00"]}, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(self._merged_times(tmp), ["09:00", "12:00", "17:00"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_overlay_falls_back_to_factory(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy(ROOT / "config.json", tmp / "config.json")
            ts = self._merged_times(tmp)
            self.assertTrue(ts, "至少兜底 09:30")
            for t in ts:
                self.assertRegex(t, r"^\d{2}:\d{2}$")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_linux_script_uses_loaders_not_raw_config(self):
        """锁死 register_schedule.sh：必须经 loaders.load_config。"""
        sh = (ROOT / "deploy" / "linux" / "register_schedule.sh").read_text(encoding="utf-8")
        self.assertIn("loaders.load_config", sh)
        self.assertNotIn("json.load(open('config.json'))", sh)
        self.assertNotIn("schtasks", sh)

    def test_register_script_no_scheduled_command(self):
        """任务书60：register_schedule.sh 不得注册 run.py --scheduled 命令行。"""
        sh = (ROOT / "deploy" / "linux" / "register_schedule.sh").read_text(encoding="utf-8")
        # 允许注释提及 --scheduled；禁止拼出 crontab 命令
        bad = []
        for ln in sh.splitlines():
            s = ln.strip()
            if s.startswith("#"):
                continue
            if "--scheduled" in s and "run.py" in s:
                bad.append(ln)
            # 旧脚本 for 循环拼 cron 行的特征
            if 'LINES="${LINES}' in s or "LINES=${LINES}" in s:
                bad.append(ln)
        self.assertEqual(bad, [], msg=f"不应再注册刷新 cron: {bad}")
        self.assertIn("ScheduleLoop", sh)


class TestScheduleLoop(unittest.TestCase):
    """任务书60：进程内 ScheduleLoop（假时钟 + mock，无真等）。"""

    def test_t60_1_fires_once_per_minute(self):
        """T-60-1：命中 schedule_times → 调 start_refresh_async(trigger=schedule)；同分钟不二次。"""
        import schedule_loop as sl

        calls = []

        def mock_start(cfg, root, trigger="manual"):
            calls.append({"cfg": cfg, "root": root, "trigger": trigger})
            return True

        cfg = {"_mark": "same-cfg-object"}
        # 2026-07-20 09:30 本地
        fixed = time.struct_time((2026, 7, 20, 9, 30, 0, 0, 201, -1))
        loop = sl.ScheduleLoop(
            cfg,
            None,
            mock_start,
            clock=lambda: fixed,
            load_times_fn=lambda: ["09:30", "17:30"],
        )
        self.assertTrue(loop.tick())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["trigger"], "schedule")
        self.assertIs(calls[0]["cfg"], cfg)  # 同源 cfg 对象
        # 同分钟再 tick → 不重复
        self.assertFalse(loop.tick())
        self.assertEqual(len(calls), 1)

    def test_t60_2_busy_not_registered(self):
        """T-60-2：返回 False（锁占用）不登记去重键，下 tick 可重试。"""
        import schedule_loop as sl

        calls = []
        results = [False, True]

        def mock_start(cfg, root, trigger="manual"):
            calls.append(trigger)
            return results.pop(0)

        fixed = time.struct_time((2026, 7, 20, 12, 0, 0, 0, 201, -1))
        loop = sl.ScheduleLoop(
            {},
            None,
            mock_start,
            clock=lambda: fixed,
            load_times_fn=lambda: ["12:00"],
        )
        self.assertFalse(loop.tick())
        self.assertEqual(calls, ["schedule"])
        self.assertEqual(loop.fired, set())
        # 重试成功并登记
        self.assertTrue(loop.tick())
        self.assertEqual(calls, ["schedule", "schedule"])
        self.assertEqual(loop.fired, {("2026-07-20", "12:00")})

    def test_t60_2b_create_app_no_schedule_thread(self):
        """T-60-2b：create_app 后无 schedule loop 线程；启动仅在 serve()。"""
        import schedule_loop as sl
        import loaders

        cfg = loaders.load_config()
        app = server.create_app(cfg, root=ROOT)
        self.assertIsNotNone(app)
        self.assertFalse(sl.schedule_loop_thread_running())
        src = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        self.assertIn("start_schedule_loop", src)
        # 唯一启动应在 serve() 体内（create_app 禁止）
        create_idx = src.find("def create_app")
        serve_idx = src.find("def serve")
        self.assertGreater(serve_idx, create_idx)
        create_body = src[create_idx:serve_idx]
        serve_body = src[serve_idx:]
        self.assertNotIn("start_schedule_loop", create_body)
        self.assertIn("start_schedule_loop", serve_body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
