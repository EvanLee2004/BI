#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书39：看端布局统一与联动（A–G）守卫。"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import assets  # noqa: E402
import loaders  # noqa: E402
import profit  # noqa: E402
import render  # noqa: E402
import theme  # noqa: E402


class TestAReceiptsFullWidth(unittest.TestCase):
    def test_stack_layout_and_chart_size(self):
        html = render.render_receipts([("1月", 10000.0, 20000.0, 50.0)])
        self.assertIn("rc-stack", html)
        self.assertIn("rc-summary", html)
        self.assertIn("rc-kpi", html)
        self.assertNotIn("rc-split", html)
        # 画布与趋势图同规格 640×288
        self.assertIn('viewBox="0 0 640 288"', html)
        css = theme.get_css()
        self.assertIn(".rc-card .rc-stack{display:flex;flex-direction:column", css)
        self.assertIn(".rc-kpi-num", css)


class TestBDailyPlacementAndSync(unittest.TestCase):
    def test_daily_before_receipts_in_dashboard_template(self):
        tpl = (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8")
        i4 = tpl.index("四")
        i_daily = tpl.index("daily_html")
        i_rc = tpl.index("receipts_budget")
        i_rank = tpl.index("rankViews")
        self.assertLess(i4, i_daily)
        self.assertLess(i_daily, i_rc)
        self.assertLess(i_rc, i_rank)

    def test_bu_daily_same_slot(self):
        tpl = (ROOT / "static/templates/render/bu_body.html").read_text(encoding="utf-8")
        i4 = tpl.index("下单与回款")
        i_daily = tpl.index("daily_html")
        i_rc = tpl.index("period-receipts")
        self.assertLess(i4, i_daily)
        self.assertLess(i_daily, i_rc)

    def test_js_period_auto_query(self):
        js = (ROOT / "static/js/cockpit.js").read_text(encoding="utf-8")
        self.assertIn("window._syncDailyDates", js)
        self.assertIn("runQuery", js)
        # 周期联动自动查询；手改不回写全局
        self.assertIn("handEdit", js)


class TestCDualDaily(unittest.TestCase):
    def test_dual_rankings_from_daily_shape(self):
        rk = {
            "orders_by_sales": {
                "items": [{"name": "甲", "amount": 1_000_000, "count": 1}],
                "total": 1_000_000,
                "full_items": [{"name": "甲", "amount": 1_000_000, "count": 1}],
            },
            "receipts_by_sales": {
                "items": [{"name": "甲", "amount": 500_000, "count": 1}],
                "total": 500_000,
                "full_items": [{"name": "甲", "amount": 500_000, "count": 1}],
            },
            "orders_by_customer": {"items": [], "total": 0, "full_items": []},
            "receipts_by_customer": {"items": [], "total": 0, "full_items": []},
        }
        d = render.dual_rankings_from_daily(rk)
        self.assertFalse(d["monthly_drill"])
        self.assertEqual(d["sales"]["title"], "下单/回款 · 按销售")
        it = d["sales"]["items"][0]
        self.assertIn("order_disp", it)
        self.assertIn("receipt_disp", it)
        self.assertIn("wo", it)
        self.assertIn("wr", it)
        self.assertEqual(it["mkey"], "")

    def test_js_paints_dual_legend(self):
        js = (ROOT / "static/js/cockpit.js").read_text(encoding="utf-8")
        self.assertIn("上·紫=下单", js)
        self.assertIn("下·青=回款", js)
        self.assertIn("dual_rankings", js)
        # 不得再拼四张单血条结果卡
        self.assertNotIn("下单 · 按销售", js)
        self.assertNotIn("rkHtml(", js)


class TestDLedgerStyle(unittest.TestCase):
    def test_template_capsules_and_scroll(self):
        dash = (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8")
        self.assertIn("cock-ctrl", dash)
        self.assertIn("ledger-scroll", dash)
        self.assertIn("mlPager", dash)
        css = theme.get_css()
        self.assertIn(".ledger-scroll", css)
        self.assertIn("position:sticky", css)
        self.assertIn("min(70vh", css)

    def test_js_period_ledger_sync(self):
        js = (ROOT / "static/js/cockpit.js").read_text(encoding="utf-8")
        self.assertIn("_syncLedgerYm", js)
        self.assertIn("pageSize", js)


class TestEExpenseTrend(unittest.TestCase):
    def test_compute_and_render_overall(self):
        # 合成台账：两月两类
        header = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]
        lcols = {
            "收单月份": 0,
            "收单日期": 1,
            "含税金额": 2,
            "业务BU": 3,
            "对应报表大类": 4,
            "预算明细费用类型": 5,
            "预算归属部门": 6,
        }
        rows = [
            (3, "2026-03-01", 1000000, "公共", "管理费用", "办公", "财务部"),  # 1万=1000000分? wait money.as_fen
            (3, "2026-03-02", 2000000, "公共", "市场费用", "推广", "市场部"),
            (6, "2026-06-01", 500000, "公共", "工资", "工资", "人事"),
        ]
        # money.as_fen: if already number treated as yuan historically? Check
        cfg = loaders.load_config(ROOT)
        raw = profit.compute_expense_monthly_by_cat(rows, 2026, lcols, cfg, year=2026, hide_salary=False)
        self.assertIn("管理费用", raw["categories"])
        m3 = raw["months"][2]
        self.assertGreater(m3["total"], 0)
        # 隐工资
        hid = render.apply_expense_salary_hide(raw, True)
        self.assertNotIn("工资", hid["categories"])
        self.assertIn("其他", hid["categories"])
        self.assertIn("并入", hid.get("note") or "")
        html = render.render_expense_trend(hid)
        self.assertIn("exp-trend-card", html)
        self.assertIn("viewBox=", html)
        self.assertIn("legend", html)

    def test_dashboard_includes_expense_trend(self):
        cfg = loaders.load_config(ROOT)
        today = datetime.date(2026, 7, 16)
        # 空台账即可：图卡仍渲染；不依赖本机真实收单台账 sheet
        header = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]
        s = profit.build_summary(
            cfg,
            [],
            [],
            [],
            [],
            header,
            [],
            today.year,
            today,
        )
        html = render.render_dashboard(s, cfg, assets.load_logo_base64(cfg))
        self.assertIn("exp-trend-card", html)
        self.assertIn("费用月度趋势", html)
        # 看端无黄横幅
        self.assertNotIn("fetchBanner", html)

    def test_bu_expense_trend_no_other_bu_leak(self):
        cfg = loaders.load_config(ROOT)
        today = loaders.pinned_today(cfg)
        # 空 BU：图表可空，但不得出现他 BU 专有金额串（用合成名）
        s = profit.build_bu_summary(
            cfg,
            loaders.load_project_detail(cfg),
            loaders.load_orders(cfg),
            loaders.load_receipts(cfg),
            loaders.load_inhouse(cfg),
            today,
            {"合成销售甲"},
            bu_name="合成BU甲",
        )
        html = render.render_bu_page("合成BU甲", s, cfg, assets.load_logo_base64(cfg))
        self.assertIn("费用月度趋势", html)
        self.assertIn("合成BU甲", html)
        self.assertNotIn("合成BU乙", html)
        self.assertNotIn("fetchBanner", html)


