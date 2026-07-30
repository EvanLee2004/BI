# -*- coding: utf-8 -*-
"""3.4.3 重点客户经营作战台：贡献/临界/三池/结构条/趋势摘要契约。

驱动真实 domain compute + packer；禁止 re-implement 业务公式。
"""
from __future__ import annotations

import datetime
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fen_wan(wan: float) -> int:
    return int(round(float(wan) * 10_000 * 100))


COLS = {"order_amount": "下单预估额", "order_date": "下单日期"}


def _row(name: str, fen: int, month: int, year: int = 2026, sales: str = "甲") -> dict:
    return {
        "客户": name,
        "销售": sales,
        "下单预估额": fen,
        "下单日期": f"{year}-{month:02d}-15",
    }


class TestNearUpgradeBoundaries(unittest.TestCase):
    def test_exactly_10pct_counts_and_one_fen_over_not(self):
        from domain.key_customers import (
            gap_to_next_fen,
            grade_ytd_fen,
            is_near_upgrade,
            near_gap_threshold_fen,
        )

        # A → S floor 200万；阈值 20万
        self.assertEqual(near_gap_threshold_fen("A"), _fen_wan(20))
        y_exact = _fen_wan(180)  # gap=20万 == 10%
        self.assertEqual(grade_ytd_fen(y_exact), "A")
        self.assertEqual(gap_to_next_fen(y_exact, "A"), _fen_wan(20))
        self.assertTrue(is_near_upgrade(y_exact, "A"))

        y_over = _fen_wan(180) - 1  # gap = 20万 +1 分
        self.assertEqual(grade_ytd_fen(y_over), "A")
        self.assertEqual(gap_to_next_fen(y_over, "A"), _fen_wan(20) + 1)
        self.assertFalse(is_near_upgrade(y_over, "A"))

        # 达门槛已升 S，不算临界
        y_s = _fen_wan(200)
        self.assertEqual(grade_ytd_fen(y_s), "S")
        self.assertFalse(is_near_upgrade(y_s, "S"))
        self.assertIsNone(gap_to_next_fen(y_s, "S"))

        # E → D floor 3万；阈值 0.3万
        y_e = _fen_wan(2.7)
        self.assertEqual(grade_ytd_fen(y_e), "E")
        self.assertTrue(is_near_upgrade(y_e, "E"))
        self.assertFalse(is_near_upgrade(y_e - 1, "E"))

    def test_s_never_near(self):
        from domain.key_customers import is_near_upgrade

        self.assertFalse(is_near_upgrade(_fen_wan(500), "S"))
        self.assertFalse(is_near_upgrade(_fen_wan(200), "S"))


