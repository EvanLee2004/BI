# -*- coding: utf-8 -*-
"""P2 BE-001/002/006：写路径原子性、诚实错误、安全 restore。

- BE-001：reapply 中途 adj 失败 → std 不半新（整事务回滚）
- BE-002：写库后 recompute OperationalError → 503 非 409
- BE-006：默认拒绝在线 restore；allow_online 放行
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import ingest  # noqa: E402
import loaders  # noqa: E402
from ingest import archive  # noqa: E402


def _cfg(tmp: Path) -> dict:
    cfg = dict(loaders.load_config(ROOT))
    cfg["db_path"] = "看板.db"
    cfg["data_dir"] = "数据"
    return cfg


class TestBe001AtomicReapply(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="be001_"))
        (self.tmp / "数据").mkdir()
        self.cfg = _cfg(self.tmp)
        self.conn = db.connect(self.cfg, self.tmp)
        # seed std row
        self.conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,客户,归属月,原值_归属月) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("LOC-1", "SO1", "2026-01-01", 10000, "部", "销", "客", "2026-01", "2026-01"),
        )
        self.conn.commit()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reapply_adj_fail_rolls_back_std(self):
        """adj 中途失败 → 旧 std 定位键仍在（非空壳半新）。"""
        old_n = self.conn.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0]
        self.assertEqual(old_n, 1)
        records = {
            "std_下单": [
                {
                    "定位键": "NEW-1",
                    "订单号": "N1",
                    "下单日期": "2026-06-01",
                    "下单预估额": 99.0,
                    "部门": "部",
                    "销售": "销",
                    "客户": "客",
                    "归属月": "2026-06",
                    "原值_归属月": "2026-06",
                }
            ],
            "std_收入明细": [],
            "std_回款": [],
            "std_内部译员": [],
            "std_费用明细": [],
        }

        def boom(*_a, **_k):
            raise RuntimeError("injected adj fail")

        with mock.patch("ingest.adjust.apply_adjustments", side_effect=boom):
            with self.assertRaises(RuntimeError):
                ingest.reapply(self.cfg, self.conn, records)

        # 回滚后旧行仍在
        n = self.conn.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0]
        self.assertEqual(n, 1, "BE-001：adj 失败不得留下半新 std")
        loc = self.conn.execute("SELECT 定位键 FROM std_下单").fetchone()[0]
        self.assertEqual(loc, "LOC-1")


class TestBe002HonestRecomputeError(unittest.TestCase):
    def test_with_write_lock_source_maps_recompute_ope_to_503(self):
        src = (ROOT / "src" / "routes" / "manual.py").read_text(encoding="utf-8")
        self.assertIn("status_code=503", src)
        self.assertIn("已保存", src)

    def test_recompute_operational_error_returns_503_not_409(self):
        """BE-002 行为注入：yield 写库成功后 recompute 抛 OperationalError → HTTP 503。"""
        import accounts
        import server
        from app_state import _LOCK, _state
        from fastapi.testclient import TestClient

        tmp = Path(tempfile.mkdtemp(prefix="be002_"))
        try:
            shutil.copy2(ROOT / "config.json", tmp / "config.json")
            (tmp / "数据").mkdir()
            cfg = loaders.load_config(tmp)
            accounts.seed_defaults(cfg, tmp)
            orig = server.recompute

            def _boom(cfg, root=None, *, rebuild_std=False, already_locked=False, **k):
                raise sqlite3.OperationalError("injected database is locked")

            server.recompute = _boom  # type: ignore[assignment]
            _state["refreshing"] = None
            while _LOCK.locked():
                try:
                    _LOCK.release()
                except RuntimeError:
                    break
            app = server.create_app(cfg, root=tmp)
            client = TestClient(app, follow_redirects=False)
            r = client.post(
                "/admin/login",
                data={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
            )
            sid = r.cookies.get(server.SID_COOKIE) or r.cookies.get(server.COOKIE)
            hdr = {"Cookie": f"{server.SID_COOKIE}={sid}"}
            # detax_rates 走 with_write_lock（写成功后 recompute）
            resp = client.post(
                "/api/v1/admin/detax_rates",
                headers=hdr,
                json={"rates": {"语言": 0.03}},
            )
            self.assertEqual(
                resp.status_code,
                503,
                f"recompute OPE must be 503 not 409: {resp.status_code} {resp.text[:300]}",
            )
            detail = ""
            try:
                detail = str((resp.json() or {}).get("detail") or "")
            except Exception:
                detail = resp.text
            self.assertIn("已保存", detail)
            self.assertNotEqual(resp.status_code, 409)
            server.recompute = orig
        finally:
            server.recompute = orig  # type: ignore[name-defined]
            shutil.rmtree(tmp, ignore_errors=True)


class TestBe006OnlineRestoreBlocked(unittest.TestCase):
    def test_default_blocks_without_allow(self):
        tmp = Path(tempfile.mkdtemp(prefix="be006_"))
        try:
            data = tmp / "数据"
            data.mkdir()
            bak = data / "备份"
            bak.mkdir()
            # minimal sqlite files
            dbp = data / "看板.db"
            conn = sqlite3.connect(str(dbp))
            conn.execute("CREATE TABLE t(x)")
            conn.commit()
            conn.close()
            bak_path = bak / "看板_20260101.db"
            shutil.copy2(dbp, bak_path)
            cfg = _cfg(tmp)
            # ensure no env allow
            import os

            old = os.environ.pop("KANBAN_ALLOW_ONLINE_RESTORE", None)
            try:
                res = archive.restore_db_from_backup(cfg, bak_path, tmp)
                self.assertEqual(res.get("status"), "error")
                self.assertEqual(res.get("code"), "online_restore_blocked")
            finally:
                if old is not None:
                    os.environ["KANBAN_ALLOW_ONLINE_RESTORE"] = old
            # allow_online 放行
            res2 = archive.restore_db_from_backup(cfg, bak_path, tmp, allow_online=True)
            self.assertEqual(res2.get("status"), "ok")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
