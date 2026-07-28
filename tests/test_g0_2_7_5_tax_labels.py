#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G0 · 2.7.5 口径标注方案 A：交付金额「含税」/副行「不含税 · ÷1.06」/峰值「· 含税」/趋势「收入(不含税)」。

锁装运路径：pack_kpi_cards_by_period（整体+BU 同源）+ TrendChart 源文案。
禁止硬编码整包 golden；禁止 mock 被测单元；禁止改算账凑绿。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import viewmodels  # noqa: E402
from viewmodels import packers  # noqa: E402

FAKE = ROOT / "_golden_data"


class TestG0TaxLabelsPackers(unittest.TestCase):
    """真实调用 pack_kpi_cards_by_period / build_cockpit_vm，断言口径文案。"""

    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "看板.db"
        cfg["zhiyun_auto_fetch"] = False
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            cls.summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        cls.cfg = cfg
        cls.cards_by = packers.pack_kpi_cards_by_period(cls.summary, cfg)
        cls.vm = viewmodels.build_cockpit_vm(cls.summary, cfg)
        cls.yk = cls.vm.year_key or next(iter(cls.cards_by.keys()), "")

    def _revenue_card(self, period_key: str | None = None) -> dict:
        pk = period_key or self.yk
        cards = self.cards_by.get(pk) or []
        for c in cards:
            if c.get("data_key") == "revenue_gross" or c.get("label") == "交付金额":
                return c
        self.fail(f"周期 {pk!r} 无交付金额卡；keys={[c.get('data_key') for c in cards]}")

    def test_delivery_card_hint_hanshui(self):
        """交付金额卡有 hint=含税（小字字段，整体装配路径）。"""
        card = self._revenue_card()
        self.assertEqual(card.get("hint"), "含税", msg=f"card keys={list(card.keys())} card={card}")

    def test_sub_label_buhanshui_div106(self):
        """副行 label 为「不含税 · ÷1.06」（数值仍为后端 revenue_net 的 *_disp）。"""
        card = self._revenue_card()
        subs = card.get("subs") or []
        labels = [s.get("label") for s in subs]
        self.assertTrue(
            any(lab == "不含税 · ÷1.06" for lab in labels),
            msg=f"期望副行「不含税 · ÷1.06」，实际 labels={labels}",
        )
        # 禁止旧文案残留
        self.assertFalse(
            any("交付收入" in str(lab) for lab in labels),
            msg=f"旧副行文案未替换: {labels}",
        )

    def test_peak_foot_contains_month_and_hanshui(self):
        """峰值 feet：label 含月份且含「含税」；与 Vue 前缀「全年峰值 · 」拼后为定稿形态。"""
        card = self._revenue_card()
        feet = card.get("feet") or []
        peaks = [f for f in feet if f.get("kind") == "peak"]
        if not peaks:
            # golden 若全 0 无峰值则跳过（结构仍要求有 feet 机制）；多数周期应有
            self.skipTest("当前周期无 peak feet（数据全 0？）")
        peak = peaks[0]
        lab = str(peak.get("label") or "")
        self.assertIn("含税", lab, msg=f"peak.label 应含「含税」: {peak}")
        # 应保留月份信息（如「3月」或「03月」或「2026年3月」裁剪后的月串）
        self.assertTrue(
            re.search(r"\d+\s*月", lab) or ("月" in lab),
            msg=f"peak.label 应保留月份: {peak}",
        )
        # 与 Vue 拼接后不得叠字「全年峰值 · 全年峰值」
        self.assertNotIn("全年峰值", lab, msg="label 勿自带「全年峰值」（Vue 会前缀）")

    def test_vm_path_same_as_packers(self):
        """build_cockpit_vm 同源：cards 上同样有 hint/副行/峰值文案。"""
        cards = (self.vm.kpi.cards_by_period or {}).get(self.yk) or []
        rev = next((c for c in cards if c.get("data_key") == "revenue_gross"), None)
        self.assertIsNotNone(rev)
        assert rev is not None
        self.assertEqual(rev.get("hint"), "含税")
        sub_labs = [s.get("label") for s in (rev.get("subs") or [])]
        self.assertIn("不含税 · ÷1.06", sub_labs)
        peaks = [f for f in (rev.get("feet") or []) if f.get("kind") == "peak"]
        if peaks:
            self.assertIn("含税", str(peaks[0].get("label") or ""))

    def test_non_revenue_cards_no_hanshui_hint(self):
        """非交付金额卡不应误挂 hint=含税。"""
        cards = self.cards_by.get(self.yk) or []
        for c in cards:
            if c.get("data_key") == "revenue_gross":
                continue
            self.assertNotEqual(c.get("hint"), "含税", msg=f"误挂 hint 的卡: {c.get('label')}")


class TestG0TrendAndFrontendNoDetax(unittest.TestCase):
    """趋势「收入(不含税)」在装运 TrendChart 源；前端无自算 ÷1.06。"""

    def test_trend_chart_source_has_income_ex_tax(self):
        src = (ROOT / "frontend" / "src" / "components" / "TrendChart.vue").read_text(encoding="utf-8")
        self.assertIn("收入(不含税)", src, msg="TrendChart 须含「收入(不含税)」标题/图例/系列名")
        # 至少出现在系列或 legend 语境，不能只是注释
        code_only = "\n".join(
            ln for ln in src.splitlines() if not ln.strip().startswith("*") and not ln.strip().startswith("//")
        )
        self.assertGreaterEqual(code_only.count("收入(不含税)"), 1)

    def test_kpi_cards_renders_hint(self):
        src = (ROOT / "frontend" / "src" / "components" / "KpiCards.vue").read_text(encoding="utf-8")
        self.assertIn("hint", src, msg="KpiCards 须渲染后端 hint（含税小字）")
        self.assertIn("c.hint", src)

    def test_frontend_no_self_div_1_06(self):
        """前端金额展示路径禁止自算 /1.06（展示性「÷1.06」文案与公式说明允许）。"""
        fe = ROOT / "frontend" / "src"
        bad: list[str] = []
        for p in fe.rglob("*"):
            if p.suffix not in {".vue", ".ts", ".js"}:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for i, ln in enumerate(text.splitlines(), 1):
                s = ln.strip()
                if s.startswith("//") or s.startswith("*") or s.startswith("<!--"):
                    continue
                # 运算性除税：标识符/表达式后接 / 1.06（排除 HTML 闭合标签里的 /）
                if re.search(r"[\w)\]\"']\s*/\s*1\.06\b", ln):
                    bad.append(f"{p.relative_to(ROOT)}:{i}:{ln.strip()}")
                if re.search(r"\*\s*\(\s*1\s*/\s*1\.06", ln):
                    bad.append(f"{p.relative_to(ROOT)}:{i}:{ln.strip()}")
        self.assertEqual(bad, [], msg="前端疑似自算÷1.06:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
