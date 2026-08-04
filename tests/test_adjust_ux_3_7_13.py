# -*- coding: utf-8 -*-
"""3.7.13 A2/B2：数据修正列表 join SO/客户/销售；同键新生效撤销旧过期疑似。"""
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


class TestListAdjustmentsContext(unittest.TestCase):
    """A2：list_adjustments 带 订单号/客户/销售。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = "数据"
        self.cfg["db_path"] = "看板.db"
        self.conn = db.connect(self.cfg, self.tmp)
        schema.create_all(self.conn)
        fen = money.yuan_to_fen(1000) or 100000
        self.conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,项目经理,"
            "整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)",
            (
                "SOD-A2",
                "SO-A2-001",
                "客户甲",
                "语言",
                "销售甲",
                "PM甲",
                "2026-06-01",
                fen,
                10000,
                "2026-06",
                "2026-06-01",
                "2026-06",
            ),
        )
        self.conn.commit()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def test_list_includes_so_customer_sales(self):
        aid = db.add_adjustment(
            self.conn, "测", "std_收入明细", "SOD-A2", "交付额", "2000", "对账改", "改值"
        )
        self.assertGreater(aid, 0)
        rows = db.list_adjustments(self.conn)
        hit = next(r for r in rows if int(r["id"]) == int(aid))
        self.assertEqual(hit.get("订单号"), "SO-A2-001")
        self.assertEqual(hit.get("客户"), "客户甲")
        self.assertEqual(hit.get("销售"), "销售甲")
        self.assertEqual(hit.get("定位键"), "SOD-A2")
        self.assertEqual(hit.get("原因"), "对账改")
        self.assertIn("字段", hit)


class TestB2RevokeExpiredOnNewEffective(unittest.TestCase):
    """B2：同(表,定位键,字段) 新生效时，旧过期疑似 → 已撤销。"""

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
            ("KEY_B2", "07", "2026-07-01", fen, "语言", "管理费用", "办公费", "行政", "2026-07", "2026-07"),
        )
        self.conn.commit()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def test_new_effective_revokes_same_key_expired(self):
        self.conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES('t0','u','std_费用明细','KEY_B2','预算归属部门','行政','旧值','旧','改值','过期疑似')"
        )
        self.conn.commit()
        exp_id = self.conn.execute(
            "SELECT id FROM adj_调整记录 WHERE 定位键='KEY_B2' AND 状态='过期疑似'"
        ).fetchone()[0]

        new_id = db.add_adjustment(
            self.conn, "测", "std_费用明细", "KEY_B2", "预算归属部门", "数据部", "新改", "改值"
        )
        self.assertIsNotNone(new_id)
        st = self.conn.execute(
            "SELECT 状态 FROM adj_调整记录 WHERE id=?", (exp_id,)
        ).fetchone()[0]
        self.assertEqual(st, "已撤销", "同键新生效应撤销旧过期疑似")
        st_new = self.conn.execute(
            "SELECT 状态 FROM adj_调整记录 WHERE id=?", (new_id,)
        ).fetchone()[0]
        self.assertEqual(st_new, "生效")

    def test_other_key_expired_untouched(self):
        self.conn.execute(
            "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
            "预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            ("KEY_OTHER", "07", "2026-07-02", 10000, "语言", "管理费用", "办公费", "行政", "2026-07", "2026-07"),
        )
        self.conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES('t0','u','std_费用明细','KEY_OTHER','预算归属部门','行政','他键','x','改值','过期疑似')"
        )
        self.conn.commit()
        other_id = self.conn.execute(
            "SELECT id FROM adj_调整记录 WHERE 定位键='KEY_OTHER'"
        ).fetchone()[0]
        db.add_adjustment(
            self.conn, "测", "std_费用明细", "KEY_B2", "预算归属部门", "产品部", "y", "改值"
        )
        st = self.conn.execute(
            "SELECT 状态 FROM adj_调整记录 WHERE id=?", (other_id,)
        ).fetchone()[0]
        self.assertEqual(st, "过期疑似", "不同定位键的过期疑似不得被误撤")

    def test_batch_also_revokes_expired(self):
        self.conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES('t0','u','std_费用明细','KEY_B2','预算归属部门','行政','旧','b','改值','过期疑似')"
        )
        self.conn.commit()
        exp_id = self.conn.execute(
            "SELECT id FROM adj_调整记录 WHERE 定位键='KEY_B2' AND 状态='过期疑似'"
        ).fetchone()[0]
        ids = db.add_adjustments_batch(
            self.conn, "测", "std_费用明细", ["KEY_B2"], "预算归属部门", "新部", "批量", "改值"
        )
        self.assertEqual(len(ids), 1)
        st = self.conn.execute(
            "SELECT 状态 FROM adj_调整记录 WHERE id=?", (exp_id,)
        ).fetchone()[0]
        self.assertEqual(st, "已撤销")


class TestFrontendUxSourceContract(unittest.TestCase):
    """A3/A4/C1/C2：管理端源码静态契约（禁连点、高亮、过期人话、原值说明）。"""

    def test_detail_view_save_guard_and_highlight_and_c2(self):
        src = (ROOT / "frontend/src/admin/views/DetailView.vue").read_text(encoding="utf-8")
        self.assertIn("saving", src)
        self.assertIn(":disabled", src)
        # 成功提示须在 await 保存之后（recompute 在服务端 with_write_lock 内完成）
        self.assertRegex(src, r"await jpost\([\s\S]*?ElMessage\.success")
        self.assertIn("highlight", src.lower())
        self.assertIn("原值_", src)
        self.assertTrue(
            "智云" in src or "底稿" in src,
            "C2 须说明原值_* 为智云底稿",
        )

    def test_ledger_view_a2_a4(self):
        src = (ROOT / "frontend/src/admin/views/LedgerView.vue").read_text(encoding="utf-8")
        self.assertIn("订单号", src)
        self.assertIn("客户", src)
        self.assertIn("销售", src)
        self.assertIn("定位键", src)
        self.assertIn("原因", src)
        # 文本搜索
        self.assertTrue("searchQ" in src or "qSearch" in src or "filterQ" in src or "搜" in src)
        self.assertIn("过期疑似", src)
        # 人话：源头/撤销/坚持
        self.assertTrue("源头" in src or "认可" in src)


if __name__ == "__main__":
    unittest.main()
