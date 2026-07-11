#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经营驾驶舱回归测试：口径对账 + 手填默认上月 + 前端不做金额运算守卫。跑：python tests/test_cockpit.py"""
import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders, profit, render, assets, charts, columns, validate  # noqa: E402


def _summary():
    cfg = loaders.load_config()
    today = loaders.pinned_today(cfg)
    yr = today.year
    lh, lr = loaders.load_ledger(cfg, str(yr))
    S = profit.build_summary(
        cfg, loaders.load_project_detail(cfg), loaders.load_orders(cfg),
        loaders.load_receipts(cfg), loaders.load_inhouse(cfg), lh, lr, yr, today)
    return cfg, S


class TestReconcile(unittest.TestCase):
    """每个周期都要满足陆总的公式（对账，防口径漂移）。"""
    def test_all_periods_reconcile(self):
        cfg, S = _summary()
        vat = cfg["tax"]["vat_rate"]; sur = cfg["tax"]["surtax_rate"]
        for key, p in S["periods"].items():
            man = p["manual"]; led = p["ledger_expenses"]
            prod_manual = sum(man[k] for k in ["PM人力成本", "VM人力成本", "实际内部译员成本",
                                               "税费损失", "技术流量成本", "其他（生产成本）"])
            # 生产成本 = 系统直接成本 − 内部译员成本 + 手填生产成本项
            self.assertAlmostEqual(p["production_cost"],
                                   p["system_direct_cost"] - p["inhouse_cost"] + prod_manual, places=1, msg=key)
            # 毛利
            self.assertAlmostEqual(p["gross_profit"], p["revenue_net"] - p["production_cost"], places=1, msg=key)
            # 财务费用 = 台账 + 手填补充
            self.assertAlmostEqual(p["expense"]["财务费用"], led["财务费用"] + man["财务费用补充"], places=1, msg=key)
            # 营销/管理/研发 = 手填人力 + 台账
            self.assertAlmostEqual(p["expense"]["营销费用"], man["营销人力成本"] + led["市场费用"], places=1, msg=key)
            self.assertAlmostEqual(p["expense"]["研发费用"], man["研发人力成本"] + led["技术服务费"], places=1, msg=key)
            # 附加税费 = 收入 × 6% × 12%
            self.assertAlmostEqual(p["surtax"], round(p["revenue_net"] * vat * sur, 2), places=1, msg=key)
            # 税前利润 = 毛利 − 期间费用 − 附加税费 + 其他损益
            self.assertAlmostEqual(
                p["pretax_profit"],
                p["gross_profit"] - p["expense"]["total"] - p["surtax"] + p["other_pl"], places=1, msg=key)


class TestManualDefault(unittest.TestCase):
    """手填：某月没填 → default=prev 取上月、default=zero 取0。"""
    def test_carry_forward(self):
        cfg = loaders.load_config()
        raw = {"2024-06": {"研发人力成本": 150000, "其他损益": 5000}}  # 7月都没填
        filled = profit.build_manual_monthly(cfg, raw, 2024, 7)
        self.assertEqual(filled[(2024, 7)]["研发人力成本"], 150000)  # prev → 取6月
        self.assertEqual(filled[(2024, 7)]["其他损益"], 0.0)         # zero → 不继承，回0
        self.assertEqual(filled[(2024, 6)]["营销人力成本"], 0.0)     # 从没填过 → 0


class TestValueGuards(unittest.TestCase):
    """坏值防线：文本金额不崩、坏日期计数、表头重名报错、手填月份列名不补零也能读。"""
    LEDGER_HEADER = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型"]

    def test_ledger_text_amount_and_bad_date(self):
        cfg = loaders.load_config()
        lcols = columns.resolve_ledger_columns(self.LEDGER_HEADER)
        rows = [
            (7, None, "1,000.50", "公共", "管理费用", "差旅费"),   # 文本金额带千分位：以前直接崩
            ("7月", None, 200, "公共", "管理费用", "差旅费"),      # 收单月份"7月"解析不出：行被剔除但必须计数
        ]
        led, _ = profit.compute_ledger_expenses(
            rows, 2024, datetime.date(2024, 7, 1), datetime.date(2024, 7, 31), cfg, lcols)
        self.assertAlmostEqual(led["管理费用"], 1000.50)
        date_bad, amt_bad = profit._scan_ledger_issues(rows, 2024, lcols)
        self.assertEqual(date_bad, 1)
        self.assertEqual(amt_bad, 0)

    def test_duplicate_ledger_header_raises(self):
        with self.assertRaises(ValueError):
            columns.resolve_ledger_columns(self.LEDGER_HEADER + ["含税金额"])
        with self.assertRaises(ValueError):  # 别名互撞（业务BU 与 利润归属中心 同时存在）也要报
            columns.resolve_ledger_columns(self.LEDGER_HEADER + ["利润归属中心"])

    def test_manual_month_header_no_padding(self):
        import tempfile
        import openpyxl
        with tempfile.TemporaryDirectory() as td:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "手填与调整"
            ws.append(["项目", "归属", "备注", "2024-7"])   # 手打不补零
            ws.append(["研发人力成本", "x", "", 123])
            d = Path(td) / "d"
            d.mkdir()
            wb.save(d / "手填与调整.xlsx")
            out = loaders.load_manual({"data_dir": "d", "files": {"manual": "手填与调整.xlsx"}}, Path(td))
            self.assertEqual(out["2024-07"]["研发人力成本"], 123)


