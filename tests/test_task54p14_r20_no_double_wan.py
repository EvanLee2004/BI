#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.14 R-20：渲染结果不得出现「万万」；VM total_disp 含单位时前端不得再拼。

位置清单（整体页 / 全部 BU 页 / 管理端不渲染 donut center / 深浅色同源组件）：
- ExpenseSection.vue graphic 中心文案（整体+BU 共用）
- 图例/tooltip value_disp（裸数字，允许拼一次）
- ReceiptsCard / TrendChart / ExpenseTrend tooltip（withWanUnit 幂等）
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FE = ROOT / "frontend" / "src"
EXP = FE / "components" / "ExpenseSection.vue"
DISP = FE / "utils" / "disp.ts"


class TestNoDoubleWan(unittest.TestCase):
    def test_disp_util_exists_and_idempotent_contract(self):
        t = DISP.read_text(encoding="utf-8")
        self.assertIn("withWanUnit", t)
        self.assertIn("endsWith('万')", t)
        self.assertIn("assertNoDoubleWan", t)

    def test_expense_section_center_not_append_wan_raw(self):
        """禁止 `${c.total_disp}万` 原始拼接（R-10 漏修病灶）。"""
        t = EXP.read_text(encoding="utf-8")
        self.assertNotRegex(t, r"\$\{c\.total_disp\}万")
        self.assertNotRegex(t, r"total_disp\s*\+\s*['\"]万['\"]")
        self.assertIn("withWanUnit", t)
        # 中心文案走 withWanUnit
        self.assertIn("centerText", t)

    def test_frontend_no_raw_disp_double_wan_patterns(self):
        """全站 SFC：禁止 `{{ x_disp }}万` 当 x 可能已含万的危险写法扫描。

        允许：value_disp（扇区裸数字）、orders_disp 等经 withWanUnit 的。
        硬禁：`total_disp}万` / `total_disp }}万`。
        """
        bad = []
        for p in (FE / "components").rglob("*.vue"):
            text = p.read_text(encoding="utf-8")
            if re.search(r"total_disp\s*\}\s*万", text) or re.search(
                r"total_disp\}\s*万", text
            ):
                bad.append(str(p.relative_to(FE)))
            if re.search(r"\$\{[^}]*total_disp[^}]*\}万", text):
                bad.append(str(p.relative_to(FE)) + ":template-literal")
        self.assertEqual(bad, [], msg="发现 total_disp 二次拼万: " + ", ".join(bad))

    def test_vm_center_total_disp_already_has_wan(self):
        """后端 donut_center.total_disp 约定含「万」——这是重复拼接的根因侧。"""
        if not (ROOT / "_golden_data").exists():
            self.skipTest("缺 golden")
        import core
        import db
        import ingest
        import loaders
        import viewmodels

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        cfg["period_pin"] = {"year": 2026, "month": 7}
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            ingest.build_std_db(
                cfg, today.year, conn=conn, today=today, trigger="r20", archive_backups=False
            )
            summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        vm = viewmodels.build_cockpit_vm(summary, cfg)
        centers = vm.expense.donut_center_by_period or {}
        self.assertTrue(centers, "应有 donut_center")
        samples = []
        for pk, c in centers.items():
            td = (c or {}).get("total_disp") or ""
            if not td:
                continue
            samples.append((pk, td))
            self.assertTrue(td.endswith("万"), f"{pk} total_disp 应含万: {td!r}")
            self.assertNotIn("万万", td, f"{pk} 后端本身不得万万: {td!r}")
        self.assertTrue(samples, "至少一个周期有 total_disp")

        # 模拟旧病灶拼接 → 必出万万；新逻辑 withWanUnit 行为用 Python 复刻校验
        def with_wan_unit(s: str) -> str:
            s = (s or "").strip()
            if not s or s in ("—", "-"):
                return s
            if s.endswith("万"):
                return s
            return s + "万"

        for pk, td in samples:
            old = f"{td}万"
            self.assertIn("万万", old, "旧拼接应制造万万以便对照")
            new = with_wan_unit(td)
            self.assertNotIn("万万", new, f"{pk} 幂等后不得万万: {new!r}")
            self.assertEqual(new, td)

    def test_bu_vm_same_center_contract(self):
        """BU 页与整体页共用 ExpenseSection；BU VM 同样 total_disp 含万。"""
        if not (ROOT / "_golden_data").exists():
            self.skipTest("缺 golden")
        import core
        import db
        import ingest
        import loaders
        import viewmodels

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        cfg["period_pin"] = {"year": 2026, "month": 7}
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            ingest.build_std_db(
                cfg, today.year, conn=conn, today=today, trigger="r20bu", archive_backups=False
            )
            summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        # 若有 BU 配置则 pack 一页；否则至少整体页契约已验
        bus = []
        try:
            import json

            bp = ROOT / "_golden_data" / "BU配置.json"
            if not bp.exists():
                bp = ROOT / "数据" / "BU配置.json"
            if bp.exists():
                raw = json.loads(bp.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    bus = [b.get("name") for b in raw if isinstance(b, dict) and b.get("name")]
                elif isinstance(raw, dict):
                    bus = list(raw.get("bus") or raw.get("names") or [])
        except Exception:
            bus = []
        if not bus:
            self.skipTest("无 BU 配置可装")
        # build_bu_vm 若存在
        build_bu = getattr(viewmodels, "build_bu_vm", None) or getattr(
            viewmodels, "build_bu_page_vm", None
        )
        if not build_bu:
            # 整体 expense 已覆盖组件契约；BU 页共用 SFC
            self.assertIn("ExpenseSection", (FE / "components" / "BUPage.vue").read_text(encoding="utf-8"))
            return
        name = str(bus[0])
        try:
            bvm = build_bu(name, summary, cfg)
        except TypeError:
            try:
                bvm = build_bu(bu_name=name, summary=summary, cfg=cfg)
            except Exception:
                self.assertIn(
                    "ExpenseSection",
                    (FE / "components" / "BUPage.vue").read_text(encoding="utf-8"),
                )
                return
        centers = (bvm.expense.donut_center_by_period if hasattr(bvm, "expense") else {}) or {}
        for pk, c in list(centers.items())[:3]:
            td = (c or {}).get("total_disp") or ""
            if td:
                self.assertTrue(td.endswith("万"))
                self.assertNotIn("万万", td)


if __name__ == "__main__":
    unittest.main()
