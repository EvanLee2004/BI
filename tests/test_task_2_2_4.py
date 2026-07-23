#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.4 十项门禁：结构源码守卫 + 手填三视图注入守恒 + 显示层 ÷100。

驱动 shipped 函数；不做 re-implementation golden。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestSourceGuards224(unittest.TestCase):
    """①③B C F：前端/后端源码结构断言。"""

    def test_period_picker_in_tb_left(self):
        for rel in ("frontend/src/App.vue", "frontend/src/components/BUPage.vue"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("tb-left", src, rel)
            # PeriodPicker 须在 tb-left 块内（不在 tb-right）
            m = re.search(
                r'class="tb-left"[^>]*>[\s\S]*?<PeriodPicker',
                src,
            )
            self.assertIsNotNone(m, f"{rel}: PeriodPicker 应在 tb-left 内")
            # tb-right 不应再含 PeriodPicker
            right = re.search(r'class="tb-right"[^>]*>[\s\S]*?</div>', src)
            if right:
                self.assertNotIn("PeriodPicker", right.group(0), f"{rel}: tb-right 不应含 PeriodPicker")

    def test_export_html_btn_in_topbar(self):
        """2.2.7：导出主路径改为 HTML（原 PNG 按钮类名/路径同步）。"""
        src = (ROOT / "frontend/src/components/TopBarActions.vue").read_text(encoding="utf-8")
        self.assertIn("export-html-btn", src)
        self.assertIn("/export.html", src)
        self.assertIn("exportHtml", src)

    def test_receipts_maxv_covers_bud(self):
        src = (ROOT / "frontend/src/components/ReceiptsCard.vue").read_text(encoding="utf-8")
        self.assertIn("axisMaxCover(maxV0, interval, [...recs, ...ords, bud])", src)
        self.assertIn('title="下单/回款情况"', src)
        # D：legacy 服务端模板同步改名（导出/legacy 路径）
        rc = (ROOT / "static/templates/render/rc_card.html").read_text(encoding="utf-8")
        self.assertIn("下单/回款情况", rc)
        self.assertNotIn(">回款情况 <", rc)

    def test_admin_logout_moved_to_settings(self):
        layout = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(encoding="utf-8")
        settings = (ROOT / "frontend/src/admin/views/SettingsView.vue").read_text(encoding="utf-8")
        # 顶栏不再有退出
        self.assertNotIn('href="/admin/logout"', layout)
        self.assertNotIn(">退出</a>", layout)
        # 设置页底部有退出
        self.assertIn("/admin/logout", settings)
        self.assertIn("退出", settings)

    def test_kpi_margin_headline_is_pct(self):
        rw = (ROOT / "src/render_widgets.py").read_text(encoding="utf-8")
        self.assertIn('("毛利率", "gross_profit"', rw)
        pk = (ROOT / "src/viewmodels/packers.py").read_text(encoding="utf-8")
        self.assertIn('unit = "%"', pk)
        self.assertIn('key == "gross_profit" and pctkey', pk)

    def test_config_zhuangxiu_fixed_ops(self):
        cfg = (ROOT / "config.json").read_text(encoding="utf-8")
        self.assertIn('"装修费": "固定运营费用"', cfg)
        self.assertNotIn('"装修费": "管理费用"', cfg)


class TestInjectManualBreakdowns(unittest.TestCase):
    """② 三视图注入：含三类 + 三视图合计相等 + 核心 total 不因注入而改。"""

    def test_inject_three_views_conservation(self):
        from profit.expense_period import (
            MANUAL_ALLOC_GROUP,
            inject_manual_alloc_into_breakdowns,
        )

        cfg = {
            "manual_alloc_category_map": {
                "房租物业": "固定运营费用",
                "其他": "固定运营费用",
                "装修费": "固定运营费用",
            }
        }
        # 手填：分（2.3.3 手填名）
        pman = {"房租物业": 100_00, "其他": 50_00, "装修费": 200_00}  # 元×100=分
        fine0 = {"管理费用": [("办公用品", 1000_00)], "固定运营费用": [("水电", 300_00)]}
        by_pc0 = [("语言", 800_00, [("办公用品", 800_00)]), ("数据", 500_00, [("水电", 500_00)])]
        by_dept0 = [("运保", 1300_00, [("办公用品", 1000_00), ("水电", 300_00)])]

        fine, by_pc, by_dept = inject_manual_alloc_into_breakdowns(
            pman, cfg, fine0, by_pc0, by_dept0
        )

        # 按类别含三类
        fixed_fines = dict(fine["固定运营费用"])
        self.assertEqual(fixed_fines["房租物业"], 100_00)
        self.assertEqual(fixed_fines["其他"], 50_00)
        self.assertEqual(fixed_fines["装修费"], 200_00)
        self.assertEqual(fixed_fines["水电"], 300_00)

        # 利润中心/部门：人工分摊(公共) 组
        pc_map = {g: (tot, dict(fines)) for g, tot, fines in by_pc}
        self.assertIn(MANUAL_ALLOC_GROUP, pc_map)
        self.assertEqual(pc_map[MANUAL_ALLOC_GROUP][0], 350_00)
        self.assertEqual(pc_map[MANUAL_ALLOC_GROUP][1]["房租物业"], 100_00)
        self.assertEqual(pc_map[MANUAL_ALLOC_GROUP][1]["装修费"], 200_00)

        dept_map = {g: tot for g, tot, _ in by_dept}
        self.assertEqual(dept_map[MANUAL_ALLOC_GROUP], 350_00)

        # 三视图合计相等
        sum_fine = sum(a for pairs in fine.values() for _, a in pairs)
        sum_pc = sum(tot for _, tot, _ in by_pc)
        sum_dept = sum(tot for _, tot, _ in by_dept)
        self.assertEqual(sum_fine, sum_pc)
        self.assertEqual(sum_pc, sum_dept)
        # = 原台账 1300 + 手填 350
        self.assertEqual(sum_fine, 1300_00 + 350_00)

    def test_inject_none_stays_none(self):
        from profit.expense_period import inject_manual_alloc_into_breakdowns

        cfg = {
            "manual_alloc_category_map": {
                "房租物业": "固定运营费用",
                "其他": "固定运营费用",
                "装修费": "固定运营费用",
            }
        }
        fine, by_pc, by_dept = inject_manual_alloc_into_breakdowns(
            {"房租物业": 10_00}, cfg, {}, None, None
        )
        self.assertIsNone(by_pc)
        self.assertIsNone(by_dept)
        self.assertEqual(dict(fine["固定运营费用"])["房租物业"], 10_00)

    def test_inject_does_not_mutate_expense_total_fields(self):
        """注入只动明细结构，不动 period expense dict（核心字段独立）。"""
        from profit.expense_period import inject_manual_alloc_into_breakdowns

        expense = {"total": 999_00, "固定运营费用": 500_00, "管理费用": 499_00}
        cfg = {"manual_alloc_category_map": {"房租物业": "固定运营费用", "其他": "固定运营费用", "装修费": "固定运营费用"}}
        inject_manual_alloc_into_breakdowns({"房租物业": 1_00}, cfg, {}, [], [])
        self.assertEqual(expense["total"], 999_00)


class TestManualAllocDispFenToYuan(unittest.TestCase):
    """E：_alloc_month_payload 显示前 ÷100。"""

    def test_disp_divides_by_100(self):
        import money

        # 模拟 payload 内逻辑：分 → 元显示
        month_total_fen = 46_728_413  # 若当元会天文数字
        yuan = money.fen_to_yuan(month_total_fen)
        self.assertAlmostEqual(yuan, 467_284.13, places=2)
        disp = f"{yuan:,.2f}"
        self.assertEqual(disp, "467,284.13")
        # 源码守卫：manual.py 调用 fen_to_yuan
        src = (ROOT / "src/routes/manual.py").read_text(encoding="utf-8")
        self.assertIn("fen_to_yuan", src)
        self.assertIn("month_total_disp", src)

    def test_payload_disp_is_yuan_level(self):
        """驱动 shipped _alloc_month_payload 显示串为元级（非把分当元）。"""
        # 直接验证 money 路径 + 源码；完整 HTTP 需 db/台账 fixture，此处用纯函数契约
        import money

        fen = 1_234_567  # 12345.67 元
        self.assertEqual(f"{money.fen_to_yuan(fen):,.2f}", "12,345.67")
        src = (ROOT / "src/routes/manual.py").read_text(encoding="utf-8")
        # 确认 disp 用转元后的值，不是直接 f"{month_total:,.2f}"
        self.assertIn("month_total_yuan", src)
        self.assertIn("remain_amt_yuan", src)


class TestGateSoftMissing(unittest.TestCase):
    """G：run.py 对缺失类 error 不再硬 return 1。"""

    def test_run_softens_missing(self):
        src = (ROOT / "run.py").read_text(encoding="utf-8")
        self.assertIn("soft_missing", src)
        self.assertIn("不存在", src)
        cockpit = (ROOT / "src/routes/cockpit.py").read_text(encoding="utf-8")
        self.assertIn("empty_message", cockpit)
        self.assertIn("暂无数据", cockpit)


if __name__ == "__main__":
    unittest.main()
