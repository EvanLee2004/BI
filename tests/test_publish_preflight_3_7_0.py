# -*- coding: utf-8 -*-
"""3.7.0 发布门闸：驱动 shipped publish_preflight / reload_verify。"""

from __future__ import annotations

import unittest

from publish_preflight import declare_publish_success, require_backup_meta


class TestRequireBackupMeta(unittest.TestCase):
    def test_missing_meta(self):
        ok, reason = require_backup_meta(None)
        self.assertFalse(ok)
        self.assertEqual(reason, "backup_meta_missing")

    def test_path_and_sha(self):
        ok, reason = require_backup_meta(
            {
                "backup_path": "/data/备份/x.db",
                "backup_sha256": "abc",
                "manifest_path": "/data/备份/x.manifest.json",
            }
        )
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "ok")

    def test_path_without_integrity(self):
        ok, reason = require_backup_meta({"backup_path": "/data/x.db"})
        self.assertFalse(ok)
        self.assertEqual(reason, "backup_integrity_missing")


class TestDeclarePublishSuccess(unittest.TestCase):
    def test_requires_backup(self):
        ok, reason = declare_publish_success(
            health_code=200,
            runtime_version="3.7.0",
            disk_version="3.7.0",
            runtime_commit="abcdef1",
            disk_commit="abcdef1",
            runtime_pid=123,
            backup_ok=False,
            process_switch_ok=True,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "backup_required")

    def test_full_gate_ok(self):
        ok, reason = declare_publish_success(
            health_code=200,
            runtime_version="3.7.0",
            disk_version="3.7.0",
            runtime_commit="abcdef123456",
            disk_commit="abcdef1",
            runtime_pid=99,
            backup_ok=True,
            process_switch_ok=True,
        )
        self.assertTrue(ok, reason)

    def test_version_mismatch(self):
        ok, reason = declare_publish_success(
            health_code=200,
            runtime_version="3.6.3",
            disk_version="3.7.0",
            runtime_commit="abc",
            disk_commit="abc",
            runtime_pid=1,
            backup_ok=True,
            process_switch_ok=True,
        )
        self.assertFalse(ok)
        self.assertIn("version_mismatch", reason)

    def test_no_pid(self):
        ok, reason = declare_publish_success(
            health_code=200,
            runtime_version="3.7.0",
            disk_version="3.7.0",
            runtime_commit="abc",
            disk_commit="abc",
            runtime_pid="",
            backup_ok=True,
            process_switch_ok=True,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "no_runtime_pid")

    def test_disk_version_alone_not_enough(self):
        """无 runtime version 即使 health 200 也不得成功。"""
        ok, reason = declare_publish_success(
            health_code=200,
            runtime_version="",
            disk_version="3.7.0",
            runtime_commit="abc",
            disk_commit="abc",
            runtime_pid=1,
            backup_ok=True,
            process_switch_ok=True,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "no_runtime_version")


if __name__ == "__main__":
    unittest.main()
