#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刀2 测试：调整重放/过期校验 + diff分级/可疑单规则（用构造的唯一键用例，符合验收"造用例"）。
跑：python3 tests/test_adjust_suspect.py"""
import datetime
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import schema, db, profit, loaders  # noqa: E402
from ingest import adjust, suspects  # noqa: E402

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


class TestDiffSuspects(unittest.TestCase):
    def test_period_shift_flagged(self):
        """周期变（归属月跨月）→ 进待确认队列。"""
        conn = _conn()
        _ins_income(conn, "SOD_E", "2026-06-30", 原值月="2026-06")
        old = suspects.snapshot_before_reset(conn)
        schema.reset_std_tables(conn)
        _ins_income(conn, "SOD_E", "2026-07-02", 原值月="2026-07")   # 重抓：周期从6月挪到7月
        r = suspects.detect(conn, old, NOW)
        self.assertEqual(r["period_shift"], 1)
        n = conn.execute("SELECT COUNT(*) FROM suspect_待确认 WHERE 规则='PERIOD_SHIFT'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_amount_change_no_suspect(self):
        """金额变（归属月没变）→ 无人工介入，不入队。"""
        conn = _conn()
        _ins_income(conn, "SOD_F", "2026-06-10", 交付额=1000.0, 原值月="2026-06")
        old = suspects.snapshot_before_reset(conn)
        schema.reset_std_tables(conn)
        _ins_income(conn, "SOD_F", "2026-06-10", 交付额=1200.0, 原值月="2026-06")  # 只金额变
        r = suspects.detect(conn, old, NOW)
        self.assertEqual(r["period_shift"], 0)

    def test_month_edge_night_new_row(self):
        """本次新出现、当月1号交付 → MONTH_EDGE_NIGHT 待确认。"""
        conn = _conn()
        old = suspects.snapshot_before_reset(conn)     # 空
        _ins_income(conn, "SOD_G", "2026-07-01")       # 当月(7月)1号，新出现
        today = datetime.date(2026, 7, 8)
        r = suspects.detect(conn, old, NOW, today=today)
        self.assertEqual(r["month_edge"], 1)

    def test_month_edge_ignores_non_current_month(self):
        conn = _conn()
        old = suspects.snapshot_before_reset(conn)
        _ins_income(conn, "SOD_H", "2026-03-01")       # 1号但非当月
        r = suspects.detect(conn, old, NOW, today=datetime.date(2026, 7, 8))
        self.assertEqual(r["month_edge"], 0)

    def test_resolved_suspect_not_renagged(self):
        """已确认正常的可疑单不再重复入队。"""
        conn = _conn()
        _ins_income(conn, "SOD_I", "2026-07-01")
        conn.execute("INSERT INTO suspect_待确认(发现时间,目标表,定位键,规则,摘要,状态)"
                     " VALUES(?,?,?,?,?,?)", (NOW, "std_收入明细", "SOD_I", "MONTH_EDGE_NIGHT", "x", "已确认正常"))
        conn.commit()
        old = suspects.snapshot_before_reset(conn)   # SOD_I 已在库
        # 新一轮：SOD_I 仍在（不是新出现），且已确认——不该再报
        r = suspects.detect(conn, old, NOW, today=datetime.date(2026, 7, 8))
        self.assertEqual(r["month_edge"], 0)


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
