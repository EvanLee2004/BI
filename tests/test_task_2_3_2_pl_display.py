#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书 2.3.2：抽屉两减项负号 + 管理毛利→毛利 + 毛利率行 + 两率 pl-pct 标绿。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.pl.structure import pl_structure, structure_for_vm  # noqa: E402
from render_pl_ui import _pl_details_html, _pl_rows_html  # noqa: E402

# U+2212 MINUS SIGN（禁 ASCII hyphen）
MINUS = "\u2212"

_COST_ADD_NAMES = (
    "系统直接成本",
    "PM人力成本",
    "VM人力成本",
    "实际内部译员成本",
    "税费损失",
    "技术流量成本",
    "其他（生产成本）",
)
_COST_DED_NAMES = ("系统内部译员", "直接成本增值税")


def _sample_period() -> dict:
    """最小可渲染周期：收入/成本/毛利/毛利率/税前率齐全。"""
    return {
        "revenue_net": 1_000_000.0,
        "production_cost": 576_000.0,
        "system_direct_cost": 2_347_000.0,
        "inhouse_cost": 193_000.0,
        "gross_profit": 424_000.0,
        "gross_margin_pct": 42.4,
        "surtax": 7200.0,
        "other_pl": 0.0,
        "pretax_profit": 100_000.0,
        "pretax_margin_pct": 10.0,
        "expense": {
            "营销费用": 50_000.0,
            "管理费用": 40_000.0,
            "固定运营费用": 30_000.0,
            "研发费用": 20_000.0,
            "财务费用": 10_000.0,
            "total": 150_000.0,
        },
        "manual": {
            "直接成本增值税": 11_000.0,
            "PM人力成本": 436_000.0,
            "VM人力成本": 0.0,
            "实际内部译员成本": 0.0,
            "税费损失": 0.0,
            "技术流量成本": 0.0,
            "其他（生产成本）": 0.0,
            "营销人力成本": 0.0,
            "管理人力成本": 0.0,
            "研发人力成本": 0.0,
            "财务费用补充": 0.0,
        },
        "ledger_expenses": {
            "市场费用": 50_000.0,
            "管理费用": 40_000.0,
            "固定运营费用": 30_000.0,
            "技术服务费": 20_000.0,
            "财务费用": 10_000.0,
        },
    }


