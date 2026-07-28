#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G4 · 2.7.9：生产 JSON/VM 路径零 import render；显示辅助在 viewmodels.format。

真路径：
- 静态闸：src/ 业务文件（非 render*.py）无 `import render` / `from render`
- format 辅助与迁前同构（_esc / _rank_amt / attach_monthly）
- rankings_view_for_period / dual 入口不依赖业务侧 import render
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 业务侧禁止的字面模式（与 G4 验收 rg 一致；无词界会命中 render_widgets 等）
_RENDER_IMPORT_RE = re.compile(r"import render|from render")


def _business_py_files() -> list[Path]:
    src = ROOT / "src"
    out = []
    for p in src.rglob("*.py"):
        if p.name.startswith("render") or p.name.startswith("render_"):
            continue
        # render*.py already excluded by name prefix "render"
        if p.name.startswith("render"):
            continue
        out.append(p)
    return sorted(out)


class TestG4NoImportRender(unittest.TestCase):
    """业务代码静态零 import render / from render。"""

    def test_business_src_zero_import_render(self):
        """与验收 `rg "import render|from render" src/ --glob '!render*.py'` 同口径（含注释/文档串）。"""
        hits: list[str] = []
        for path in _business_py_files():
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if _RENDER_IMPORT_RE.search(line):
                    rel = path.relative_to(ROOT)
                    hits.append(f"{rel}:{i}:{line.rstrip()}")
        self.assertEqual(
            hits,
            [],
            "业务 src 仍含 import render|from render（含 render_widgets 等子串命中）:\n"
            + "\n".join(hits[:40]),
        )


class TestG4FormatParity(unittest.TestCase):
    """迁后 format 辅助与 charts.esc / 金额口径等价。"""

    def test_esc_rank_amt_parity(self):
        import charts
        from viewmodels.format import _esc, _rank_amt

        samples = ["", "a&b", '<x "y">', "客户甲"]
        for s in samples:
            self.assertEqual(_esc(s), charts.esc(s), s)
        self.assertEqual(_rank_amt(0), "0.0万")
        self.assertTrue(_rank_amt(12345600).endswith("万"))
        self.assertTrue(_rank_amt(-100).startswith("−"))

    def test_attach_monthly_structure(self):
        from viewmodels.format import _merge_dual_rank, attach_monthly_to_dual

        o_rk = {
            "items": [{"name": "甲", "amount": 100.0}, {"name": "乙", "amount": 50.0}],
            "full_items": [{"name": "甲", "amount": 100.0}, {"name": "乙", "amount": 50.0}],
        }
        r_rk = {
            "items": [{"name": "甲", "amount": 80.0}, {"name": "乙", "amount": 40.0}],
            "full_items": [{"name": "甲", "amount": 80.0}, {"name": "乙", "amount": 40.0}],
        }
        dual = _merge_dual_rank(o_rk, r_rk, top=10)
        store: dict = {}
        out = attach_monthly_to_dual(dual, {"甲": {"order": [1] * 12, "receipt": [2] * 12}}, year=2026, dim="sales", store=store)
        self.assertTrue(out.get("items"))
        self.assertTrue(out["items"][0].get("mkey"))
        self.assertIn(out["items"][0]["mkey"], store)
        self.assertEqual(len(store[out["items"][0]["mkey"]]), 12)
        self.assertIn("order_disp", store[out["items"][0]["mkey"]][0])


class TestG4VmPathNoRenderImport(unittest.TestCase):
    """装运 VM/JSON 入口：rankings_view 含显示字段。"""

    def test_rankings_view_for_period_display_fields(self):
        import api_v1

        period = {
            "range": ("2026-01-01", "2026-01-31"),
            "rankings": {
                "orders_by_sales": {
                    "items": [{"name": "销售A", "amount": 1000000}],
                    "full_items": [{"name": "销售A", "amount": 1000000}],
                },
                "receipts_by_sales": {
                    "items": [{"name": "销售A", "amount": 800000}],
                    "full_items": [{"name": "销售A", "amount": 800000}],
                },
                "orders_by_customer": {
                    "items": [{"name": "客户B", "amount": 500000}],
                    "full_items": [{"name": "客户B", "amount": 500000}],
                },
                "receipts_by_customer": {
                    "items": [{"name": "客户B", "amount": 400000}],
                    "full_items": [{"name": "客户B", "amount": 400000}],
                },
            },
            "rankings_monthly": {"year": 2026, "sales": {}, "customer": {}},
        }
        view = api_v1.rankings_view_for_period(period, embed_full=False)
        self.assertTrue(view.get("visible"))
        sales = view.get("sales") or {}
        self.assertFalse(sales.get("empty"))
        item = (sales.get("items") or [None])[0]
        self.assertIsNotNone(item)
        self.assertIn("order_disp", item)
        self.assertIn("receipt_disp", item)
        self.assertIn("name_esc", item)
        self.assertTrue(str(item["order_disp"]).endswith("万"))


if __name__ == "__main__":
    unittest.main()
