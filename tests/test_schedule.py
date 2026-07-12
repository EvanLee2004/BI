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
        r = self.client.post("/api/settings", headers=self.hdr,
                             json={"schedule_times": ["17:30", "09:30", "12:00"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["schedule_times"], ["09:30", "12:00", "17:30"])
        # F-01 修复：写覆盖文件、旧 schedule_time=最早时间点；**config.json 一字不动**
        ov = self._override()
        self.assertEqual(ov["schedule_times"], ["09:30", "12:00", "17:30"])
        self.assertEqual(ov["schedule_time"], "09:30")
        self.assertEqual(self._raw(), before_cfg)   # config.json 未被程序改动（git 工作区保持干净）
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
        self.assertEqual(self._raw(), before_cfg)   # config.json 未变

    def test_config_json_never_dirtied_by_settings(self):
        """F-01 守卫：多次改各类设置后，config.json 逐字节不变（部署机 git 工作区不脏→一键更新可用）。"""
        before = (self.root / "config.json").read_text(encoding="utf-8")
        for body in ({"schedule_times": ["10:00"]}, {"backup_keep_days": 200},
                     {"ledger_share_path": r"\\srv\share\台账.xlsx"}, {"zhiyun_auto_fetch": True}):
            self.assertEqual(self.client.post("/api/settings", headers=self.hdr, json=body).status_code,
                             200, body)
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
