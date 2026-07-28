#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1 · 2.7.6：packers/VM 关键数字与 api_v1.extract_numbers 契约锁死。

真路径：_golden_data → summary → extract_numbers / pack_kpi / pack_pl / pack_rank / build_cockpit_vm。
只比数字与 *_disp 显示串，不比 HTML 字节/SHA。禁止 mock 被测单元、禁止改算账凑绿。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import api_v1  # noqa: E402
import charts  # noqa: E402
import core  # noqa: E402
import db  # noqa: E402
import ingest  # noqa: E402
import loaders  # noqa: E402
import viewmodels  # noqa: E402
from viewmodels import packers  # noqa: E402

FAKE = ROOT / "_golden_data"

# 全年 KPI 卡 data_key → numbers 字段（毛利率卡大数字是 % 不是 gross_profit 额）
KPI_MONEY_KEYS = ("orders", "revenue_gross", "pretax_profit", "receipts")
PL_NAME_TO_KEY = {
    "交付收入（不含税）": "revenue_net",
    "毛利": "gross_profit",
    "税前利润": "pretax_profit",
}


def _build_summary():
    cfg = dict(loaders.load_config(ROOT))
    cfg["data_dir"] = "_golden_data"
    cfg["db_path"] = "看板.db"
    cfg["zhiyun_auto_fetch"] = False
    cfg["period_pin"] = {"year": 2026, "month": 7}
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, ROOT)
    try:
        ingest.build_std_db(
            cfg, today.year, conn=conn, today=today, trigger="g1_contract", archive_backups=False
        )
        summary = core.summary_from_conn(cfg, conn, today)
        for fn in (core.attach_unassigned, core.attach_allocation_to_summary, core.attach_bu_orders):
            try:
                if fn is core.attach_unassigned:
                    fn(cfg, conn, today, summary, ROOT)
                else:
                    fn(cfg, conn, today, summary)
            except TypeError:
                try:
                    fn(cfg, conn, today, summary)
                except Exception:
                    pass
            except Exception:
                pass
    finally:
        conn.close()
    return summary, cfg


def _fen_to_wan_anim(fen_val) -> float:
    """与 packers KPI 中间帧同一换算：分 → 万。"""
    try:
        fen = int(fen_val)
    except (TypeError, ValueError):
        fen = 0
    return (fen / 100.0) / 10000.0


