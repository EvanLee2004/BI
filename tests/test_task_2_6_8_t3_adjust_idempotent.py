# -*- coding: utf-8 -*-
"""2.6.8 T3：调整幂等 + 撤销撤净 + 撤销后 std 值真恢复。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import schema  # noqa: E402
from ingest import adjust as adj_mod  # noqa: E402


class TestAdjustIdempotentAndRevokeAll(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = "数据"
        self.cfg["db_path"] = "看板.db"
        self.conn = db.connect(self.cfg, self.tmp)
        schema.create_all(self.conn)
        fen = money.yuan_to_fen(100) or 10000
        self.conn.execute(
            "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
            "预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            ("KEY_T3", "07", "2026-07-01", fen, "语言", "管理费用", "办公费", "行政", "2026-07", "2026-07"),
        )
        self.conn.commit()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def _dept(self) -> str:
        return self.conn.execute(
            "SELECT 预算归属部门 FROM std_费用明细 WHERE 定位键=? AND 已删除=0",
            ("KEY_T3",),
        ).fetchone()[0]

    def test_double_add_only_one_effective(self):
        a1 = db.add_adjustment(self.conn, "测", "std_费用明细", "KEY_T3", "预算归属部门", "数据部", "一", "改值")
        a2 = db.add_adjustment(self.conn, "测", "std_费用明细", "KEY_T3", "预算归属部门", "产品部", "二", "改值")
        self.assertEqual(a1, a2)
        n = self.conn.execute(
            "SELECT COUNT(*) FROM adj_调整记录 WHERE 目标表=? AND 定位键=? AND 字段=? AND 状态='生效'",
            ("std_费用明细", "KEY_T3", "预算归属部门"),
        ).fetchone()[0]
        self.assertEqual(n, 1)
        val = self.conn.execute(
            "SELECT 新值 FROM adj_调整记录 WHERE id=?", (a1,)
        ).fetchone()[0]
        self.assertEqual(val, "产品部")

    def test_revoke_clears_sibling_effective(self):
        self.conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES('t','u','std_费用明细','KEY_T3','预算归属部门','行政','A','x','改值','生效')"
        )
        self.conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES('t','u','std_费用明细','KEY_T3','预算归属部门','行政','B','x','改值','生效')"
        )
        self.conn.commit()
        ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT id FROM adj_调整记录 WHERE 定位键='KEY_T3' AND 状态='生效' ORDER BY id"
            ).fetchall()
        ]
        self.assertGreaterEqual(len(ids), 2)
        ok = db.revoke_adjustment(self.conn, ids[0])
        self.assertTrue(ok)
        left = self.conn.execute(
            "SELECT COUNT(*) FROM adj_调整记录 WHERE 定位键='KEY_T3' AND 字段='预算归属部门' AND 状态='生效'"
        ).fetchone()[0]
        self.assertEqual(left, 0)

    def test_revoke_restores_std_value_via_replay(self):
        """add → apply → 新值生效 → revoke → 重建源值 → apply → 回到原值。"""
        original = self._dept()
        self.assertEqual(original, "行政")

        aid = db.add_adjustment(
            self.conn, "测", "std_费用明细", "KEY_T3", "预算归属部门", "数据部", "测撤", "改值"
        )
        rep1 = adj_mod.apply_adjustments(self.conn, "2026-07-27 12:00:00")
        self.assertGreaterEqual(int(rep1.get("applied") or 0), 1)
        self.assertEqual(self._dept(), "数据部", "重放后 std 必须是新值")

        ok = db.revoke_adjustment(self.conn, aid)
        self.assertTrue(ok)
        # 模拟下次管道：源值回到台账原文，再重放（已无生效调整）
        self.conn.execute(
            "UPDATE std_费用明细 SET 预算归属部门=? WHERE 定位键=? AND 已删除=0",
            (original, "KEY_T3"),
        )
        self.conn.commit()
        rep2 = adj_mod.apply_adjustments(self.conn, "2026-07-27 12:01:00")
        self.assertEqual(int(rep2.get("applied") or 0), 0)
        self.assertEqual(self._dept(), original, "撤销后重放不得再套用，值应保持原值")


if __name__ == "__main__":
    unittest.main()
