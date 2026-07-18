#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·阶段0：看端明细白名单（去配音费合同号）+ 费用堆叠面积图 + 整体放大一档。

覆盖：
- VIEW 白名单列序 / 6 隐藏列
- 看端 detail JSON 与导出不含隐藏列；管理端全列仍在
- 面积图 SVG 含 <path 且 1~12 月标签
- 整体页/BU 页组装 HTML 中明细卡与 expense_trend 断言
- theme 放大：--fs-kpi / 业务 BU 分页 / 板块二图高
"""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import charts  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import render  # noqa: E402
import server  # noqa: E402
import theme  # noqa: E402

WHITELIST = [
    "收单日期",
    "事项",
    "含税金额",
    "对应报表大类",
    "预算明细费用类型",
    "业务员",
    "预算归属部门",
    "业务BU",
]
HIDDEN = [
    "定位键",
    "收单月份",
    "归属月",
    "提单人",
    "提单人部门",
    "配音费合同号",
]


def _fen(y):
    return money.yuan_to_fen(y)


class TestWhitelistConstants(unittest.TestCase):
    def test_order_and_hidden(self):
        self.assertEqual(db.VIEW_EXPENSE_COLUMNS, WHITELIST)
        self.assertEqual(db.VIEW_EXPENSE_COLUMNS_BU, [c for c in WHITELIST if c != "业务BU"])
        for h in HIDDEN:
            self.assertNotIn(h, db.VIEW_EXPENSE_COLUMNS)
            self.assertNotIn(h, db.VIEW_EXPENSE_COLUMNS_BU)
        self.assertEqual(list(db.VIEW_EXPENSE_HIDDEN), HIDDEN)


class _LedgerApp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = "数据"
        self.cfg["db_path"] = "数据/看板.db"
        self.cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"},
                {"账号": "all", "密码": "8888", "权限": "整体", "显示名": "姜总"},
                {"账号": "bu_a", "密码": "8888", "权限": "BU", "可见BU": ["甲BU"], "显示名": "甲"},
            ],
        )
        conn = db.connect(self.cfg, self.tmp)
        rows = [
            ("K1", "01", "2026-01-10", _fen(100), "甲BU", "管理费用", "办公费", "市场部", "事A", "提A", "提部", "业A", "PO-1", "2026-01"),
            ("K2", "02", "2026-02-10", _fen(200), "甲BU", "市场费用", "推广费", "市场部", "事B", "提B", "提部", "业B", "PO-2", "2026-02"),
            ("K3", "03", "2026-03-10", _fen(150), "乙BU", "管理费用", "办公费", "市场部", "事C", "提C", "提部", "业C", "", "2026-03"),
        ]
        for r in rows:
            conn.execute(
                "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
                "预算明细费用类型,预算归属部门,事项,提单人,提单人部门,业务员,配音费合同号,归属月,原值_归属月,已删除)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                r + (r[13],),
            )
        conn.commit()
        conn.close()
        self.app = server.create_app(self.cfg, root=self.tmp)
        from fastapi.testclient import TestClient

        self.TC = TestClient

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _login(self, account="all"):
        c = self.TC(self.app)
        r = c.post("/login", data={"account": account, "password": "8888"}, follow_redirects=False)
        self.assertIn(r.status_code, (302, 303), r.text[:200])
        return c


class TestDetailJsonAndExport(_LedgerApp):
    def test_view_json_no_hidden_fields(self):
        c = self._login("all")
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 50, "year": "2026"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["columns"], WHITELIST)
        for h in HIDDEN:
            self.assertNotIn(h, d["columns"])
        for row in d["rows"]:
            for h in HIDDEN:
                self.assertNotIn(h, row, f"看端 JSON 行不得含隐藏列字段 {h}")

    def test_bu_json_omits_bu_col(self):
        c = self._login("bu_a")
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 50, "year": "2026", "bu": "甲BU"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["columns"], db.VIEW_EXPENSE_COLUMNS_BU)
        self.assertNotIn("业务BU", d["columns"])
        for h in HIDDEN:
            self.assertNotIn(h, d["columns"])
            for row in d["rows"]:
                self.assertNotIn(h, row)

    def test_export_whitelist_only(self):
        c = self._login("all")
        r = c.get("/api/detail_export", params={"table": "费用明细", "year": "2026"})
        self.assertEqual(r.status_code, 200, r.text)
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        headers = [cell.value for cell in wb.active[1]]
        self.assertEqual(headers, WHITELIST)
        for h in HIDDEN:
            self.assertNotIn(h, headers)

    def test_admin_still_full_columns(self):
        conn = db.connect(self.cfg, self.tmp)
        d = db.query_detail(conn, "费用明细", year="2026", page_size=50, audience="admin")
        conn.close()
        for col in ("定位键", "提单人", "提单人部门", "配音费合同号", "归属月", "收单月份"):
            self.assertIn(col, d["columns"], "管理端全列不得砍")


class TestAreaChart(unittest.TestCase):
    def test_stack_chart_is_area_with_12_months(self):
        months = []
        for i in range(12):
            segs = []
            if i in (2, 5):
                segs = [
                    {"cat": "管理费用", "amount": 1_000_000, "amount_disp": "1.0", "pct_disp": "50.0%"},
                    {"cat": "市场费用", "amount": 1_000_000, "amount_disp": "1.0", "pct_disp": "50.0%"},
                ]
            total = sum(float(s["amount"]) for s in segs)
            months.append(
                {
                    "m": i + 1,
                    "total": total,
                    "total_disp": charts.fmt_wan(total),
                    "segs": segs,
                }
            )
        svg = charts.expense_stack_chart(months, ["管理费用", "市场费用"])
        self.assertIn("<path", svg)
        self.assertIn('class="exp-area"', svg)
        self.assertNotIn('class="bar exp-seg"', svg)
        for m in range(1, 13):
            self.assertIn(f">{m}月", svg)
        self.assertIn("viewBox=", svg)
        # 放大后高度 317
        self.assertIn('viewBox="0 0 640 317"', svg)

    def test_render_expense_trend_card(self):
        raw = {
            "categories": ["管理费用", "市场费用"],
            "months": [
                {
                    "m": i + 1,
                    "total": 2_000_000 if i == 2 else 0,
                    "by_cat": {"管理费用": 1_000_000, "市场费用": 1_000_000} if i == 2 else {},
                }
                for i in range(12)
            ],
            "note": "",
        }
        html = render.render_expense_trend(raw)
        self.assertIn("exp-trend-card", html)
        self.assertIn("<path", html)
        for m in range(1, 13):
            self.assertIn(f"{m}月", html)


class TestAssemblePagesNoHidden(unittest.TestCase):
    """组装后的整体/BU 页：明细卡容器在；expense_trend 面积；隐藏列名不进 trend/ledger 相关 frags。"""

    def test_dashboard_and_bu_expense_trend(self):
        raw = {
            "categories": ["管理费用"],
            "months": [{"m": i + 1, "total": 0, "by_cat": {}} for i in range(12)],
            "note": "",
        }
        trend = render.render_expense_trend(raw)
        frags = {
            "title": "t",
            "particles": "",
            "logo": "",
            "version": "v",
            "generated_at": "",
            "pw_modal": "",
            "period_bar": "",
            "kpi_views": "",
            "trend_html": "",
            "donut_views": "",
            "pl_views": "",
            "profit_rank_views": "",
            "receipts_budget": "",
            "daily_html": "",
            "rank_views": "",
            "expense_trend_html": trend,
            "drawer": "",
            "bu_nav": "",
            "bu_unassigned": "",
        }
        dash = render.assemble_dashboard_html(frags)
        self.assertIn("cock-ledger", dash)
        self.assertIn("mlTbl", dash)
        self.assertIn("<path", dash)
        self.assertIn("exp-trend-card", dash)
        for h in HIDDEN:
            # 明细卡本身由 JS 动态建表，shell 不应硬编码隐藏列名
            # 面积图 SVG 也不应含这些业务列名
            self.assertNotIn(h, trend)

        bu_frags = {
            "title": "t",
            "particles": "",
            "logo": "",
            "name": "甲BU",
            "version": "v",
            "generated_at": "",
            "export_url": "#",
            "pw_modal": "",
            "period_bar": "",
            "kpi_views": "",
            "trend_html": "",
            "donut_views": "",
            "pl_tag": "",
            "pl_views": "",
            "profit_rank_views": "",
            "receipts_html": "",
            "daily_html": "",
            "rank_views": "",
            "expense_trend_html": trend,
            "drawer": "",
            "rk_modal": "",
        }
        bu_html = render.assemble_bu_dashboard_html(bu_frags)
        self.assertIn("bu-ledger", bu_html)
        self.assertIn("blTbl", bu_html)
        self.assertIn("<path", bu_html)
        for h in HIDDEN:
            self.assertNotIn(h, trend)


class TestThemeScale(unittest.TestCase):
    def test_fs_kpi_and_bu_nav_and_chart_h(self):
        css = theme.get_css()
        # 54.9：KPI 字号归 8pt 网格 32px（原任务书46 的 35.2px 已废止）
        self.assertIn("--fs-kpi:32px", css)
        self.assertNotIn("--fs-kpi:35.2px", css)
        self.assertIn("--chart-h-sec2:317px", css)
        # 业务 BU 分页 +10%（历史刻度仍保留）
        self.assertIn("font-size:15.4px", css)
        self.assertIn("padding:7.7px 17.6px", css)
        # 板块二图高
        svg = charts.combo_bar_line_chart([("1月", 1_000_000, 400_000, 60.0)])
        self.assertIn('viewBox="0 0 640 317"', svg)


if __name__ == "__main__":
    unittest.main()
