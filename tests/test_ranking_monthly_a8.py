#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""陆总#8：排名行 1~12 月下单/回款月度下钻。

- views 结构：items 挂 monthly[12] 显示串 + 宽度%
- 守恒：主体全年月度下单/回款之和 == compute_ranking 该主体金额
- 只挂排名出现的主体（非全库倾倒）
- JS 组装 ≡ Python render_rankings（规范化）
- 前端零金额运算；无新跨界 API
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import api_v1  # noqa: E402
import profit  # noqa: E402
import render  # noqa: E402

S, E = datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)
COLS = {
    "order_amount": "金额",
    "order_date": "日期",
    "receipt_amount": "金额",
    "receipt_date": "日期",
}


def _orders():
    return [
        {"销售": "甲", "客户": "客A", "金额": 100_000, "日期": "2026-01-15"},
        {"销售": "甲", "客户": "客A", "金额": 50_000, "日期": "2026-03-10"},
        {"销售": "乙", "客户": "客B", "金额": 20_000, "日期": "2026-02-01"},
        {"销售": "丙", "客户": "客C", "金额": 5_000, "日期": "2026-04-01"},
        # 期外不应进月度
        {"销售": "甲", "客户": "客A", "金额": 999_999, "日期": "2025-12-31"},
    ]


def _receipts():
    return [
        {"销售": "甲", "客户": "客A", "金额": 80_000, "日期": "2026-01-20"},
        {"销售": "甲", "客户": "客A", "金额": 10_000, "日期": "2026-06-01"},
        {"销售": "乙", "客户": "客B", "金额": 15_000, "日期": "2026-02-15"},
    ]


def _period():
    orders, receipts = _orders(), _receipts()
    rk = {
        "orders_by_sales": profit.compute_ranking(orders, "销售", COLS["order_amount"], COLS["order_date"], S, E),
        "receipts_by_sales": profit.compute_ranking(
            receipts, "销售", COLS["receipt_amount"], COLS["receipt_date"], S, E
        ),
        "orders_by_customer": profit.compute_ranking(orders, "客户", COLS["order_amount"], COLS["order_date"], S, E),
        "receipts_by_customer": profit.compute_ranking(
            receipts, "客户", COLS["receipt_amount"], COLS["receipt_date"], S, E
        ),
    }
    rm = profit.build_rankings_monthly(orders, receipts, COLS, 2026, rk)
    return {
        "range": ("2026-01-01", "2026-12-31"),
        "rankings": rk,
        "rankings_monthly": rm,
    }


class TestRankingMonthlyA8(unittest.TestCase):
    def test_views_structure_and_conservation(self):
        p = _period()
        view = api_v1.rankings_view_for_period(p, embed_full=True)
        self.assertTrue(view.get("visible"))
        sales = view["sales"]
        self.assertFalse(sales.get("empty"))
        self.assertTrue(sales.get("items"))
        # 主体甲
        it = next(x for x in sales["items"] if x["name"] == "甲")
        mon = it.get("monthly") or []
        self.assertEqual(len(mon), 12)
        for i, m in enumerate(mon, 1):
            self.assertEqual(m["i"], i)
            self.assertEqual(m["name"], f"{i}月")
            self.assertIn("order_disp", m)
            self.assertIn("receipt_disp", m)
            self.assertIn("wo", m)
            self.assertIn("wr", m)
        # 守恒：月度下单之和 == compute_ranking 金额
        raw = p["rankings_monthly"]["sales"]["甲"]
        o_sum = round(sum(raw["order"]), 2)
        r_sum = round(sum(raw["receipt"]), 2)
        o_rk = next(x for x in p["rankings"]["orders_by_sales"]["full_items"] if x["name"] == "甲")
        r_rk = next(x for x in p["rankings"]["receipts_by_sales"]["full_items"] if x["name"] == "甲")
        self.assertEqual(o_sum, o_rk["amount"])
        self.assertEqual(r_sum, r_rk["amount"])
        # 1 月 / 3 月有数
        self.assertEqual(raw["order"][0], 100_000.0)
        self.assertEqual(raw["order"][2], 50_000.0)
        self.assertEqual(raw["order"][1], 0.0)

    def test_only_ranked_entities_not_full_db(self):
        p = _period()
        # 故意多造不在排名行的名字不会出现在 monthly
        self.assertIn("甲", p["rankings_monthly"]["sales"])
        self.assertIn("乙", p["rankings_monthly"]["sales"])
        self.assertNotIn("不存在的销售", p["rankings_monthly"]["sales"])
        # monthly keys ⊆ 排名 full 名单
        names = {it["name"] for it in p["rankings"]["orders_by_sales"]["full_items"]}
        names |= {it["name"] for it in p["rankings"]["receipts_by_sales"]["full_items"]}
        self.assertEqual(set(p["rankings_monthly"]["sales"].keys()), names)

    def test_js_equals_python_with_monthly(self):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        p = _period()
        py_html = render.render_rankings(p, embed_full=True)
        view = api_v1.rankings_view_for_period(p, embed_full=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(view, f, ensure_ascii=False)
            vp = f.name
        r = subprocess.run(
            ["node", str(ROOT / "static/js/assemble/rankings_node_runner.js"), vp],
            capture_output=True,
            text=True,
            check=True,
        )

        def norm(s):
            return re.sub(r">\s+<", "><", s.replace("\n", ""))

        self.assertEqual(norm(py_html), norm(r.stdout))
        self.assertIn("data-monthly=", py_html)
        self.assertIn("rk-entity", py_html)
        self.assertIn("1月", py_html)  # JSON 内月份名

    def test_js_click_handlers_and_no_money_math(self):
        js = (ROOT / "static/js/assemble/rankings.js").read_text(encoding="utf-8")
        self.assertIn("rk-entity", js)
        self.assertIn("data-monthly", js)
        self.assertIn("paintRankingMonthly", js)
        bad = re.findall(r"\b(amount|order|receipt)\s*[\+\-\*/]", js)
        self.assertEqual(bad, [], f"组装 JS 疑似金额运算: {bad}")
        for name in ("cockpit.js", "cockpit-bu.js"):
            src = (ROOT / "static/js" / name).read_text(encoding="utf-8")
            self.assertIn("rk-entity", src, name)
            self.assertIn("paintRankingMonthly", src, name)
            self.assertIn("data-monthly", src, name)

    def test_golden_generate_monthly_present(self):
        """真实 generate 路径：views 挂 monthly，守恒抽查一主体。"""
        import loaders
        import core

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        summary, _, _, _ = core.generate(cfg, datetime.date(2026, 6, 30), trigger="a8-monthly")
        yk = (summary.get("meta") or {}).get("year_key") or "2026年"
        p = (summary.get("periods") or {}).get(yk) or {}
        self.assertIn("rankings_monthly", p)
        view = api_v1.rankings_view_for_period(p, embed_full=True)
        items = (view.get("sales") or {}).get("items") or []
        self.assertTrue(items, "golden 年排名应有销售")
        it = items[0]
        self.assertEqual(len(it.get("monthly") or []), 12)
        name = it["name"]
        raw = ((p.get("rankings_monthly") or {}).get("sales") or {}).get(name)
        self.assertIsNotNone(raw)
        o_sum = round(sum(raw["order"]), 2)
        # 与 full_items 该名下单金额一致（全年）
        o_items = ((p.get("rankings") or {}).get("orders_by_sales") or {}).get("full_items") or []
        match = next((x for x in o_items if x["name"] == name), None)
        self.assertIsNotNone(match)
        self.assertEqual(o_sum, match["amount"])


if __name__ == "__main__":
    unittest.main()
