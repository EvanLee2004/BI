#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调整重放/过期校验 + R1 全字段可调（黑名单制）测试（用构造的唯一键用例）。
跑：python3 tests/test_adjust.py"""
import datetime
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import schema, db, profit, loaders  # noqa: E402
from ingest import adjust  # noqa: E402

NOW = "2026-07-08 10:00:00"


def _conn():
    c = sqlite3.connect(":memory:")
    schema.create_all(c)
    return c


def _ins_income(conn, 定位键, 交付日期, 交付额=1000.0, 归属月=None, 原值月=None):
    ym = 归属月 or (交付日期[:7] if 交付日期 else None)
    conn.execute(
        "INSERT INTO std_收入明细(定位键,订单号,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
        " VALUES(?,?,?,?,?,?,?,?,0)",
        (定位键, 定位键, 交付日期, 交付额, 0.0, ym, 交付日期, 原值月 or ym))
    conn.commit()


def _add_adj(conn, 目标表, 定位键, 字段, 原值, 新值, 类型="改值", 状态="生效"):
    conn.execute(
        "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (NOW, "明昊", 目标表, 定位键, 字段, 原值, 新值, "测试", 类型, 状态))
    conn.commit()


def _income(conn, 定位键):
    return conn.execute("SELECT 整单交付日期,归属月,已删除 FROM std_收入明细 WHERE 定位键=?", (定位键,)).fetchone()


class TestReplay(unittest.TestCase):
    def test_move_month_survives_refetch(self):
        """核心：挪月调整（0701→0630）加上后，重抓（重建原始值）仍被重放回 6 月。"""
        conn = _conn()
        _ins_income(conn, "SOD_A", "2026-07-01")
        _add_adj(conn, "std_收入明细", "SOD_A", "整单交付日期", "2026-07-01", "2026-06-30")
        r = adjust.apply_adjustments(conn, NOW)
        self.assertEqual(r["applied"], 1)
        d, ym, _ = _income(conn, "SOD_A")
        self.assertEqual(d, "2026-06-30")      # 套用
        self.assertEqual(ym, "2026-06")        # 归属月连带重算到 6 月
        # 模拟重抓：标准表重建成原始值（0701），再重放
        schema.reset_std_tables(conn)
        _ins_income(conn, "SOD_A", "2026-07-01")   # 源头没变，重抓回 0701
        adjust.apply_adjustments(conn, NOW)
        d2, ym2, _ = _income(conn, "SOD_A")
        self.assertEqual(d2, "2026-06-30")     # 调整不丢，仍在 6 月
        self.assertEqual(ym2, "2026-06")

    def test_source_changed_marks_expired(self):
        """改源值→黄牌：重抓后现值与调整原值不符 → 过期疑似、不套用。"""
        conn = _conn()
        _ins_income(conn, "SOD_B", "2026-07-05")   # 源头已从 0701 改到 0705
        _add_adj(conn, "std_收入明细", "SOD_B", "整单交付日期", "2026-07-01", "2026-06-30")
        r = adjust.apply_adjustments(conn, NOW)
        self.assertEqual(r["expired"], 1)
        self.assertEqual(r["applied"], 0)
        d, _, _ = _income(conn, "SOD_B")
        self.assertEqual(d, "2026-07-05")          # 未被套用，保留源值
        st = conn.execute("SELECT 状态 FROM adj_调整记录 WHERE 定位键='SOD_B'").fetchone()[0]
        self.assertEqual(st, "过期疑似")

    def test_remove_soft_deletes(self):
        """剔除：打软删标记（不物理删），已删除=1。"""
        conn = _conn()
        _ins_income(conn, "SOD_C", "2026-06-10")
        _add_adj(conn, "std_收入明细", "SOD_C", "", "", "", 类型="剔除")
        r = adjust.apply_adjustments(conn, NOW)
        self.assertEqual(r["removed"], 1)
        _, _, deleted = _income(conn, "SOD_C")
        self.assertEqual(deleted, 1)

    def test_amount_adjust_applies(self):
        conn = _conn()
        _ins_income(conn, "SOD_D", "2026-06-10", 交付额=1000.0)
        _add_adj(conn, "std_收入明细", "SOD_D", "交付额", "1000", "1500")
        adjust.apply_adjustments(conn, NOW)
        v = conn.execute("SELECT 交付额 FROM std_收入明细 WHERE 定位键='SOD_D'").fetchone()[0]
        self.assertAlmostEqual(v, 1500.0)


def _ins_expense(conn, 定位键, 含税金额=100.0, 预算归属部门="市场部", 归属月="2026-06"):
    conn.execute(
        "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,0)",
        (定位键, 归属月, f"{归属月}-15", 含税金额, "语言", "管理费用", "办公费", 预算归属部门, 归属月, 归属月))
    conn.commit()


class TestAdjustableFieldsBlacklist(unittest.TestCase):
    """R1：可调整字段 = std 表全部列 − 黑名单（id/定位键/归属月/原值_*/已删除）。"""

    def test_blacklist_locked_all_tables(self):
        for t, fields in schema.ADJUSTABLE_FIELDS.items():
            for banned in schema.NON_ADJUSTABLE:
                self.assertNotIn(banned, fields, f"{t} 不应可调 {banned}")
            self.assertFalse(any(f.startswith("原值_") for f in fields), f"{t} 不应可调 原值_* 列")

    def test_all_business_columns_open(self):
        """全部业务列开放：以费用明细为例逐列核对（含新开放的 预算归属部门）。"""
        self.assertEqual(
            set(schema.ADJUSTABLE_FIELDS["std_费用明细"]),
            {"收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"})
        self.assertIn("客户", schema.ADJUSTABLE_FIELDS["std_收入明细"])
        self.assertIn("订单号", schema.ADJUSTABLE_FIELDS["std_下单"])

    def test_new_field_adjust_applies_and_survives_refetch(self):
        """新开放字段（费用明细.预算归属部门）可调整，且重抓（重建原始值）后重放仍生效。"""
        conn = _conn()
        _ins_expense(conn, "LED_A", 预算归属部门="市场部")
        aid = db.add_adjustment(conn, "明昊", "std_费用明细", "LED_A", "预算归属部门", "数据部", "测试R1", "改值")
        self.assertGreater(aid, 0)
        adjust.apply_adjustments(conn, NOW)
        v = conn.execute("SELECT 预算归属部门 FROM std_费用明细 WHERE 定位键='LED_A'").fetchone()[0]
        self.assertEqual(v, "数据部")
        # 模拟重抓：重建回原始值，重放后调整不丢
        schema.reset_std_tables(conn)
        _ins_expense(conn, "LED_A", 预算归属部门="市场部")
        adjust.apply_adjustments(conn, NOW)
        v2 = conn.execute("SELECT 预算归属部门 FROM std_费用明细 WHERE 定位键='LED_A'").fetchone()[0]
        self.assertEqual(v2, "数据部")

    def test_blacklist_field_rejected(self):
        """黑名单字段（id/定位键/归属月/原值_*/已删除）提交调整 → ValueError（接口层转 400）。"""
        conn = _conn()
        _ins_expense(conn, "LED_B")
        for banned in ("定位键", "归属月", "原值_归属月", "已删除", "id"):
            with self.assertRaises(ValueError, msg=f"{banned} 应被拒"):
                db.add_adjustment(conn, "明昊", "std_费用明细", "LED_B", banned, "x", "测试", "改值")

    def test_date_field_still_recomputes_period(self):
        """改日期字段连带重算归属月的既有逻辑保留（黑名单制不破坏 PERIOD_DATE_FIELD）。"""
        conn = _conn()
        _ins_income(conn, "SOD_P", "2026-07-01")
        db.add_adjustment(conn, "明昊", "std_收入明细", "SOD_P", "整单交付日期", "2026-06-30", "挪月", "改值")
        adjust.apply_adjustments(conn, NOW)
        d, ym, _ = _income(conn, "SOD_P")
        self.assertEqual(d, "2026-06-30")
        self.assertEqual(ym, "2026-06")


class TestReplayEndToEnd(unittest.TestCase):
    """全链集成：挪月调整 → std → db读 → profit → 利润表数字从 7 月移到 6 月。"""
    def _summary(self, conn, cfg, today):
        lh, lr = db.load_ledger(cfg, conn)
        return profit.build_summary(
            cfg, db.load_project_detail(cfg, conn), db.load_orders(cfg, conn),
            db.load_receipts(cfg, conn), db.load_inhouse(cfg, conn), lh, lr,
            today.year, today, manual_raw=db.load_manual(cfg, conn))

    def test_move_month_reflected_in_profit(self):
        cfg = loaders.load_config()
        today = datetime.date(2026, 7, 8)
        conn = _conn()
        _ins_income(conn, "SOD_Z", "2026-07-01", 交付额=1060000.0)  # 含税106万→不含税100万
        S0 = self._summary(conn, cfg, today)
        self.assertAlmostEqual(S0["periods"]["2026年7月"]["revenue_net"], 1000000.0, places=0)
        self.assertAlmostEqual(S0["periods"]["2026年6月"]["revenue_net"], 0.0, places=0)
        # 挪月：0701→0630，套用
        _add_adj(conn, "std_收入明细", "SOD_Z", "整单交付日期", "2026-07-01", "2026-06-30")
        adjust.apply_adjustments(conn, NOW)
        S1 = self._summary(conn, cfg, today)
        self.assertAlmostEqual(S1["periods"]["2026年6月"]["revenue_net"], 1000000.0, places=0)  # 到6月
        self.assertAlmostEqual(S1["periods"]["2026年7月"]["revenue_net"], 0.0, places=0)         # 离开7月


if __name__ == "__main__":
    unittest.main(verbosity=2)