class TestFFetchBannerViewerGone(unittest.TestCase):
    def test_admin_keeps_banner_hook(self):
        self.assertIn("fetchBanner", (ROOT / "static/admin/admin.html.legacy").read_text(encoding="utf-8"))
        self.assertIn("paintFetchBanners", (ROOT / "static/admin/admin.js").read_text(encoding="utf-8"))


class TestGPctClamp(unittest.TestCase):
    def test_target_bar_extreme_pct(self):
        from render_widgets import _target_bar

        b = {"order": {"target": 1, "done": 100_000, "pct": 48178.0}}
        h = _target_bar(b, "order", "2026年", 2026, {"orders": 100_000})
        self.assertIn(">999% · 目标待校准", h)
        self.assertNotIn("48178", h)

    def test_budget_tag_removed_task41(self):
        """任务书41·B：卡头预算小字删除；KPI 进度条仍保留 G 钳制。"""
        tag = render._budget_tag({"receipt": {"target": 100, "pct": 50000}})
        self.assertEqual(tag, "")


class TestDailyApiDual(unittest.TestCase):
    def test_api_daily_returns_dual(self):
        from fastapi.testclient import TestClient
        import accounts
        import db
        import server

        tmp = Path(tempfile.mkdtemp())
        (tmp / "数据").mkdir()
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "数据"
        cfg["db_path"] = "数据/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            cfg,
            tmp,
            [
                {"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"},
                {"账号": "overall", "密码": server.DEFAULT_VIEW_PW, "权限": "整体", "显示名": "整"},
            ],
        )
        conn = db.connect(cfg, tmp)
        conn.close()
        app = server.create_app(cfg, root=tmp)
        c = TestClient(app, follow_redirects=False)
        lr = c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(lr.status_code, 303)
        r = c.get("/api/daily", params={"start": "2026-01-01", "end": "2026-03-31"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("dual_rankings", d)
        self.assertIn("sales", d["dual_rankings"])
        self.assertIn("customer", d["dual_rankings"])
        self.assertIs(d["dual_rankings"]["monthly_drill"], False)
        self.assertIn("totals", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