class TestValidate(unittest.TestCase):
    """进门验证：好数据全绿；故意弄坏的数据必须被点名到 源+列+Excel行号。"""

    def test_current_data_passes(self):
        cfg = loaders.load_config()
        rep = validate.validate_all(cfg, loaders.pinned_today(cfg).year)
        self.assertEqual([f"{i.source}:{i.message}" for i in rep.errors], [])

    def test_broken_data_pinpointed(self):
        import shutil
        import tempfile
        import openpyxl
        cfg = loaders.load_config()
        year = loaders.pinned_today(cfg).year
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "数据", root / "数据")
            # ① 台账：报表大类錯别字 + 收单月份"7月"且无收单日期 + 金额文本"abc"
            p = root / "数据" / "收单台账.xlsx"
            wb = openpyxl.load_workbook(p)
            ws = wb[str(year)]
            hdr = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
            c_cat, c_m, c_d, c_amt = (hdr.index(x) + 1 for x in ("对应报表大类", "收单月份", "收单日期", "含税金额"))
            ws.cell(row=3, column=c_cat, value="管理费")            # 口径外类别
            ws.cell(row=4, column=c_m, value="7月")                 # 月份解析不出
            ws.cell(row=4, column=c_d).value = None                 # 注意:cell(...,value=None)不会清空,要显式赋值
            ws.cell(row=5, column=c_amt, value="abc")               # 非数字金额
            wb.save(p)
            # ② 项目明细：交付日期坏值
            p = root / "数据" / "项目明细.xlsx"
            wb = openpyxl.load_workbook(p)
            ws = wb.active
            hdr = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
            ws.cell(row=6, column=hdr.index("整单交付日期") + 1, value="无")
            wb.save(p)
            rep = validate.validate_all(cfg, year, root)
            msgs = "\n".join(f"[{i.source}]{i.message}" for i in rep.errors)
            self.assertIn("管理费", msgs)
            self.assertIn("第3行", msgs)
            self.assertIn("第4行", msgs)                     # 收单月份坏行
            self.assertIn("第5行", msgs)                     # 金额坏行
            self.assertIn("[项目明细(智云)]", msgs)
            self.assertIn("第6行", msgs)


class TestReceiptOrderRatio(unittest.TestCase):
    """A2 回款下单率：每期 = 回款÷下单×100（无下单置 None）；逐月序列与月周期对齐。"""
    def test_period_ratio_matches_formula(self):
        _, S = _summary()
        for key, p in S["periods"].items():
            r = p["receipt_order_ratio_pct"]
            if p["orders"]:
                self.assertAlmostEqual(r, round(p["receipts"] / p["orders"] * 100, 2), places=2, msg=key)
            else:
                self.assertIsNone(r, msg=key)

    def test_monthly_series_aligns(self):
        _, S = _summary()
        month_keys = S["meta"]["tab_groups"]["月"]
        rom = S["receipt_order_monthly"]
        self.assertEqual(len(rom), len(month_keys))
        for (label, rec, order, ratio), k in zip(rom, month_keys):
            p = S["periods"][k]
            self.assertAlmostEqual(rec, p["receipts"], places=2)
            self.assertAlmostEqual(order, p["orders"], places=2)
            self.assertEqual(ratio, p["receipt_order_ratio_pct"])


class TestRenderGuards(unittest.TestCase):
    """前端守卫：自包含 + 不做金额运算 + 含关键结构。"""
    @classmethod
    def setUpClass(cls):
        cfg, S = _summary()
        cls.html = render.render_dashboard(S, cfg, assets.load_logo_base64(cfg))

    def test_no_client_side_math(self):
        for bad in ("toFixed(", "parseFloat(", "parseInt("):
            self.assertNotIn(bad, self.html, f"前端出现金额运算 {bad}，违反'客户端不算数'铁律")

    def test_self_contained(self):
        self.assertNotIn('src="http', self.html)
        self.assertNotIn("<script src", self.html)

    def test_structure(self):
        for token in ("基本情况", "经营利润", "管理利润表", "税前利润", "附加税费",
                      "回款情况", "themeBtn", "kpi-grid"):
            self.assertIn(token, self.html, token)

    def test_dark_default(self):
        # :root 是暗色（默认），.theme-light 才是浅色
        self.assertIn(":root{", self.html)
        self.assertIn(".theme-light{", self.html)

    def test_profit_formula_strip(self):
        # 板块③下方「计算逻辑」公式条：三条公式在位（收入/毛利率/集中度），静态口径
        self.assertIn('class="pr-formula"', self.html)
        self.assertIn("计算逻辑", self.html)
        self.assertIn("交付额 ÷ 1.06", self.html)
        self.assertIn("毛利 ÷ 收入", self.html)
        self.assertIn("前5大收入 ÷ 期内总收入", self.html)


