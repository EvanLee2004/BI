# -*- coding: utf-8 -*-
"""3.6.0 G1：发布原子性 / 启动安全 / 安装状态 / Excel 稳定复制 / 备份恢复。

驱动真实 shipped 模块；禁止 re-implement 判据。
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class TestReloadVerify(unittest.TestCase):
    def test_health_alone_not_enough(self):
        from reload_verify import verify_process_switch

        ok, reason = verify_process_switch(
            old_pid="100",
            new_pid="100",
            health_code=200,
            runtime_version="3.5.0",
            disk_version="3.5.0",
        )
        self.assertFalse(ok)
        self.assertIn("pid_unchanged", reason)

    def test_stale_commit_fails(self):
        from reload_verify import verify_process_switch

        ok, reason = verify_process_switch(
            old_pid="1",
            new_pid="2",
            health_code=200,
            runtime_version="3.5.0",
            disk_version="3.5.0",
            runtime_commit="aaaaaaaa",
            disk_commit="bbbbbbbb",
        )
        self.assertFalse(ok)
        self.assertIn("commit_mismatch", reason)

    def test_ok_when_pid_and_version_match(self):
        from reload_verify import verify_process_switch

        ok, reason = verify_process_switch(
            old_pid="1",
            new_pid="2",
            health_code=200,
            runtime_version="3.5.0",
            disk_version="3.5.0",
            runtime_commit="abc1234deadbeef",
            disk_commit="abc1234",
            old_pid_still_alive=False,
        )
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "ok")

    def test_disk_commit_without_runtime_fails(self):
        from reload_verify import verify_process_switch

        ok, reason = verify_process_switch(
            old_pid="1",
            new_pid="2",
            health_code=200,
            runtime_version="3.6.0",
            disk_version="3.6.0",
            runtime_commit="",
            disk_commit="426bebc87b40e7cd",
        )
        self.assertFalse(ok)
        self.assertIn("no_runtime_commit", reason)

    def test_term_is_expected_ops_exit(self):
        from reload_verify import is_expected_ops_exit

        self.assertTrue(is_expected_ops_exit(143))
        self.assertTrue(is_expected_ops_exit(0))
        self.assertTrue(is_expected_ops_exit(130))
        self.assertFalse(is_expected_ops_exit(1))
        self.assertFalse(is_expected_ops_exit(42))


class TestInstallStateBootstrap(unittest.TestCase):
    def test_memory_has_data_false_but_disk_ready_not_bootstrap(self):
        from install_state import bootstrap_allowed, detect_phase, resolve_admin_entry

        phase = detect_phase(
            has_accounts=True,
            has_db=True,
            has_source_files=True,
            has_lkg=False,
            last_build_ok=None,
        )
        self.assertEqual(phase, "ready")
        self.assertFalse(
            bootstrap_allowed(
                phase=phase,
                has_accounts=True,
                has_db=True,
                has_source_files=True,
                has_lkg=False,
                memory_has_data=False,
            )
        )

    def test_fresh_and_unconfigured_bootstrap(self):
        from install_state import bootstrap_allowed

        self.assertTrue(
            bootstrap_allowed(
                phase="fresh",
                has_accounts=False,
                has_db=False,
                has_source_files=False,
                has_lkg=False,
                memory_has_data=False,
            )
        )
        # 空机 seed 账号后仍允许首次取数引导
        self.assertTrue(
            bootstrap_allowed(
                phase="unconfigured",
                has_accounts=True,
                has_db=False,
                has_source_files=False,
                has_lkg=False,
                memory_has_data=False,
            )
        )

    def test_build_fail_degraded_not_bootstrap(self):
        from install_state import bootstrap_allowed, detect_phase

        phase = detect_phase(
            has_accounts=True,
            has_db=True,
            has_source_files=True,
            has_lkg=True,
            last_build_ok=False,
        )
        self.assertEqual(phase, "degraded")
        self.assertFalse(
            bootstrap_allowed(
                phase=phase,
                has_accounts=True,
                has_db=True,
                has_source_files=True,
                has_lkg=True,
                memory_has_data=False,
            )
        )

    def test_resolve_admin_entry_on_tmp_disk(self):
        from install_state import mark_ready, resolve_admin_entry

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        # empty → bootstrap
        self.assertEqual(resolve_admin_entry(tmp, memory_has_data=False), "bootstrap")
        # accounts + xlsx → spa even if memory false
        (tmp / "看板账号.json").write_text('{"accounts":[]}', encoding="utf-8")
        (tmp / "下单.xlsx").write_bytes(b"PK\x03\x04fake")
        mark_ready(tmp, version="3.6.0", commit="deadbeef")
        self.assertEqual(resolve_admin_entry(tmp, memory_has_data=False), "spa")


class TestExcelStableCopy(unittest.TestCase):
    def test_bad_zip_retries_then_fails(self):
        from excel_stable import StableCopyError, stable_copy

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        src = tmp / "bad.xlsx"
        src.write_bytes(b"not-a-zip")
        dest = tmp / "snap"
        with self.assertRaises(StableCopyError) as cm:
            stable_copy(src, dest, retries=2, settle_ms=1)
        self.assertEqual(cm.exception.source, "bad.xlsx")
        self.assertIn(cm.exception.args[0], ("bad_zip", "size_unstable"))

    def test_good_xlsx_copies(self):
        from excel_stable import stable_copy

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        src = tmp / "ok.xlsx"
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr("xl/workbook.xml", "<workbook/>")
        out = stable_copy(src, tmp / "snap", retries=2, settle_ms=1)
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 0)


class TestDbBackupRestore(unittest.TestCase):
    def _mini_db(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute('CREATE TABLE "std_下单" (id INTEGER)')
            conn.execute('INSERT INTO "std_下单" VALUES (1),(2)')
            conn.execute('CREATE TABLE "std_回款" (id INTEGER)')
            conn.commit()
        finally:
            conn.close()

    def test_backup_manifest_has_version_commit(self):
        from db_backup import backup_sqlite, restore_isolated_verify

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        db = tmp / "看板.db"
        self._mini_db(db)
        meta = backup_sqlite(db, tmp / "备份", version="3.6.0", commit="abc1234dead")
        self.assertEqual(meta["version"], "3.6.0")
        self.assertTrue(meta["git_commit"].startswith("abc1234"))
        self.assertIn("counts_fp", meta)
        self.assertTrue(Path(meta["backup_path"]).is_file())
        res = restore_isolated_verify(
            meta["backup_path"],
            expected_counts_fp=meta["counts_fp"],
            work_dir=tmp / "restore",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["counts_fp"], meta["counts_fp"])

    def test_corrupt_backup_fails_quick_check(self):
        from db_backup import quick_check

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        bad = tmp / "x.db"
        bad.write_bytes(b"not sqlite")
        ok, reason = quick_check(bad)
        self.assertFalse(ok)


class TestLkgSnapshot(unittest.TestCase):
    def test_save_load_roundtrip(self):
        from lkg_snapshot import is_compatible, load_lkg, save_lkg

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        save_lkg(
            tmp,
            {"meta": {"year": 2026}},
            version="3.6.0",
            commit="c0ffee",
            schema_version=3,
        )
        data = load_lkg(tmp, require_schema=3)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["summary"]["meta"]["year"], 2026)
        self.assertTrue(is_compatible(data, schema_version=3))

    def test_checksum_tamper_fails(self):
        from lkg_snapshot import load_lkg, lkg_path, save_lkg

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        save_lkg(tmp, {"meta": {"year": 2026}}, version="3.6.0", schema_version=3)
        p = lkg_path(tmp)
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace('"year": 2026', '"year": 2099'), encoding="utf-8")
        self.assertIsNone(load_lkg(tmp))

    def test_schema_none_not_compatible(self):
        from lkg_snapshot import is_compatible

        self.assertFalse(
            is_compatible({"summary": {}, "schema_version": None})
        )
        self.assertFalse(is_compatible({"summary": {}}))

    def test_corrupt_returns_none(self):
        from lkg_snapshot import load_lkg, lkg_path

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        p = lkg_path(tmp)
        p.parent.mkdir(parents=True)
        p.write_text("{not json", encoding="utf-8")
        self.assertIsNone(load_lkg(tmp))


class TestWatchdogTermNotCrash(unittest.TestCase):
    def test_script_exits_on_143_without_fail_count(self):
        text = (ROOT / "deploy/linux/start_with_rollback.sh").read_text(encoding="utf-8")
        self.assertIn("143", text)
        self.assertIn("预期运维退出", text)
        # 不把 143 送进 FAILS 累加路径之前就 exit
        idx_term = text.find("143")
        idx_fails = text.find("FAILS=$((FAILS + 1))")
        self.assertGreater(idx_fails, idx_term)

    def test_systemd_on_failure_not_always(self):
        text = (ROOT / "deploy/linux/kanban.service").read_text(encoding="utf-8")
        self.assertIn("Restart=on-failure", text)
        self.assertNotIn("Restart=always", text)

    def test_reload_uses_reload_verify(self):
        text = (ROOT / "deploy/linux/reload_kanban.sh").read_text(encoding="utf-8")
        self.assertIn("reload_verify", text)
        self.assertIn("verify_process_switch", text)


class TestAdminNotBootstrapWhenInstalled(unittest.TestCase):
    def test_admin_pages_uses_install_state(self):
        src = (ROOT / "src/routes/admin_pages.py").read_text(encoding="utf-8")
        self.assertIn("install_state", src)
        self.assertIn("resolve_admin_entry", src)
        self.assertIn("维护中", src)


if __name__ == "__main__":
    unittest.main()
