#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""陆总#8 / 任务书34：排名行 1~12 月下钻（页面级字典 + 行 mkey）。

- views：items 只带 mkey；monthly 显示串在 monthly_data / rankings_monthly_data
- 守恒：主体全年月度下单/回款之和 == compute_ranking 该主体金额
- 只挂排名出现的主体（非全库倾倒）
- JS 组装 ≡ Python render_rankings（规范化）
- 前端零金额运算；无行级 data-monthly 大 JSON；paint 按 mkey 取数
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
        # 主体甲：行上 mkey，无 monthly 大数组
        it = next(x for x in sales["items"] if x["name"] == "甲")
        self.assertNotIn("monthly", it)
        self.assertTrue(it.get("mkey"))
        self.assertEqual(it["mkey"], "2026|销售|甲")
        mon = (view.get("monthly_data") or {}).get(it["mkey"]) or []
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
        # 显示串与后端预算一致（paint 只拼已有串）
        self.assertEqual(mon[0]["order_disp"], render._rank_amt(100_000.0))
        self.assertEqual(mon[2]["order_disp"], render._rank_amt(50_000.0))

    def test_only_ranked_entities_not_full_db(self):
        p = _period()
        self.assertIn("甲", p["rankings_monthly"]["sales"])
        self.assertIn("乙", p["rankings_monthly"]["sales"])
        self.assertNotIn("不存在的销售", p["rankings_monthly"]["sales"])
        names = {it["name"] for it in p["rankings"]["orders_by_sales"]["full_items"]}
        names |= {it["name"] for it in p["rankings"]["receipts_by_sales"]["full_items"]}
        self.assertEqual(set(p["rankings_monthly"]["sales"].keys()), names)
        view = api_v1.rankings_view_for_period(p, embed_full=True)
        store_keys = set((view.get("monthly_data") or {}).keys())
        # 键集合 ⊆ 销售|客户 排名主体
        for k in store_keys:
            self.assertRegex(k, r"^\d+\|(销售|客户)\|.+")

    def test_no_row_level_monthly_blob(self):
        """任务书34：行 HTML/JSON 无 data-monthly 大数组。"""
        p = _period()
        py_html = render.render_rankings(p, embed_full=True)
        self.assertNotIn("data-monthly=", py_html)
        self.assertIn("data-mkey=", py_html)
        self.assertIn('id="rkMonthlyData"', py_html)
        self.assertIn("2026|销售|甲", py_html)
        view = api_v1.rankings_view_for_period(p, embed_full=True)
        for it in (view["sales"].get("items") or []) + (view["sales"].get("full_items") or []):
            self.assertNotIn("monthly", it)
            self.assertTrue(it.get("mkey"))

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
        self.assertIn("data-mkey=", py_html)
        self.assertIn("rk-entity", py_html)
        self.assertIn("1月", py_html)  # 页面级 JSON 内月份名
        self.assertNotIn("data-monthly=", py_html)

    def test_paint_lookup_matches_store(self):
        """驱动真实 rankings.js paint：按 mkey 取出 12 月显示串。"""
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        p = _period()
        view = api_v1.rankings_view_for_period(p, embed_full=True)
        it = next(x for x in view["sales"]["items"] if x["name"] == "甲")
        mkey = it["mkey"]
        store = view["monthly_data"]
        mon0 = store[mkey][0]["order_disp"]
        script = f"""
const fs = require('fs');
const path = require('path');
const code = fs.readFileSync(path.join({json.dumps(str(ROOT / "static/js/assemble"))}, 'rankings.js'), 'utf8');
const vm = require('vm');
const sandbox = {{ window: {{}}, globalThis: {{}}, console }};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.runInNewContext(code, sandbox);
sandbox.__rkMonthlyData = {json.dumps(store, ensure_ascii=False)};
const el = {{ getAttribute: (k) => k === 'data-mkey' ? {json.dumps(mkey)} : null }};
const html = sandbox.paintRankingMonthly(el);
if (!html.includes('dual-month')) throw new Error('no dual-month');
if (!html.includes({json.dumps(mon0)})) throw new Error('missing disp ' + {json.dumps(mon0)});
if ((html.match(/dual-month/g) || []).length !== 12) throw new Error('need 12 months');
process.stdout.write('PAINT_OK');
"""
        r = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PAINT_OK", r.stdout)

    def test_js_click_handlers_and_no_money_math(self):
        js = (ROOT / "static/js/assemble/rankings.js").read_text(encoding="utf-8")
        self.assertIn("rk-entity", js)
        self.assertIn("data-mkey", js)
        self.assertIn("paintRankingMonthly", js)
        self.assertIn("__rkMonthlyData", js)
        self.assertNotIn("data-monthly", js)
        bad = re.findall(r"\b(amount|order|receipt)\s*[\+\-\*/]", js)
        self.assertEqual(bad, [], f"组装 JS 疑似金额运算: {bad}")
        for name in ("cockpit.js", "cockpit-bu.js"):
            src = (ROOT / "static/js" / name).read_text(encoding="utf-8")
            self.assertIn("rk-entity", src, name)
            self.assertIn("paintRankingMonthly", src, name)
            self.assertIn("data-mkey", src, name)
            self.assertNotIn("data-monthly", src, name)

    def test_multi_period_shared_store_no_row_monthly(self):
        """多周期：共享 monthly_store 去重；各 period items 无 monthly、无各自 monthly_data。"""
        p = _period()
        shared: dict = {}
        v1 = api_v1.rankings_view_for_period(p, embed_full=True, monthly_store=shared)
        v2 = api_v1.rankings_view_for_period(
            {**p, "range": ("2026-01-01", "2026-01-31")}, embed_full=True, monthly_store=shared
        )
        self.assertNotIn("monthly_data", v1)
        self.assertNotIn("monthly_data", v2)
        self.assertIn("2026|销售|甲", shared)
        # 第二次写入不膨胀（同键覆盖/跳过）
        n_sales = len([k for k in shared if k.startswith("2026|销售|")])
        self.assertEqual(n_sales, len(p["rankings_monthly"]["sales"]))
        for rv in (v1, v2):
            for it in (rv["sales"].get("items") or []):
                self.assertNotIn("monthly", it)
                self.assertTrue(it.get("mkey"))

    def test_golden_generate_monthly_present(self):
        """真实 generate 路径：views 挂 monthly store，守恒抽查一主体。"""
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
        views = summary.get("_views") or api_v1.build_cockpit_views(summary, cfg)
        store = views.get("rankings_monthly_data") or {}
        self.assertTrue(store, "应有页面级月度字典")
        view = (views.get("rankings_view") or {}).get(yk) or api_v1.rankings_view_for_period(p, embed_full=True)
        items = (view.get("sales") or {}).get("items") or []
        self.assertTrue(items, "golden 年排名应有销售")
        it = items[0]
        self.assertNotIn("monthly", it)
        self.assertTrue(it.get("mkey"))
        mon = store.get(it["mkey"]) or (view.get("monthly_data") or {}).get(it["mkey"])
        self.assertEqual(len(mon or []), 12)
        name = it["name"]
        raw = ((p.get("rankings_monthly") or {}).get("sales") or {}).get(name)
        self.assertIsNotNone(raw)
        o_sum = round(sum(raw["order"]), 2)
        o_items = ((p.get("rankings") or {}).get("orders_by_sales") or {}).get("full_items") or []
        match = next((x for x in o_items if x["name"] == name), None)
        self.assertIsNotNone(match)
        self.assertEqual(o_sum, match["amount"])


if __name__ == "__main__":
    unittest.main()