class TestWarDeskSummary(unittest.TestCase):
    def test_focus_contrib_silent_near_counts(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        # today 7-15：已过 1..6；静默看 5、6 月
        today = datetime.date(2026, 7, 15)
        rows = [
            # S 250万 · 5/6 有单 · 不静默
            _row("S活", _fen_wan(250), 5),
            # A 180万临界 · 仅 1 月有单 → 5/6=0 静默
            _row("A临界静", _fen_wan(180), 1),
            # B 50万 · 活跃
            _row("B活", _fen_wan(50), 6),
            # C 15万 · 不进 silent_focus
            _row("C静", _fen_wan(15), 1),
            # E 2.7万 临界
            _row("E临界", _fen_wan(2.7), 3),
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=today)
        wd = raw["war_desk"]
        focus_amt = _fen_wan(250) + _fen_wan(180) + _fen_wan(50)
        self.assertEqual(wd["focus_amount"], focus_amt)
        self.assertEqual(wd["total_amount"], focus_amt + _fen_wan(15) + _fen_wan(2.7))
        # silent focus: A临界静 only（S/B 活跃）
        self.assertEqual(wd["silent_focus_count"], 1)
        # near: A临界静 + E临界
        self.assertEqual(wd["near_upgrade_count"], 2)

        vm = pack_key_customers(raw, embed_full=True)
        sc = vm["summary_cards"]
        self.assertEqual(sc["total"]["count"], 5)
        self.assertIn("户", sc["total"]["value_disp"])
        self.assertIn("万", sc["total"]["value_disp"])
        # 贡献率 = focus/total
        expected_pct = f"{focus_amt / wd['total_amount'] * 100:.1f}%"
        self.assertEqual(sc["focus_contrib"]["pct_disp"], expected_pct)
        self.assertEqual(sc["focus_contrib"]["value_disp"], expected_pct)
        self.assertEqual(sc["silent_focus"]["count"], 1)
        self.assertEqual(sc["near_upgrade"]["count"], 2)
        self.assertIn("10%", sc["near_upgrade"]["tip"])

    def test_structure_bars_conserve_six_tiers(self):
        from domain.key_customers import TIER_ORDER, compute_key_customers
        from viewmodels.packers import pack_key_customers

        rows = [
            _row("S1", _fen_wan(250), 1),
            _row("A1", _fen_wan(100), 2),
            _row("B1", _fen_wan(50), 3),
            _row("C1", _fen_wan(15), 4),
            _row("D1", _fen_wan(5), 5),
            _row("E1", _fen_wan(1), 6),
            _row("E2", _fen_wan(2), 7),
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=datetime.date(2026, 8, 1))
        vm = pack_key_customers(raw, embed_full=False)
        bars = vm["structure_bars"]
        self.assertEqual(len(bars["count"]["segments"]), 6)
        self.assertEqual(len(bars["amount"]["segments"]), 6)
        # 守恒
        sum_c = sum(s["count"] for s in bars["count"]["segments"])
        self.assertEqual(sum_c, raw["totals"]["count"])
        sum_wo_c = sum(s["wo"] for s in bars["count"]["segments"])
        self.assertAlmostEqual(sum_wo_c, 100.0, places=1)
        sum_wo_a = sum(s["wo"] for s in bars["amount"]["segments"])
        self.assertAlmostEqual(sum_wo_a, 100.0, places=1)
        # 与原六档 count/amount 一致
        by_id = {t["id"]: t for t in vm["tiers"]}
        for i, tid in enumerate(TIER_ORDER):
            self.assertEqual(bars["count"]["segments"][i]["id"], tid)
            self.assertEqual(bars["count"]["segments"][i]["count"], by_id[tid]["count"])
            self.assertEqual(bars["amount"]["segments"][i]["amount_disp"], by_id[tid]["amount_disp"])
        # 兼容 pie 仍在
        self.assertEqual(sum(vm["pie_count"]["values"]), raw["totals"]["count"])

    def test_three_pools_mapping(self):
        from domain.key_customers import pool_for_tier
        from viewmodels.packers import pack_key_customers
        from domain.key_customers import compute_key_customers

        self.assertEqual(pool_for_tier("S"), "focus")
        self.assertEqual(pool_for_tier("A"), "focus")
        self.assertEqual(pool_for_tier("B"), "focus")
        self.assertEqual(pool_for_tier("C"), "nurture")
        self.assertEqual(pool_for_tier("D"), "nurture")
        self.assertEqual(pool_for_tier("E"), "longtail")

        rows = [
            _row("S1", _fen_wan(250), 1),
            _row("C1", _fen_wan(15), 2),
            _row("E1", _fen_wan(1), 3),
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=datetime.date(2026, 6, 1))
        vm = pack_key_customers(raw, embed_full=True)
        self.assertEqual(vm["default_pool"], "focus")
        by_p = {p["id"]: p for p in vm["pools"]}
        self.assertEqual(by_p["focus"]["count"], 1)
        self.assertEqual(by_p["nurture"]["count"], 1)
        self.assertEqual(by_p["longtail"]["count"], 1)
        self.assertEqual(by_p["focus"]["tiers"], ["S", "A", "B"])
        # items 带 tier/pool
        s_items = next(t["items"] for t in vm["tiers"] if t["id"] == "S")
        self.assertEqual(s_items[0]["tier"], "S")
        self.assertEqual(s_items[0]["pool"], "focus")


class TestSortAndActionQueues(unittest.TestCase):
    def test_silent_and_near_sort_keys(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        today = datetime.date(2026, 7, 15)
        rows = [
            # 静默重点（仅 1 月有单 → 5/6 为 0）
            _row("静S", _fen_wan(220), 1),
            _row("静A大", _fen_wan(150), 1),
            _row("静A小", _fen_wan(90), 1),
            # 临界但不静默：5/6 月有单
            _row("近A", _fen_wan(100), 5),
            _row("近A", _fen_wan(85), 6),  # ytd=185 · gap 15万
            _row("远A", _fen_wan(100), 5),
            _row("远A", _fen_wan(81), 6),  # ytd=181 · gap 19万
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=today)
        vm = pack_key_customers(raw, embed_full=True)
        silent_names = [x["name"] for x in vm["action_queues"]["silent"]]
        # 等级 S→E，同档金额降序：静S, 静A大, 静A小
        self.assertEqual(silent_names, ["静S", "静A大", "静A小"])

        near = vm["action_queues"]["near"]
        near_names = [x["name"] for x in near]
        # gap 升序：近A(15) 先于 远A(19)
        self.assertIn("近A", near_names)
        self.assertIn("远A", near_names)
        self.assertLess(near_names.index("近A"), near_names.index("远A"))

        # 行字段：status / gap
        items_a = next(t["items"] for t in vm["tiers"] if t["id"] == "A")
        near_it = next(it for it in items_a if it["name"] == "近A")
        self.assertTrue(near_it["near_upgrade"])
        self.assertIsNotNone(near_it["gap_fen"])
        self.assertIn("万", near_it["gap_disp"])
        self.assertTrue(near_it["status_disp"])


class TestTrendSummary(unittest.TestCase):
    def test_peak_avg_recent_silent_months(self):
        from domain.key_customers import month_trend_summary

        today = datetime.date(2026, 7, 15)  # 完整月 1..6
        months = [10, 30, 20, 0, 0, 5, 99, 0, 0, 0, 0, 0]  # 分任意
        # 放大到有意义分值
        months = [m * 1_000_000 for m in months]
        t = month_trend_summary(months, 2026, today)
        self.assertEqual(t["complete_month_count"], 6)
        self.assertEqual(t["peak_month"], 2)  # 30
        self.assertEqual(t["peak_fen"], 30_000_000)
        self.assertEqual(t["incomplete_month"], 7)
        # 近两完整月 5=0, 6=5 → up
        self.assertEqual(t["recent_trend"], "up")
        # 从末尾连续 0：月6非0 → 0
        self.assertEqual(t["consecutive_silent_complete"], 0)

        months2 = [1, 1, 1, 1, 0, 0] + [0] * 6
        months2 = [m * 1_000_000 for m in months2]
        t2 = month_trend_summary(months2, 2026, today)
        self.assertEqual(t2["recent_trend"], "flat")  # 5=0,6=0
        self.assertEqual(t2["consecutive_silent_complete"], 2)

        # 1 月：无可比
        t3 = month_trend_summary([0] * 12, 2026, datetime.date(2026, 1, 20))
        self.assertEqual(t3["complete_month_count"], 0)
        self.assertEqual(t3["recent_trend"], "none")

    def test_packer_trend_disp_on_item(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        today = datetime.date(2026, 7, 15)
        rows = [
            _row("趋客", _fen_wan(40), 2),
            _row("趋客", _fen_wan(10), 6),
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=today)
        vm = pack_key_customers(raw, embed_full=True)
        it = raw["tiers"]["A"]["items"][0] if raw["tiers"]["A"]["items"] else raw["tiers"]["B"]["items"][0]
        # pack
        items = []
        for t in vm["tiers"]:
            items.extend(t["items"])
        packed = next(x for x in items if x["name"] == "趋客")
        tr = packed["trend"]
        self.assertIn("peak_disp", tr)
        self.assertIn("avg_disp", tr)
        self.assertIn("recent_disp", tr)
        self.assertIn("silent_complete_disp", tr)
        self.assertTrue(tr["incomplete_hint"])


class TestDefaultNoSelectAndCompareMax(unittest.TestCase):
    def test_vm_compare_max_and_guide(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        raw = compute_key_customers(
            [_row("K", _fen_wan(100), 1)],
            2026,
            COLS,
            today=datetime.date(2026, 5, 1),
        )
        vm = pack_key_customers(raw)
        self.assertEqual(vm["compare_max"], 5)  # 3.6.0：最多五客
        self.assertEqual(vm["default_pool"], "focus")
        self.assertTrue(vm.get("guide_text"))
        # 前端结构守卫：源码不得默认选中第一户（3.5.0 实现在 composable + key-customers/）
        parts = [
            ROOT / "frontend/src/components/KeyCustomersPanel.vue",
            ROOT / "frontend/src/components/key-customers/KeyCustomersPanel.vue",
            ROOT / "frontend/src/composables/useKeyCustomers.ts",
        ]
        src = "\n".join(p.read_text(encoding="utf-8") for p in parts if p.is_file())
        self.assertIn("selectedKey", src)
        self.assertNotRegex(
            src,
            r"selectedKey\.value\s*=\s*itemKey\(.*items\[0\]",
            "禁止默认选中第一户",
        )
        self.assertIn("compare_max", src.lower() or src)
        # 比较上限 3 的人话提示须存在
        self.assertTrue(
            "对比" in src or "比较" in src,
            "须有加入对比交互",
        )


class TestFrontendWarDeskStructure(unittest.TestCase):
    def test_panel_has_war_desk_dom_hooks(self):
        kc_dir = ROOT / "frontend/src/components/key-customers"
        parts = [ROOT / "frontend/src/components/KeyCustomersPanel.vue"]
        if kc_dir.is_dir():
            parts.extend(sorted(kc_dir.glob("*.vue")))
        src = "\n".join(p.read_text(encoding="utf-8") for p in parts if p.is_file())
        css = (
            ROOT / "frontend/src/styles/components/KeyCustomersPanel.css"
        ).read_text(encoding="utf-8")
        for needle in (
            "kc-summary-cards",
            "kc-structure-bars",
            "kc-pool",
            "kc-insight",
            "kc-action-queue",
            "data-testid=\"kc-summary-cards\"",
            "data-testid=\"kc-structure-bars\"",
            "需跟进",
            "临界晋级",
        ):
            self.assertIn(needle, src, f"missing in vue: {needle}")
        # 禁止双饼主区
        self.assertNotIn('data-testid="kc-pies"', src)
        self.assertIn("kc-workbench", css)
        # 无业务 vue style
        self.assertNotRegex(src, r"<style\b")


class TestSnapshotEmbedStillFull(unittest.TestCase):
    def test_embed_full_has_lazy_items_and_structure(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        rows = [
            _row("S1", _fen_wan(250), 1),
            _row("C1", _fen_wan(15), 2),
            _row("E1", _fen_wan(1), 3),
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=datetime.date(2026, 6, 1))
        full = pack_key_customers(raw, embed_full=True)
        by = {t["id"]: t for t in full["tiers"]}
        self.assertFalse(by["C"]["lazy"])
        self.assertEqual(len(by["C"]["items"]), 1)
        self.assertIn("structure_bars", full)
        self.assertIn("summary_cards", full)
        for it in by["C"]["items"]:
            self.assertIn("trend", it)
            self.assertIn(it["mkey"], full["monthly"])


if __name__ == "__main__":
    unittest.main()
