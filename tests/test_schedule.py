#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""② 多次更新时间测试。跑：.venv/bin/python tests/test_schedule.py

守卫点（明昊 2026-07-12 拍板：单一每日时间 → 可添加/删除多个时间点，各到点各更新一次）：
- normalize_schedule_times：接受 list/单串/分隔串；HH:MM 校验；去重、升序；空/非法/超上限 → ValueError
- get_schedule_times：优先 schedule_times，缺失从旧 schedule_time 单值推导，坏值兜底 09:30
- _win_task_names：第 1 个=主名（与 .bat 一致），其余 _2.._n
- /api/settings：GET 回 schedule_times；POST 列表→config 写 schedule_times + schedule_time(=最早)；
  兼容旧单值 schedule_time；列表含非法 → 400
- 控制台含多时间点 UI 锚点（schedTimes / schedAdd / saveSchedule）
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders, server  # noqa: E402


class TestNormalizeTimes(unittest.TestCase):
    def test_list_dedup_sort(self):
        self.assertEqual(server.normalize_schedule_times(["17:30", "09:30", "09:30"]),
                         ["09:30", "17:30"])

    def test_single_and_separated_strings(self):
        self.assertEqual(server.normalize_schedule_times("09:30"), ["09:30"])
        self.assertEqual(server.normalize_schedule_times("09:30、12:00,17:30"),
                         ["09:30", "12:00", "17:30"])

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
        self.assertEqual(server.get_schedule_times(
            {"schedule_times": ["12:00", "09:30"], "schedule_time": "08:00"}),
            ["09:30", "12:00"])

    def test_falls_back_to_single(self):
        self.assertEqual(server.get_schedule_times({"schedule_time": "08:15"}), ["08:15"])

    def test_bad_values_default(self):
        self.assertEqual(server.get_schedule_times({}), ["09:30"])
        self.assertEqual(server.get_schedule_times({"schedule_times": ["坏"], "schedule_time": "坏"}),
                         ["09:30"])


class TestTaskNames(unittest.TestCase):
    def test_naming(self):
        self.assertEqual(server._win_task_names(1), [server.SCHTASK_NAME])
        self.assertEqual(server._win_task_names(3),
                         [server.SCHTASK_NAME, f"{server.SCHTASK_NAME}_2", f"{server.SCHTASK_NAME}_3"])


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

    def test_get_returns_times_list(self):
        d = self.client.get("/api/settings", headers=self.hdr).json()
        self.assertIn("schedule_times", d)
        self.assertIsInstance(d["schedule_times"], list)
        self.assertTrue(d["schedule_times"])

    def test_post_multi_times(self):
        r = self.client.post("/api/settings", headers=self.hdr,
                             json={"schedule_times": ["17:30", "09:30", "12:00"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["schedule_times"], ["09:30", "12:00", "17:30"])
        # config + cfg：schedule_times 写入，旧 schedule_time=最早时间点
        raw = self._raw()
        self.assertEqual(raw["schedule_times"], ["09:30", "12:00", "17:30"])
        self.assertEqual(raw["schedule_time"], "09:30")
        self.assertEqual(self.cfg["schedule_times"], ["09:30", "12:00", "17:30"])
        self.assertEqual(self.cfg["schedule_time"], "09:30")

    def test_legacy_single_still_works(self):
        r = self.client.post("/api/settings", headers=self.hdr, json={"schedule_time": "08:45"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["schedule_times"], ["08:45"])
        raw = self._raw()
        self.assertEqual(raw["schedule_time"], "08:45")
        self.assertEqual(raw["schedule_times"], ["08:45"])

    def test_invalid_in_list_400(self):
        for bad in ({"schedule_times": ["09:30", "25:00"]}, {"schedule_times": []},
                    {"schedule_times": ["9点"]}):
            r = self.client.post("/api/settings", headers=self.hdr, json=bad)
            self.assertEqual(r.status_code, 400, f"{bad} 应 400")

    def test_audit_records_time_change(self):
        self.client.post("/api/settings", headers=self.hdr,
                         json={"schedule_times": ["09:30", "18:00"]})
        d = self.client.get("/api/config_changes?category=设置", headers=self.hdr).json()
        joined = json.dumps(d.get("changes", []), ensure_ascii=False)
        self.assertIn("更新时间", joined)
        self.assertIn("18:00", joined)

    def test_console_has_multi_time_ui(self):
        html = server._ADMIN_CONSOLE
        for anchor in ("schedTimes", "schedAdd", "saveSchedule", "添加时间点"):
            self.assertIn(anchor, html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
