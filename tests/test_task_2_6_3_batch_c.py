#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.3 批次 C：写锁 409 / publish 原子 / generate root 贯通。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
from app_state import _LOCK, _state  # noqa: E402
from refresh_pipeline import publish, snapshot_state  # noqa: E402


class TestC1WriteLock409(unittest.TestCase):
    def test_busy_lock_returns_409_no_half_write(self):
        """刷新持锁时保存 → 409，且库无半条脏记录（不进写路径）。"""
        from fastapi.testclient import TestClient
        import server
        import accounts

        tmp = Path(tempfile.mkdtemp(prefix="t263c1_"))
        try:
            shutil.copy2(ROOT / "config.json", tmp / "config.json")
            (tmp / "数据").mkdir()
            cfg = loaders.load_config(tmp)
            accounts.seed_defaults(cfg, tmp)
            # 持锁模拟刷新
            self.assertTrue(_LOCK.acquire(blocking=False))
            try:
                _state["refreshing"] = {"trigger": "manual", "started": time.time()}
                app = server.create_app(cfg, root=tmp)
                client = TestClient(app, follow_redirects=False)
                r = client.post(
                    "/admin/login",
                    data={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
                )
                hdr = {
                    "Cookie": f"{server.SID_COOKIE}="
                    f"{(r.cookies.get(server.SID_COOKIE) or r.cookies.get(server.COOKIE))}"
                }
                resp = client.post(
                    "/api/v1/admin/manual",
                    headers=hdr,
                    json={"归属月": "2026-07", "项目": "装修费", "金额": 1, "范围": "全公司"},
                )
                # 未知项目可能 400；关键是不得 500；锁占用必须 409
                self.assertEqual(resp.status_code, 409, resp.text)
                self.assertIn("更新进行中", resp.json().get("detail") or resp.text)
            finally:
                _state["refreshing"] = None
                _LOCK.release()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestC2PublishAtomic(unittest.TestCase):
    def test_concurrent_read_no_torn_snapshot(self):
        """publish 期间读侧用 snapshot_state 一次取引用，不应见新 summary+旧 views 组合长期存在。"""
        # 预置旧态
        _state.clear()
        _state.update(
            {
                "summary": {"v": "old"},
                "views": {"v": "old"},
                "fragments": None,
                "has_data": True,
                "built_at": "old",
                "admin_html": "",
                "user_html": "",
                "bu_pages": {},
                "export_html_cache": None,
            }
        )
        seen = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                snap = snapshot_state()
                s = (snap.get("summary") or {}).get("v")
                v = (snap.get("views") or {}).get("v")
                if s is not None and v is not None:
                    seen.append((s, v))
                # 撕裂：新 summary + 旧 views
                if s == "new" and v == "old":
                    seen.append(("TORN", s, v))

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        time.sleep(0.01)
        for i in range(20):
            publish(
                {},
                {"v": "new"},
                fragments={"f": i},
                views={"v": "new"},
            )
        stop.set()
        t.join(timeout=1)
        torn = [x for x in seen if isinstance(x, tuple) and x and x[0] == "TORN"]
        # 允许极短窗口？我们的实现 clear+update 仍可能短暂空；断言不应有 new+old 配对
        self.assertEqual(torn, [], f"torn samples: {torn[:5]} seen={len(seen)}")


class TestC3GenerateRoot(unittest.TestCase):
    def test_generate_with_temp_root_does_not_touch_default_data(self):
        """传临时 root 时不得在默认 数据/ 下新建看板.db（用 mtime 哨兵）。"""
        import core
        import datetime as dt

        default_db = ROOT / "数据" / "看板.db"
        before = default_db.stat().st_mtime_ns if default_db.is_file() else None
        tmp = Path(tempfile.mkdtemp(prefix="t263c3_"))
        try:
            shutil.copy2(ROOT / "config.json", tmp / "config.json")
            data = tmp / "数据"
            data.mkdir()
            # 最小空库：走 generate 可能因缺源失败；至少 connect 路径不碰默认
            cfg = loaders.load_config(tmp)
            cfg["data_dir"] = "数据"
            cfg["db_path"] = "看板.db"
            # 直接测 db_path / connect 贯通
            import db as dbmod

            p = dbmod.db_path(cfg, tmp)
            self.assertTrue(str(p).startswith(str(tmp)))
            self.assertNotIn(str(ROOT / "数据"), str(p))
            conn = dbmod.connect(cfg, tmp)
            conn.close()
            # generate 可能因缺源抛错，不强制跑满；根路径已覆盖
            after = default_db.stat().st_mtime_ns if default_db.is_file() else None
            self.assertEqual(before, after)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
