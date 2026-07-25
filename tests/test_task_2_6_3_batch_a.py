#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.3 批次 A 守卫：原子写 / 坏账号不 seed / db_path 双拼抛错 / 本地配置白名单与坏文件 / 空密 400。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
from secure_io import write_private_text  # noqa: E402


class TestA1AtomicWriteAndCorruptAccounts(unittest.TestCase):
    def setUp(self):
        accounts.clear_accounts_corrupt_status()
        self.tmp = Path(tempfile.mkdtemp(prefix="t263a1_"))
        self.cfg = loaders.load_config()
        self.cfg["data_dir"] = str(self.tmp)

    def tearDown(self):
        accounts.clear_accounts_corrupt_status()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_private_text_atomic_replace(self):
        """同目录 tmp → chmod → os.replace；目标最终可读完整内容。"""
        p = self.tmp / "secret.json"
        write_private_text(p, '{"ok": true}\n')
        self.assertTrue(p.is_file())
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["ok"], True)
        # 无残留 .tmp
        tmps = list(self.tmp.glob(".secret.json.*.tmp"))
        self.assertEqual(tmps, [])

    def test_corrupt_json_quarantine_no_seed(self):
        """截断账号表 → 不 seed 出厂口令；坏文件改名 .corrupt-*；原密不可被 kanban2026 顶替。"""
        accounts.save_accounts(
            self.cfg,
            None,
            [
                {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": "StrongPw_A1b2"},
                {"账号": "overall", "显示名": "整体", "权限": "整体", "密码": "StrongPw_C3d4"},
            ],
        )
        p = self.tmp / "看板账号.json"
        raw = p.read_text(encoding="utf-8")
        p.write_text(raw[: len(raw) // 2], encoding="utf-8")
        rows = accounts.load_accounts(self.cfg, None, create=True)
        self.assertEqual(rows, [], "坏表不得 seed 出厂账号")
        self.assertFalse(p.exists(), "坏文件应被改名隔离")
        corrupts = list(self.tmp.glob("看板账号.json.corrupt-*"))
        self.assertEqual(len(corrupts), 1)
        st = accounts.accounts_corrupt_status()
        self.assertIsNotNone(st)
        self.assertIn("JSON", st.get("reason") or "")
        # 出厂口令不能登（因为没有账号表）
        self.assertIsNone(accounts.authenticate(self.cfg, None, "lushasha", "kanban2026"))
        self.assertIsNone(accounts.authenticate(self.cfg, None, "lushasha", "StrongPw_A1b2"))

    def test_missing_file_still_seeds(self):
        """文件真不存在 → 才 seed。"""
        rows = accounts.load_accounts(self.cfg, None, create=True)
        self.assertTrue(any(a["账号"] == "lushasha" for a in rows))
        self.assertTrue((self.tmp / "看板账号.json").is_file())


class TestA2DbPathAndLocalConfigWhitelist(unittest.TestCase):
    def setUp(self):
        loaders.clear_local_config_corrupt_status()
        self.tmp = Path(tempfile.mkdtemp(prefix="t263a2_"))
        # 在临时 root 放最小 config
        (self.tmp / "config.json").write_text(
            json.dumps(
                {
                    "data_dir": "数据",
                    "db_path": "看板.db",
                    "files": {
                        "project_detail_stem": "项目明细",
                        "orders": "下单.xlsx",
                        "receipts": "回款记录.xlsx",
                        "inhouse": "内部译员.xlsx",
                        "ledger": "收单台账.xlsx",
                        "manual": "手填.xlsx",
                    },
                    "columns": {
                        "project_delivery_date": "整单交付日期",
                        "project_revenue": "交付额/本币",
                        "project_cost": "成本",
                        "project_line": "业务线",
                        "order_date": "下单日期",
                        "order_amount": "金额",
                        "receipt_date": "回款日期",
                        "receipt_amount": "金额",
                        "inhouse_date": "日期",
                        "inhouse_amount": "金额",
                        "inhouse_type": "类型",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp / "数据").mkdir()

    def tearDown(self):
        loaders.clear_local_config_corrupt_status()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_db_path_double_join_raises(self):
        # 故意写「数据/看板.db」触发双拼检测（相对 data_dir=数据 时首段重复）
        bad_rel = "数据" + "/" + "看板.db"
        cfg = {"data_dir": "数据", "db_path": bad_rel}
        with self.assertRaises(ValueError) as cm:
            db.db_path(cfg, self.tmp)
        self.assertIn("看板.db", str(cm.exception))
        self.assertIn("重复", str(cm.exception))

    def test_db_path_correct_no_duplicate_segment(self):
        cfg = {"data_dir": "数据", "db_path": "看板.db"}
        p = db.db_path(cfg, self.tmp)
        parts = p.parts
        # 不得出现连续两个「数据」
        for i in range(len(parts) - 1):
            self.assertFalse(parts[i] == "数据" and parts[i + 1] == "数据")
        self.assertEqual(p.name, "看板.db")
        self.assertEqual(p.parent.name, "数据")

    def test_local_config_cannot_override_db_path(self):
        lc = self.tmp / "数据" / "本地配置.json"
        evil = "数据" + "/" + "看板.db"
        lc.write_text(
            json.dumps({"db_path": evil, "backup_keep_days": 7}, ensure_ascii=False),
            encoding="utf-8",
        )
        cfg = loaders.load_config(self.tmp)
        self.assertEqual(cfg.get("db_path"), "看板.db")  # 危险键被拒，仍用 config 默认
        self.assertEqual(cfg.get("backup_keep_days"), 7)  # 非危险键可覆盖
        self.assertNotIn("feishu_webhook_url", cfg)  # 飞书字段已删，读盘也会丢弃
        p = db.db_path(cfg, self.tmp)
        self.assertEqual(str(p).count("/数据/数据/"), 0)


class TestA4LocalConfigCorruptAndEmptyPassword(unittest.TestCase):
    def setUp(self):
        accounts.clear_accounts_corrupt_status()
        loaders.clear_local_config_corrupt_status()
        self.tmp = Path(tempfile.mkdtemp(prefix="t263a4_"))
        self.cfg = loaders.load_config()
        self.cfg["data_dir"] = str(self.tmp)

    def tearDown(self):
        accounts.clear_accounts_corrupt_status()
        loaders.clear_local_config_corrupt_status()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bad_local_config_marks_yellow_status(self):
        root = self.tmp / "root"
        root.mkdir()
        # 复制最小 config 结构：用正式 config 再改 data_dir 到子目录
        import shutil

        shutil.copy2(ROOT / "config.json", root / "config.json")
        data = root / "数据"
        data.mkdir()
        (data / "本地配置.json").write_text("{not json", encoding="utf-8")
        loaders.clear_local_config_corrupt_status()
        cfg = loaders.load_config(root, strict=False)
        st = loaders.local_config_corrupt_status()
        self.assertIsNotNone(st)
        self.assertIn("JSON", st.get("reason") or st.get("reason", "") or str(st))

    def test_empty_password_raises(self):
        accounts.save_accounts(
            self.cfg,
            None,
            [
                {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": "StrongPw_A1b2"},
                {"账号": "overall", "显示名": "整体", "权限": "整体", "密码": "StrongPw_C3d4"},
            ],
        )
        with self.assertRaises(ValueError) as cm:
            accounts.save_accounts(
                self.cfg,
                None,
                [
                    {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": ""},
                    {"账号": "overall", "显示名": "整体", "权限": "整体", "密码": "StrongPw_C3d4"},
                ],
            )
        self.assertIn("密码不能为空", str(cm.exception))
        # 库内仍是原密码，未变成 8888
        acc = accounts.find_account(self.cfg, None, "lushasha")
        self.assertEqual(acc["密码"], "StrongPw_A1b2")


if __name__ == "__main__":
    unittest.main()
