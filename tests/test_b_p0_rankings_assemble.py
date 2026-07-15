#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P0：排名双血条 旧路径 render_rankings vs 新路径 view+同构组装 逐字节相等。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def assemble_from_view(view: dict) -> str:
    """用与 render 相同的 tpl 片段从 view 组装（等价于 JS 读同一模板结构）。"""
    import tpl
    import render

    def card(blk):
        if blk.get("empty"):
            body = tpl.load("render/ev_empty.html")
        else:
            rows = []
            for it in blk.get("items") or []:
                rows.append(tpl.fill(
                    "render/dual_row.html",
                    i=it["i"], title=it["name_esc"], name=it["name_esc"],
                    wo=it["wo"], wr=it["wr"],
                    o_amt=it["order_disp"], r_amt=it["receipt_disp"]))
            more = ""
            o = blk.get("others")
            if o:
                more = tpl.fill("render/rank_more.html", names=o["names"], amt=o["amt"], count=o["count"])
            body = tpl.fill("render/rank_body.html", rows="".join(rows), more=more, full="")
        return tpl.fill("render/dual_card.html", dim=blk["dim"], title=blk["title"], body=body)

    return tpl.fill(
        "render/dual_grid.html",
        s=view["start"], e=view["end"],
        sales=card(view["sales"]), cust=card(view["customer"]))


class TestP0RankingsAssemble(unittest.TestCase):
    def _period(self):
        return {
            "range": ("2026-01-01", "2026-12-31"),
            "rankings": {
                "orders_by_sales": {
                    "items": [{"name": "甲", "amount": 100.0, "count": 1}],
                    "full_items": [{"name": "甲", "amount": 100.0, "count": 1}], "total": 100.0},
                "receipts_by_sales": {
                    "items": [{"name": "甲", "amount": 40.0, "count": 1}],
                    "full_items": [{"name": "甲", "amount": 40.0, "count": 1}], "total": 40.0},
                "orders_by_customer": {
                    "items": [{"name": "客", "amount": 80.0, "count": 1}],
                    "full_items": [{"name": "客", "amount": 80.0, "count": 1}], "total": 80.0},
                "receipts_by_customer": {
                    "items": [{"name": "客", "amount": 30.0, "count": 1}],
                    "full_items": [{"name": "客", "amount": 30.0, "count": 1}], "total": 30.0},
            },
        }

    def test_py_render_equals_view_assemble(self):
        import render, api_v1
        p = self._period()
        old = render.render_rankings(p)
        view = api_v1.rankings_view_for_period(p)
        new = assemble_from_view(view)
        self.assertEqual(old, new)

    def test_assemble_js_no_money_math(self):
        js = (ROOT / "static" / "js" / "assemble" / "rankings.js").read_text(encoding="utf-8")
        bad = re.findall(r"\b(amount|order|receipt)\s*[\+\-\*/]", js)
        self.assertEqual(bad, [], f"组装 JS 疑似金额运算: {bad}")

    def test_js_file_exists(self):
        self.assertTrue((ROOT / "static" / "js" / "assemble" / "rankings.js").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