class TestG1VmNumbersContract(unittest.TestCase):
    """全年 KPI / PL / ranking total / trend 样本：VM·packers ↔ extract_numbers。"""

    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cls.summary, cls.cfg = _build_summary()
        cls.numbers = api_v1.extract_numbers(cls.summary)
        cls.yk = cls.numbers.get("meta_year_key") or ""
        if not cls.yk or cls.yk not in (cls.numbers.get("periods") or {}):
            raise unittest.SkipTest(f"无 year_key 周期: {cls.yk!r}")
        cls.n_year = cls.numbers["periods"][cls.yk]
        cls.cards_by = packers.pack_kpi_cards_by_period(cls.summary, cls.cfg)
        cls.pl_by = packers.pack_pl_by_period(cls.summary, is_bu=False)
        cls.rank_by = packers.pack_profit_rank_by_period(cls.summary, embed_full=False)
        cls.vm = viewmodels.build_cockpit_vm(cls.summary, cls.cfg)

    def _card_map(self, period_key: str | None = None) -> dict[str, dict]:
        pk = period_key or self.yk
        cards = self.cards_by.get(pk) or []
        return {c.get("data_key"): c for c in cards if c.get("data_key")}

    # ── KPI ──────────────────────────────────────────────────────────
    def test_year_kpi_money_disp_matches_numbers(self):
        """全年 KPI 金额卡 value_disp == charts.fmt_wan(numbers[key])。"""
        cmap = self._card_map()
        for key in KPI_MONEY_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, cmap, f"缺 KPI 卡 data_key={key}")
                raw = self.n_year.get(key)
                self.assertIsNotNone(raw, f"numbers 缺 {key}")
                exp_disp = charts.fmt_wan(raw)
                self.assertEqual(
                    cmap[key].get("value_disp"),
                    exp_disp,
                    f"{key}: packers disp={cmap[key].get('value_disp')!r} vs numbers→{exp_disp!r}",
                )
                # 中间帧 value 与分→万 同口径
                self.assertAlmostEqual(
                    float(cmap[key].get("value") or 0),
                    _fen_to_wan_anim(raw),
                    places=4,
                    msg=f"{key} anim value 与 numbers 分→万不一致",
                )

    def test_year_kpi_revenue_net_sub_matches_numbers(self):
        """交付金额副行「不含税」数值 = revenue_net 的 *_disp。"""
        card = self._card_map().get("revenue_gross") or {}
        subs = card.get("subs") or []
        net_sub = next((s for s in subs if "不含税" in str(s.get("label") or "")), None)
        self.assertIsNotNone(net_sub, f"缺不含税副行: {subs}")
        exp = charts.fmt_wan(self.n_year.get("revenue_net")) + "万"
        self.assertEqual(net_sub.get("value_disp"), exp)

    def test_year_kpi_margin_pct_matches_numbers(self):
        """毛利率卡大数字 = numbers.gross_margin_pct（一位小数显示）。"""
        card = self._card_map().get("gross_profit") or {}
        pct = float(self.n_year.get("gross_margin_pct") or 0.0)
        self.assertEqual(card.get("value_unit"), "%")
        self.assertAlmostEqual(float(card.get("value") or 0), pct, places=4)
        # value_disp 为一位小数串
        self.assertEqual(card.get("value_disp"), f"{pct:.1f}")

    def test_vm_kpi_same_as_packers(self):
        """build_cockpit_vm.kpi.cards_by_period 与 pack_kpi 同源。"""
        vm_cards = (self.vm.kpi.cards_by_period or {}).get(self.yk) or []
        pack_cards = self.cards_by.get(self.yk) or []
        self.assertEqual(len(vm_cards), len(pack_cards))
        for a, b in zip(vm_cards, pack_cards):
            self.assertEqual(a.get("data_key"), b.get("data_key"))
            self.assertEqual(a.get("value_disp"), b.get("value_disp"))
            self.assertEqual(a.get("value"), b.get("value"))

    # ── PL ───────────────────────────────────────────────────────────
    def test_year_pl_key_rows_match_numbers(self):
        """PL 关键行 amt_disp 与 numbers 对应金额 fmt 一致。"""
        table = self.pl_by.get(self.yk) or {}
        rows = table.get("rows") or []
        by_name = {r.get("name"): r for r in rows}
        for name, key in PL_NAME_TO_KEY.items():
            with self.subTest(name=name):
                self.assertIn(name, by_name, f"PL 缺行 {name}；有 {list(by_name)[:15]}")
                raw = self.n_year.get(key)
                exp = charts.fmt_wan(raw) + "万"
                self.assertEqual(
                    by_name[name].get("amt_disp"),
                    exp,
                    f"PL {name}: got {by_name[name].get('amt_disp')!r} exp {exp!r}",
                )

    def test_vm_pl_same_as_packers(self):
        vm_rows = ((self.vm.pl.table_by_period or {}).get(self.yk) or {}).get("rows") or []
        pack_rows = (self.pl_by.get(self.yk) or {}).get("rows") or []
        self.assertEqual(
            [(r.get("name"), r.get("amt_disp")) for r in vm_rows],
            [(r.get("name"), r.get("amt_disp")) for r in pack_rows],
        )

    # ── ranking total ────────────────────────────────────────────────
    def test_year_ranking_totals_and_conc(self):
        """profit_rankings_totals 与 pack 侧 conc / 首条 revenue_disp 一致。"""
        prt = self.n_year.get("profit_rankings_totals") or {}
        packed = self.rank_by.get(self.yk) or {}
        # raw summary 侧
        raw_pr = ((self.summary.get("periods") or {}).get(self.yk) or {}).get("profit_rankings") or {}

        for dim_key, side in (("revenue_by_customer", "customer"), ("revenue_by_sales", "sales")):
            with self.subTest(side=side):
                tot = prt.get(dim_key) or {}
                side_pack = packed.get(side) or {}
                if tot.get("n_items", 0) == 0 and side_pack.get("empty"):
                    continue
                # conc_pct 出现在 conc_disp
                c = tot.get("conc_pct")
                if c is not None:
                    self.assertIn(f"{c:.1f}%", str(side_pack.get("conc_disp") or ""))
                # 首条 revenue_disp 与 raw items[0].revenue
                raw_blk = raw_pr.get(dim_key) or {}
                items = raw_blk.get("items") or []
                pack_items = side_pack.get("items") or []
                if items and pack_items:
                    exp0 = charts.fmt_wan(items[0].get("revenue") or 0) + "万"
                    self.assertEqual(pack_items[0].get("revenue_disp"), exp0)
                # total_revenue 守恒：top items + others ≈ total（分）
                total_rev = tot.get("total_revenue")
                if total_rev is not None and items:
                    s = sum(float(it.get("revenue") or 0) for it in items)
                    others = raw_blk.get("others") or {}
                    s += float(others.get("revenue") or 0)
                    # full_items 若比 items 更全，用 full 对 total
                    full = raw_blk.get("full_items") or []
                    if full:
                        s_full = sum(float(it.get("revenue") or 0) for it in full)
                        self.assertEqual(
                            int(s_full),
                            int(total_rev),
                            f"{side} full_items 合计 {s_full} != total_revenue {total_rev}",
                        )
                    else:
                        self.assertEqual(
                            int(s),
                            int(total_rev),
                            f"{side} items+others 合计 {s} != total_revenue {total_rev}",
                        )

    def test_vm_rank_conc_matches_numbers(self):
        vm_pr = (self.vm.rankings.profit_rank_by_period or {}).get(self.yk) or {}
        prt = self.n_year.get("profit_rankings_totals") or {}
        for dim_key, side in (("revenue_by_customer", "customer"), ("revenue_by_sales", "sales")):
            c = (prt.get(dim_key) or {}).get("conc_pct")
            if c is None:
                continue
            disp = ((vm_pr.get(side) or {}).get("conc_disp")) or ""
            self.assertIn(f"{c:.1f}%", disp)

    # ── trend 样本点 ─────────────────────────────────────────────────
    def test_trend_sample_matches_numbers(self):
        """trend 至少 1 个样本点：数值与 *_disp 对齐 numbers/summary.trend。"""
        raw_trend = self.numbers.get("trend") or self.summary.get("trend") or []
        self.assertTrue(raw_trend, "summary/numbers 无 trend")
        # 取第 1 个与中间（若有）样本
        idxs = [0]
        if len(raw_trend) >= 3:
            idxs.append(len(raw_trend) // 2)
        vm_tr = self.vm.trend
        for i in idxs:
            row = raw_trend[i]
            self.assertTrue(row and len(row) >= 4, f"trend[{i}] 残缺: {row!r}")
            lab, r, c, m = row[0], float(row[1] or 0), float(row[2] or 0), float(row[3] or 0)
            with self.subTest(i=i, lab=lab):
                self.assertEqual(vm_tr.labels[i], str(lab))
                self.assertEqual(float(vm_tr.revenue[i]), r)
                self.assertEqual(float(vm_tr.cost[i]), c)
                self.assertAlmostEqual(float(vm_tr.margin_pct[i]), m, places=4)
                self.assertEqual(vm_tr.revenue_disp[i], charts.fmt_wan(r))
                self.assertEqual(vm_tr.cost_disp[i], charts.fmt_wan(c))
                self.assertEqual(vm_tr.margin_pct_disp[i], f"{m:.1f}%")

    def test_vm_numbers_tree_equals_extract(self):
        """VM.numbers 与 extract_numbers 全等（装配不得另算）。"""
        self.assertEqual(self.vm.numbers.get("meta_year_key"), self.numbers.get("meta_year_key"))
        self.assertEqual(self.vm.numbers.get("period_keys"), self.numbers.get("period_keys"))
        # 全年关键 KPI 键逐项
        for k in KPI_MONEY_KEYS + ("revenue_net", "gross_profit", "gross_margin_pct"):
            self.assertEqual(
                (self.vm.numbers.get("periods") or {}).get(self.yk, {}).get(k),
                self.n_year.get(k),
                f"vm.numbers[{k}] 漂移",
            )

    # ── 禁新 HTML 架构锁（本文件：不比 HTML 字节）────────────────────
    def test_this_file_compares_numbers_not_html_bytes(self):
        lines = Path(__file__).read_text(encoding="utf-8").splitlines()
        code_imports = [
            ln.strip()
            for ln in lines
            if ln.strip().startswith(("import ", "from ")) and not ln.strip().startswith("#")
        ]
        for ln in code_imports:
            self.assertNotIn("hashlib", ln)
        # 真断言路径只用 cards_by_period / table_by_period / profit_rank / trend，不用 HTML body
        self.assertTrue(any("pack_kpi_cards_by_period" in ln for ln in lines))
        self.assertTrue(any("extract_numbers" in ln for ln in lines))
        self.assertFalse(any(ln.strip().startswith("import render") for ln in lines))


class TestG1NoNewHtmlShaInGoalDiff(unittest.TestCase):
    """G1 新增测不得引入 HTML 字节/固化金样架构锁。"""

    def test_g1_test_file_no_hashlib_import(self):
        p = ROOT / "tests" / "test_g1_2_7_6_vm_numbers_contract.py"
        self.assertTrue(p.exists())
        imports = [
            ln.strip()
            for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        self.assertTrue(any("api_v1" in ln for ln in imports))
        self.assertTrue(any("packers" in ln for ln in imports))
        self.assertFalse(any("hashlib" in ln for ln in imports))


if __name__ == "__main__":
    unittest.main()
