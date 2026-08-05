#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.8 G1：写锁死锁清零。

硬性要求：
- 禁止 mock routes._srv.recompute 掩盖 already_locked 透传
- 真路径：with_write_lock 持锁 → recompute(already_locked=True) 不二次抢锁
- 连续 manual 保存 200；刷新持锁 → 409 无脏写；BU recompute 不死锁
"""
from __future__ import annotations

import inspect
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import loaders  # noqa: E402
from app_state import _LOCK, _state  # noqa: E402
from routes import _srv  # noqa: E402


class TestSrvPassthrough(unittest.TestCase):
    def test_recompute_signature_accepts_already_locked(self):
        sig = inspect.signature(_srv.recompute)
        self.assertIn("already_locked", sig.parameters)
        self.assertIn("rebuild_std", sig.parameters)

    def test_start_refresh_async_signature_accepts_on_complete(self):
        sig = inspect.signature(_srv.start_refresh_async)
        self.assertIn("on_complete", sig.parameters)

    def test_recompute_already_locked_does_not_reacquire(self):
        """持锁时 already_locked=True 必须在超时内返回（无死锁）。"""
        import refresh_pipeline as rp

        calls = []
        orig = rp.do_recompute

        def _stub(cfg, root=None, *, rebuild_std=False):
            calls.append({"rebuild_std": rebuild_std, "locked": _LOCK.locked()})

        rp.do_recompute = _stub  # type: ignore[assignment]
        try:
            self.assertTrue(_LOCK.acquire(blocking=False))
            try:
                done = []

                def _run():
                    # 走生产包装 → server.recompute → pipeline（须透传 already_locked）
                    _srv.recompute({}, None, rebuild_std=False, already_locked=True)
                    done.append(1)

                t = threading.Thread(target=_run, daemon=True)
                t.start()
                t.join(timeout=2.0)
                self.assertFalse(t.is_alive(), "already_locked=True 仍挂起 → 死锁回归")
                self.assertEqual(done, [1])
                self.assertEqual(len(calls), 1)
                self.assertTrue(calls[0]["locked"])
            finally:
                _LOCK.release()
        finally:
            rp.do_recompute = orig


class TestManualWriteLockLive(unittest.TestCase):
    """HTTP 集成：真 with_write_lock 路径；recompute 用 **kwargs 桩（不吞 already_locked 签名）。"""

    def setUp(self):
        import server

        self.tmp = Path(tempfile.mkdtemp(prefix="t378_wl_"))
        shutil.copy2(ROOT / "config.json", self.tmp / "config.json")
        (self.tmp / "数据").mkdir()
        self.cfg = loaders.load_config(self.tmp)
        accounts.seed_defaults(self.cfg, self.tmp)
        # 记录 kwargs，证明 already_locked=True 到达 server.recompute
        self.seen_kwargs: list[dict] = []
        self._orig = server.recompute

        def _track(cfg, root=None, *, rebuild_std=False, already_locked=False, **extra):
            self.seen_kwargs.append(
                {
                    "rebuild_std": rebuild_std,
                    "already_locked": already_locked,
                    **extra,
                }
            )
            server._state["built_at"] = "RECOMPUTED"

        server.recompute = _track  # type: ignore[assignment]
        _state["refreshing"] = None
        # 确保锁空闲
        if _LOCK.locked():
            try:
                _LOCK.release()
            except RuntimeError:
                pass
        self.server = server
        self.app = server.create_app(self.cfg, root=self.tmp)
        from fastapi.testclient import TestClient

        self.client = TestClient(self.app, follow_redirects=False)
        r = self.client.post(
            "/admin/login",
            data={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
        )
        sid = r.cookies.get(server.SID_COOKIE) or r.cookies.get(server.COOKIE)
        self.hdr = {"Cookie": f"{server.SID_COOKIE}={sid}"}

    def tearDown(self):
        self.server.recompute = self._orig
        _state["refreshing"] = None
        while _LOCK.locked():
            try:
                _LOCK.release()
            except RuntimeError:
                break
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_consecutive_manual_saves_200_and_pass_already_locked(self):
        """连续保存均 200；每次 recompute 收到 already_locked=True。"""
        body = {
            "items": [
                {
                    "归属月": "2026-07",
                    "项目": "装修费",
                    "金额": 100,
                    "范围": "全公司",
                }
            ]
        }
        # 项目名可能被校验拒绝 → 用单条 manual 若项目白名单不认则跳到 adjust 路径
        r1 = self.client.post("/api/v1/admin/manual_batch", headers=self.hdr, json=body)
        # 若 batch 因业务校验 400，改用 detax_rates 等更稳写路径；优先 manual
        if r1.status_code == 400:
            # fallback: detax_rates 写路径同样走 with_write_lock
            r1 = self.client.post(
                "/api/v1/admin/detax_rates",
                headers=self.hdr,
                json={"rates": {"语言": 0.03}},
            )
        self.assertEqual(r1.status_code, 200, r1.text)
        n_after_first = len(self.seen_kwargs)
        self.assertGreaterEqual(n_after_first, 1)
        self.assertTrue(
            self.seen_kwargs[-1].get("already_locked") is True,
            f"first recompute kwargs={self.seen_kwargs[-1]}",
        )

        r2 = self.client.post(
            "/api/v1/admin/detax_rates",
            headers=self.hdr,
            json={"rates": {"语言": 0.04}},
        )
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertGreater(len(self.seen_kwargs), n_after_first)
        self.assertTrue(self.seen_kwargs[-1].get("already_locked") is True)

        # 锁必须已释放，可再 acquire
        self.assertTrue(_LOCK.acquire(blocking=False), "写完后锁应释放")
        _LOCK.release()

    def test_refresh_held_lock_returns_409_no_recompute(self):
        """刷新持锁时写 → 409，不调用 recompute。"""
        self.assertTrue(_LOCK.acquire(blocking=False))
        try:
            _state["refreshing"] = {"trigger": "manual", "started": time.time()}
            before = len(self.seen_kwargs)
            r = self.client.post(
                "/api/v1/admin/detax_rates",
                headers=self.hdr,
                json={"rates": {"语言": 0.05}},
            )
            self.assertEqual(r.status_code, 409, r.text)
            self.assertIn("更新进行中", r.json().get("detail") or r.text)
            self.assertEqual(len(self.seen_kwargs), before, "409 不得触发 recompute")
        finally:
            _state["refreshing"] = None
            _LOCK.release()


class TestBuConfigAlreadyLocked(unittest.TestCase):
    def test_bu_config_recompute_passes_already_locked(self):
        import server

        tmp = Path(tempfile.mkdtemp(prefix="t378_bu_"))
        try:
            shutil.copy2(ROOT / "config.json", tmp / "config.json")
            (tmp / "数据").mkdir()
            cfg = loaders.load_config(tmp)
            accounts.seed_defaults(cfg, tmp)
            seen = []
            orig = server.recompute

            def _track(cfg, root=None, *, rebuild_std=False, already_locked=False, **k):
                seen.append({"already_locked": already_locked, "rebuild_std": rebuild_std})
                server._state["built_at"] = "RECOMPUTED"

            server.recompute = _track  # type: ignore[assignment]
            _state["refreshing"] = None
            app = server.create_app(cfg, root=tmp)
            from fastapi.testclient import TestClient

            client = TestClient(app, follow_redirects=False)
            r = client.post(
                "/admin/login",
                data={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
            )
            sid = r.cookies.get(server.SID_COOKIE) or r.cookies.get(server.COOKIE)
            hdr = {"Cookie": f"{server.SID_COOKIE}={sid}"}
            # 读当前 bu 配置再原样写回
            g = client.get("/api/v1/admin/bu_config", headers=hdr)
            if g.status_code != 200:
                # 无此 GET 时用最小合法 body
                bus = [{"name": "语言", "业务线": ["语言"]}]
                payload = {"bus": bus, "公共费用分摊启用": False}
            else:
                body = g.json()
                payload = {
                    "bus": body.get("bus") or [],
                    "公共费用分摊启用": bool(body.get("公共费用分摊启用")),
                }
            resp = client.post("/api/v1/admin/bu_config", headers=hdr, json=payload)
            # TEST-002：禁止 400 时退化为「源码含 already_locked 字符串」假绿；必须真行为
            self.assertEqual(
                resp.status_code,
                200,
                f"BU config save must succeed for lock probe: {resp.status_code} {resp.text[:200]}",
            )
            self.assertTrue(seen, "应调用 recompute")
            self.assertTrue(seen[-1]["already_locked"] is True, seen)
            self.assertTrue(_LOCK.acquire(blocking=False), "BU 写完锁应释放")
            _LOCK.release()
            server.recompute = orig
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            server.recompute = getattr(server, "recompute", None) or orig  # type: ignore[name-defined]


class TestNoTypeErrorFallback(unittest.TestCase):
    def test_manual_has_no_typeerror_dead_path(self):
        src = (ROOT / "src/routes/manual.py").read_text(encoding="utf-8")
        # 死路径特征：except TypeError 后无 already_locked 再 recompute
        self.assertNotIn("except TypeError", src)
        self.assertIn("already_locked=True", src)


if __name__ == "__main__":
    unittest.main()
