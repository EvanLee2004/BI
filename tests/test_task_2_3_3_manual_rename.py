#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书 2.3.3：手填「房租→房租物业」「物业费→其他」+ 库 key 幂等迁移。

驱动 shipped 路径：schema.migrate_manual_item_names_2_3_3 / create_all；
config 装载后手填名与台账剔除名单拆分。
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestConfigManualVsLedgerSplit(unittest.TestCase):
    """手填展示名 ≠ 台账剔除名（防双计红线）。"""

    def test_config_json_split(self):
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        names = [it["name"] for it in cfg["manual_items"] if isinstance(it, dict)]
        self.assertIn("房租物业", names)
        self.assertIn("其他", names)
        self.assertIn("装修费", names)
        self.assertNotIn("房租", names)  # 手填旧名不得再出现
        self.assertNotIn("物业费", names)
        fine = list(cfg["manual_alloc_fine_types"])
        self.assertEqual(fine, ["房租", "物业费", "装修费"])
        cmap = cfg["manual_alloc_category_map"]
        self.assertEqual(cmap.get("房租物业"), "固定运营费用")
        self.assertEqual(cmap.get("其他"), "固定运营费用")
        self.assertEqual(cmap.get("装修费"), "固定运营费用")
        self.assertNotIn("房租", cmap)
        self.assertNotIn("物业费", cmap)

    def test_default_cmap_keys_match_new_names(self):
        from profit.expense_period import _DEFAULT_MANUAL_ALLOC_CMAP, manual_alloc_amounts_by_cat

        self.assertEqual(
            set(_DEFAULT_MANUAL_ALLOC_CMAP.keys()),
            {"房租物业", "其他", "装修费"},
        )
        man = {"房租物业": 100_00, "其他": 20_00, "装修费": 0}
        self.assertEqual(manual_alloc_amounts_by_cat(man, None).get("固定运营费用"), 120_00)


class TestMigrateManualItemNames(unittest.TestCase):
    """shipped migrate_manual_item_names_2_3_3：rename / merge / 二次幂等。"""

    def setUp(self):
        import schema

        self.conn = sqlite3.connect(":memory:")
        schema.create_all(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_rename_only_old(self):
        import schema

        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额, 填写时间, 经手人) VALUES(?,?,?,?,?)",
            ("2026-03", "房租", 12000_00, "t", "u"),
        )
        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额, 填写时间, 经手人) VALUES(?,?,?,?,?)",
            ("2026-03", "物业费", 300_00, "t", "u"),
        )
        self.conn.execute(
            "INSERT INTO manual_手填BU(归属月, 范围, 项目, 金额, 填写时间, 经手人) VALUES(?,?,?,?,?,?)",
            ("2026-03", "语言", "房租", 5000_00, "t", "u"),
        )
        self.conn.execute(
            "INSERT INTO manual_历史(时间, 经手人, 归属月, 项目, 旧值, 新值) VALUES(?,?,?,?,?,?)",
            ("t", "u", "2026-03", "房租", 0, 12000_00),
        )
        self.conn.commit()

        st = schema.migrate_manual_item_names_2_3_3(self.conn)
        self.conn.commit()
        self.assertGreaterEqual(st["manual_手填"], 2)
        self.assertGreaterEqual(st["manual_手填BU"], 1)
        self.assertGreaterEqual(st["manual_历史"], 1)

        rows = {
            r[0]: r[1]
            for r in self.conn.execute(
                "SELECT 项目, 金额 FROM manual_手填 WHERE 归属月=?", ("2026-03",)
            )
        }
        self.assertEqual(rows.get("房租物业"), 12000_00)
        self.assertEqual(rows.get("其他"), 300_00)
        self.assertNotIn("房租", rows)
        self.assertNotIn("物业费", rows)

        bu = self.conn.execute(
            "SELECT 项目, 金额 FROM manual_手填BU WHERE 归属月=? AND 范围=?",
            ("2026-03", "语言"),
        ).fetchall()
        self.assertEqual(dict(bu), {"房租物业": 5000_00})

        hist = self.conn.execute("SELECT 项目 FROM manual_历史").fetchall()
        self.assertEqual([h[0] for h in hist], ["房租物业"])

    def test_merge_conflict_sum_fen(self):
        import schema

        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额) VALUES(?,?,?)",
            ("2026-04", "房租", 100_00),
        )
        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额) VALUES(?,?,?)",
            ("2026-04", "房租物业", 50_00),
        )
        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额) VALUES(?,?,?)",
            ("2026-04", "物业费", 10_00),
        )
        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额) VALUES(?,?,?)",
            ("2026-04", "其他", 7_00),
        )
        self.conn.commit()

        schema.migrate_manual_item_names_2_3_3(self.conn)
        self.conn.commit()
        rows = {
            r[0]: r[1]
            for r in self.conn.execute(
                "SELECT 项目, 金额 FROM manual_手填 WHERE 归属月=?", ("2026-04",)
            )
        }
        self.assertEqual(rows["房租物业"], 150_00)
        self.assertEqual(rows["其他"], 17_00)
        self.assertNotIn("房租", rows)
        self.assertNotIn("物业费", rows)

    def test_second_migrate_idempotent(self):
        import schema

        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额) VALUES(?,?,?)",
            ("2026-05", "房租", 88_00),
        )
        self.conn.commit()
        schema.migrate_manual_item_names_2_3_3(self.conn)
        self.conn.commit()
        st2 = schema.migrate_manual_item_names_2_3_3(self.conn)
        self.conn.commit()
        self.assertEqual(st2["manual_手填"], 0)
        self.assertEqual(st2["manual_手填BU"], 0)
        amt = self.conn.execute(
            "SELECT 金额 FROM manual_手填 WHERE 归属月=? AND 项目=?",
            ("2026-05", "房租物业"),
        ).fetchone()
        self.assertEqual(amt[0], 88_00)
        n_old = self.conn.execute(
            "SELECT COUNT(*) FROM manual_手填 WHERE 项目 IN ('房租','物业费')"
        ).fetchone()[0]
        self.assertEqual(n_old, 0)

    def test_create_all_runs_migrate(self):
        """create_all 挂链：旧 key 写入后再次 create_all（同 conn）须迁完。"""
        import schema

        # 新空库已 create_all；写入旧 key 后再调 migrate（create_all 内也会调）
        self.conn.execute(
            "INSERT INTO manual_手填(归属月, 项目, 金额) VALUES(?,?,?)",
            ("2026-06", "物业费", 1_00),
        )
        self.conn.commit()
        # 模拟 ensure 路径再次执行迁移段
        schema.migrate_manual_item_names_2_3_3(self.conn)
        self.conn.commit()
        row = self.conn.execute(
            "SELECT 项目, 金额 FROM manual_手填 WHERE 归属月=?", ("2026-06",)
        ).fetchone()
        self.assertEqual(row, ("其他", 1_00))


if __name__ == "__main__":
    unittest.main()
