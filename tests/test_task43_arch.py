#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书43：SQL 守卫、共享盘只读、治理、告警、登录锁、日志脱敏。"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# —— SQL 白名单：仅存储层可含裸 SQL ——
SQL_ALLOW = {
    "db.py",
    "db_write.py",
    "schema.py",
}
# 只认大写 SQL 关键字（代码里 SQL 用大写；避开 update/apply/commit 方法名）
SQL_RE = re.compile(
    r"""(?x)
    \bSELECT\b.+\bFROM\b
    |\bINSERT\s+(OR\s+REPLACE\s+)?INTO\b
    |\bUPDATE\s+\w+\s+SET\b
    |\bDELETE\s+FROM\b
    |\bPRAGMA\s+\w+
    |\bBEGIN\s+IMMEDIATE\b
    |\bROLLBACK\b
    """
)
# 业务/管道层（不得含 SQL 字面量）
SQL_SCAN_GLOBS = [
    "profit.py",
    "routes/*.py",
    "server.py",
    "accounts.py",
    "core.py",
    "refresh_pipeline.py",
    "ingest/*.py",
    "notify.py",
    "login_guard.py",
    "app_logging.py",
]


class TestNoRawSqlInBusiness(unittest.TestCase):
    def test_business_zero_sql_literals(self):
        bad = []
        for pattern in SQL_SCAN_GLOBS:
            for p in SRC.glob(pattern):
                if p.name in SQL_ALLOW:
                    continue
                if p.name == "__init__.py" and p.parent.name == "ingest":
                    # ingest 包入口可 import db_write，不应有 SQL
                    pass
                text = p.read_text(encoding="utf-8", errors="replace")
                # 去掉注释行
                lines = []
                for ln in text.splitlines():
                    s = ln.strip()
                    if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
                        continue
                    lines.append(ln)
                body = "\n".join(lines)
                if SQL_RE.search(body):
                    # 允许出现在字符串文档/注释已滤；仍命中则报
                    for i, ln in enumerate(body.splitlines(), 1):
                        if SQL_RE.search(ln) and not ln.strip().startswith("#"):
                            bad.append(f"{p.relative_to(ROOT)}:{i}:{ln.strip()[:100]}")
        self.assertEqual(bad, [], "业务层出现裸 SQL：\n" + "\n".join(bad[:30]))


class TestShareReadOnly(unittest.TestCase):
    def test_fetch_only_copies_into_local(self):
        src = (ROOT / "src" / "ingest" / "fetch.py").read_text(encoding="utf-8")
        # 允许 copy2(share, local)；禁止 copy2(local, share) 形态与 open 写 share
        self.assertIn("shutil.copy2(share, local)", src)
        self.assertNotIn("shutil.copy2(local, share)", src)
        self.assertNotRegex(src, r"open\s*\(\s*share")
        self.assertNotRegex(src, r"share\.write")

    def test_no_write_to_ledger_share_path_in_src(self):
        """全库：ledger_share_path 只出现在读配置/fetch 读路径，不作为写目标。"""
        hits = []
        for p in SRC.rglob("*.py"):
            if p.name.endswith(".pyc"):
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            if "ledger_share" not in t:
                continue
            for i, ln in enumerate(t.splitlines(), 1):
                if "ledger_share" not in ln:
                    continue
                # 写操作红线
                if re.search(r"write_text|open\([^)]*['\"]w|to_excel|dump\(|shutil\.copy2\([^,]+,\s*share", ln):
                    hits.append(f"{p}:{i}:{ln.strip()}")
        self.assertEqual(hits, [], hits)


class TestPruneAndVacuum(unittest.TestCase):
    def test_prune_run_logs(self):
        import db
        import db_write
        import loaders
        import schema

        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "数据").mkdir()
            cfg = dict(loaders.load_config(ROOT))
            cfg["data_dir"] = "数据"
            cfg["db_path"] = "数据/看板.db"
            conn = db.connect(cfg, tmp)
            # 插两条：旧 + 新
            conn.execute(
                "INSERT INTO meta_运行日志(时间,触发方式,结果,体检JSON) VALUES(?,?,?,?)",
                ("2020-01-01 00:00:00", "t", "绿", "{}"),
            )
            conn.execute(
                "INSERT INTO meta_运行日志(时间,触发方式,结果,体检JSON) VALUES(?,?,?,?)",
                ("2099-01-01 00:00:00", "t", "绿", "{}"),
            )
            conn.commit()
            n = db_write.prune_run_logs(conn, keep_days=30)
            self.assertGreaterEqual(n, 1)
            left = conn.execute("SELECT 时间 FROM meta_运行日志").fetchall()
            self.assertTrue(any("2099" in r[0] for r in left))
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_vacuum_runs(self):
        import db
        import db_write
        import loaders

        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "数据").mkdir()
            cfg = dict(loaders.load_config(ROOT))
            cfg["data_dir"] = "数据"
            cfg["db_path"] = "数据/看板.db"
            conn = db.connect(cfg, tmp)
            db_write.vacuum_db(conn)
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestNotify(unittest.TestCase):
    def test_empty_webhook_silent(self):
        import notify

        self.assertFalse(notify.post_feishu_text("", "hi"))
        notify.maybe_alert_pipeline({"feishu_webhook_url": ""}, {"result": "红"})

    def test_webhook_called_on_red(self):
        import notify

        called = []

        def fake(url, text, timeout=3.0):
            called.append((url, text))
            return True

        with mock.patch.object(notify, "post_feishu_text", side_effect=fake):
            notify.maybe_alert_pipeline(
                {"feishu_webhook_url": "http://example.invalid/hook"},
                {"result": "红", "fetch": {"status": "no_source"}, "db_check": {"ok": True}},
            )
        self.assertEqual(len(called), 1)
        self.assertIn("告警", called[0][1])

    def test_webhook_failure_swallowed(self):
        import notify

        with mock.patch.object(notify, "post_feishu_text", side_effect=RuntimeError("boom")):
            # maybe_alert 内 try；post 已不抛；再包一层
            notify.maybe_alert_pipeline({"feishu_webhook_url": "http://x"}, {"result": "红", "fetch": {}, "db_check": {}})


class TestLoginGuard(unittest.TestCase):
    def setUp(self):
        import login_guard

        login_guard.reset_all_for_tests()

    def test_lock_after_n(self):
        import login_guard

        cfg = {"login_max_failures": 3, "login_lock_minutes": 5}
        for _ in range(3):
            login_guard.register_failure("bob", cfg, now=1000.0)
        self.assertTrue(login_guard.is_locked("bob", cfg, now=1001.0))
        login_guard.clear_failures("bob")
        self.assertFalse(login_guard.is_locked("bob", cfg, now=1001.0))


class TestLogRedact(unittest.TestCase):
    def test_redact_filter(self):
        import logging
        from app_logging import _RedactFilter

        rec = logging.LogRecord("n", logging.INFO, __file__, 1, "password=secret123 token=abc", (), None)
        _RedactFilter().filter(rec)
        self.assertNotIn("secret123", rec.getMessage())
        self.assertIn("***", rec.getMessage())


class TestNginxAssets(unittest.TestCase):
    def test_madr_exists(self):
        self.assertTrue((ROOT / "docs/madr/0003_nginx_proxy_scheme_b.md").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