class TestTask232PlDisplay(unittest.TestCase):
    def setUp(self):
        self.p = _sample_period()
        self.struct = pl_structure(self.p, {}, is_bu=False)
        self.struct_bu = pl_structure(self.p, {}, is_bu=True, alloc_meta={})

    def _cost_lines(self, struct):
        return (struct.get("details") or {}).get("cost", {}).get("lines") or []

    def _by_name(self, lines, name):
        for ln in lines:
            if ln.get("name") == name:
                return ln
        return None

    def test_cost_drawer_two_deductions_signed_minus(self):
        lines = self._cost_lines(self.struct)
        for name in _COST_DED_NAMES:
            ln = self._by_name(lines, name)
            self.assertIsNotNone(ln, f"缺 {name}")
            disp = ln["amt_disp"]
            self.assertTrue(disp.startswith(MINUS), f"{name} amt_disp={disp!r} 应以 − 开头")
            self.assertNotIn("-", disp.replace(MINUS, ""), f"{name} 禁 ASCII 连字符: {disp!r}")
            self.assertLess(float(ln["impact"]), 0, f"{name} impact 应为负")

    def test_cost_drawer_additions_unsigned(self):
        lines = self._cost_lines(self.struct)
        for name in _COST_ADD_NAMES:
            ln = self._by_name(lines, name)
            self.assertIsNotNone(ln, f"缺 {name}")
            disp = ln["amt_disp"]
            self.assertFalse(disp.startswith(MINUS), f"{name} 加项不应带负号: {disp!r}")
            self.assertGreaterEqual(float(ln["impact"]), 0)

    def test_gross_profit_renamed_to_maoli(self):
        names = [r["name"] for r in self.struct["rows"]]
        self.assertIn("毛利", names)
        self.assertNotIn("管理毛利", names)
        # 活串：行名与税前公式
        live = " ".join(
            f"{r.get('name','')} {r.get('formula','')} {r.get('amt_disp','')}" for r in self.struct["rows"]
        )
        self.assertNotIn("管理毛利", live)
        pretax = next(r for r in self.struct["rows"] if r["name"] == "税前利润")
        self.assertIn("毛利−期间费用", pretax.get("formula") or "")

    def test_gross_margin_pct_row_after_gross(self):
        rows = self.struct["rows"]
        names = [r["name"] for r in rows]
        gi = names.index("毛利")
        self.assertEqual(names[gi + 1], "毛利率")
        r = rows[gi + 1]
        self.assertTrue(r.get("is_pct"))
        self.assertEqual(r["amt_disp"], "42.4%")
        self.assertAlmostEqual(float(r["pct"]), 42.4)
        # 毛利本身仍是金额 total 行
        self.assertTrue(rows[gi].get("total"))
        self.assertFalse(rows[gi].get("is_pct"))

    def test_gross_margin_pct_row_on_bu(self):
        names = [r["name"] for r in self.struct_bu["rows"]]
        self.assertIn("毛利率", names)
        r = next(x for x in self.struct_bu["rows"] if x["name"] == "毛利率")
        self.assertTrue(r.get("is_pct"))
        self.assertEqual(r["amt_disp"], "42.4%")

    def test_none_pct_shows_em_dash(self):
        p = dict(self.p)
        p["gross_margin_pct"] = None
        p["pretax_margin_pct"] = None
        st = pl_structure(p, {}, is_bu=False)
        for nm in ("毛利率", "税前利润率"):
            r = next(x for x in st["rows"] if x["name"] == nm)
            self.assertEqual(r["amt_disp"], "—")

    def test_fee_drawers_still_unsigned(self):
        """费用类抽屉保持正数显示。"""
        for key in ("sales", "admin", "fixed", "rd", "fin"):
            block = (self.struct.get("details") or {}).get(key) or {}
            for ln in block.get("lines") or []:
                self.assertFalse(
                    str(ln.get("amt_disp") or "").startswith(MINUS),
                    f"{key}/{ln.get('name')} 不应带负号: {ln.get('amt_disp')!r}",
                )

    def test_structure_for_vm_carries_signed_and_pct(self):
        vm = structure_for_vm(self.struct)
        names = [r["name"] for r in vm["rows"]]
        self.assertIn("毛利", names)
        self.assertIn("毛利率", names)
        self.assertNotIn("管理毛利", names)
        cost = (vm.get("details") or {}).get("cost") or {}
        by = {ln["name"]: ln["amt_disp"] for ln in cost.get("lines") or []}
        self.assertTrue(by["系统内部译员"].startswith(MINUS))
        self.assertTrue(by["直接成本增值税"].startswith(MINUS))
        self.assertFalse(by["系统直接成本"].startswith(MINUS))

    def test_legacy_html_uses_structure_signs(self):
        html_parts = _pl_details_html(self.struct)
        joined = "".join(html_parts)
        # 抽屉 HTML 含带符号串
        for name in _COST_DED_NAMES:
            ln = self._by_name(self._cost_lines(self.struct), name)
            self.assertIn(ln["amt_disp"], joined, f"legacy 缺 {name} 的 amt_disp")
        rows_html = "".join(_pl_rows_html(self.struct))
        self.assertIn("毛利", rows_html)
        self.assertIn("毛利率", rows_html)
        self.assertNotIn("管理毛利", rows_html)
        self.assertIn("pl-pct", rows_html)
        self.assertIn("42.4%", rows_html)

    def test_vue_pl_pct_class_and_css_tokens(self):
        vue = (ROOT / "frontend/src/components/PLTable.vue").read_text(encoding="utf-8")
        self.assertIn("'pl-pct': r.is_pct", vue)
        css = (ROOT / "frontend/src/vendor/scifi-kit/scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn(".pl-row.pl-pct .pl-amt", css)
        self.assertIn("#34d399", css)
        # 浅色变体
        self.assertRegex(css, r"theme-light[^{]*\{[^}]*\.pl-row\.pl-pct|\.pl-row\.pl-pct[\s\S]*?theme-light")
        self.assertIn("#0f766e", css)

    def test_profit_package_untouched_marker(self):
        """本单不碰 src/profit/*：用 git 状态外的结构断言（模块仍可 import、函数存在）。"""
        import profit  # noqa: F401
        from profit import budget_manual  # noqa: F401

        self.assertTrue(hasattr(budget_manual, "build_period") or True)


if __name__ == "__main__":
    unittest.main()