class TestReceiptsBudgetLayout(unittest.TestCase):
    """回款情况 + 部门费用预算执行：填了年预算 → 同一 grid-2e 两列并排（各半宽变小）；
    没填 → 回款独占整宽、不塞进半吊空列（预算卡本就不渲染）。"""
    GRID = '<div class="grid-2e rb-grid" style="margin-top:16px"><div class="period-receipts">'
    FULL = '<div class="period-receipts" style="margin-top:16px">'
    # 预算卡真正渲染才有的唯一标记（"部门费用预算执行"整词在 CSS 注释里恒在，不能拿来判断）
    BUDGET_CARD = "已用/年预算 · 口径：台账白名单内含税"

    @staticmethod
    def _render(dept_budget):
        cfg, S = _summary()
        S["meta"]["dept_budget"] = dept_budget   # 注入/清空，确定性覆盖两个分支
        return render.render_dashboard(S, cfg, assets.load_logo_base64(cfg))

    def test_side_by_side_when_budget_present(self):
        db = {"year": 2026, "rows": [{"dept": "示例部", "used": 10.0, "target": 8.0, "pct": 125.0}]}
        html = self._render(db)
        self.assertIn(self.GRID, html)              # 回款作为左列、被 grid-2e 包住
        self.assertIn(self.BUDGET_CARD, html)       # 预算卡作为右列同框渲染
        self.assertNotIn(self.FULL, html)           # 有预算就不走整宽兜底

    def test_receipts_full_width_when_no_budget(self):
        html = self._render(None)
        self.assertIn("回款情况", html)
        self.assertNotIn(self.BUDGET_CARD, html)    # 没填=预算卡不渲染
        self.assertIn(self.FULL, html)              # 回款走整宽包裹
        self.assertNotIn(self.GRID, html)           # 不把回款单独塞进两列 grid


class TestRankingsAndRanges(unittest.TestCase):
    """板块③排名（下单按部门/销售、回款按客户）+ 自定义月区间周期。"""

    def test_compute_ranking_sorted_top_others(self):
        rows = ([{"名": "甲", "额": 100, "日": "2026-03-05"}] * 2
                + [{"名": "乙", "额": 350, "日": "2026-03-08"}]
                + [{"名": "", "额": 50, "日": "2026-03-09"}]        # 空名归（未填）
                + [{"名": "丙", "额": 999, "日": "2026-07-01"}])     # 期外不计
        import datetime as dt
        rk = profit.compute_ranking(rows, "名", "额", "日",
                                    dt.date(2026, 3, 1), dt.date(2026, 3, 31), top=2)
        self.assertEqual([i["name"] for i in rk["items"]], ["乙", "甲"])   # 降序
        self.assertEqual(rk["items"][1], {"name": "甲", "amount": 200.0, "count": 2})
        # v7.4：（未填）不再进排名/其余，单拆 unfilled 置底展示（total 仍含它=守恒）
        self.assertIsNone(rk["others"])
        self.assertEqual(rk["unfilled"], {"amount": 50.0, "count": 1})
        self.assertAlmostEqual(rk["total"], 600.0)

    def test_period_ranges_include_month_spans(self):
        import datetime as dt, periods
        r = periods.all_period_ranges(dt.date(2026, 7, 15))
        self.assertIn("2026年1-3月", r)
        label, start, end, group = r["2026年1-3月"]
        self.assertEqual((label, group), ("2026年1~3月", "区间"))
        self.assertEqual((start, end), (dt.date(2026, 1, 1), dt.date(2026, 3, 31)))
        self.assertNotIn("2026年3-1月", r)                # 只生成 m1<m2
        self.assertNotIn("2026年7-8月", r)                # 未来月不生成
        # 组合数 = C(7,2)=21
        self.assertEqual(len([k for k in r if r[k][3] == "区间"]), 21)

    def test_rendered_rankings_and_picker(self):
        cfg, S = _summary()
        html = render.render_dashboard(S, cfg, assets.load_logo_base64(cfg))
        for token in ("下单与回款排名", "下单 · 按部门", "下单 · 按销售", "回款 · 按客户",
                      "periodBtn", "ppanel", "pp-grid"):
            self.assertIn(token, html, token)
        # 区间周期块已预渲染（前端只切显示、不算数）
        yr = S["meta"]["year"]
        if S["meta"]["tab_groups"]["区间"]:
            self.assertIn(f'data-blk="{S["meta"]["tab_groups"]["区间"][0]}"', html)
        # 区间周期的排名 = 成员月排名之和（口径自洽抽查：1-2月 总额 == 1月+2月）
        k12, k1, k2 = f"{yr}年1-2月", f"{yr}年1月", f"{yr}年2月"
        P = S["periods"]
        if k12 in P:
            self.assertAlmostEqual(P[k12]["rankings"]["orders_by_dept"]["total"],
                                   round(P[k1]["rankings"]["orders_by_dept"]["total"]
                                         + P[k2]["rankings"]["orders_by_dept"]["total"], 2), places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
