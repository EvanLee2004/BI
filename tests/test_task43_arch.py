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

# —— SQL 白名单：仅存储层可含裸 SQL（54.4·E：db 包 _impl 等同原 db.py）——
SQL_ALLOW = {
    "db.py",
    "_impl.py",  # db/_impl.py
    "db_write.py",
    "schema.py",
}
SQL_ALLOW_DIRS = {"db"}  # 整个 db 包允许 SQL
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
    "profit/*.py",
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
                if p.parent.name in SQL_ALLOW_DIRS:
                    continue
                if p.name == "__init__.py" and p.parent.name == "ingest":
                    pass
                text = p.read_text(encoding="utf-8", errors="replace")
                lines = []
                for ln in text.splitlines():
                    s = ln.strip()
                    if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
                        continue
                    lines.append(ln)
                body = "\n".join(lines)
                if SQL_RE.search(body):
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


class TestArchiveExportAndFeishuSettings(unittest.TestCase):
    def test_export_audit_archive_xlsx(self):
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
            conn.execute(
                "INSERT INTO manual_历史(时间,经手人,归属月,项目,旧值,新值) VALUES(?,?,?,?,?,?)",
                ("2026-03-01 10:00:00", "t", "2026-03", "项", 1, 2),
            )
            conn.execute(
                "INSERT INTO manual_配置变更(时间,操作账号,类别,摘要) VALUES(?,?,?,?)",
                ("2026-05-01 11:00:00", "a", "设置", "测"),
            )
            conn.commit()
            raw = db_write.export_audit_archive_xlsx(conn, 2026)
            self.assertGreater(len(raw), 100)
            self.assertTrue(raw[:2] == b"PK")
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_settings_feishu_roundtrip(self):
        import accounts
        import loaders
        import server
        from fastapi.testclient import TestClient

        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "数据").mkdir()
            cfg = dict(loaders.load_config(ROOT))
            cfg["data_dir"] = "数据"
            cfg["db_path"] = "数据/看板.db"
            cfg["zhiyun_auto_fetch"] = False
            accounts.save_accounts(
                cfg,
                tmp,
                [{"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"}],
            )
            app = server.create_app(cfg, root=tmp)
            c = TestClient(app)
            r = c.post("/admin/login", data={"account": "admin1", "password": "8888"}, follow_redirects=False)
            self.assertIn(r.status_code, (302, 303))
            r = c.post("/api/settings", json={"feishu_webhook_url": "https://example.com/hook"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json().get("feishu_webhook_url"), "https://example.com/hook")
            g = c.get("/api/settings")
            self.assertEqual(g.json().get("feishu_webhook_url"), "https://example.com/hook")
            # 归档导出
            r2 = c.get("/api/archive_export", params={"year": "2026"})
            self.assertEqual(r2.status_code, 200, r2.text[:200])
            self.assertIn("spreadsheet", r2.headers.get("content-type", ""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_admin_ui_has_archive_and_feishu(self):
        # 54.4·D4：完整骨架在 admin.html.legacy；admin.html 为 Vue 重定向
        html = (ROOT / "static/admin/admin.html.legacy").read_text(encoding="utf-8")
        js = (ROOT / "static/admin/admin.js").read_text(encoding="utf-8")
        vue = (ROOT / "frontend/src/admin").read_text if False else ""
        self.assertIn("btnArchExport", html)
        self.assertIn("exportAuditArchive", js)
        self.assertIn("sFeishuHook", html)
        self.assertIn("feishu_webhook_url", js)
        self.assertIn("setCardAlert", html)
        # Vue 设置页亦有飞书 webhook 字段
        settings = (ROOT / "frontend/src/admin/views/SettingsView.vue").read_text(encoding="utf-8")
        self.assertTrue("feishu" in settings.lower() or "飞书" in settings)

    def test_watchdog_script_calls_alert(self):
        sh = (ROOT / "deploy/linux/start_with_rollback.sh").read_text(encoding="utf-8")
        self.assertIn("alert_event('rollback'", sh)
        self.assertIn("alert_event('boot_crash'", sh)

    def test_print_hook_in_setup_logging(self):
        src = (ROOT / "src/app_logging.py").read_text(encoding="utf-8")
        self.assertIn("builtins.print", src)
        self.assertIn("kanban.stdout", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
