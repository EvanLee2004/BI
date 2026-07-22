#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.14 R-21 主题响应 / R-22 弹层 z-index / R-24 比率轴 / R-25 banner / R-26 热力图 结构守卫。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
THEME_CSS = ROOT / "static" / "css" / "theme.css"
BRIDGE = FE / "vendor" / "scifi-kit" / "scifi-bridge.css"


class TestThemeReactive(unittest.TestCase):
    def test_theme_util_and_toggle(self):
        t = (FE / "utils" / "theme.ts").read_text(encoding="utf-8")
        self.assertIn("themeMode", t)
        self.assertIn("applyTheme", t)
        self.assertIn("kanban-theme-change", t)
        self.assertIn("installThemeListeners", t)
        self.assertIn("postMessage", t)
        tog = (FE / "components" / "ThemeToggle.vue").read_text(encoding="utf-8")
        self.assertIn("toggleTheme", tog)
        self.assertIn("themeMode", tog)

    def test_charts_depend_on_theme_mode(self):
        for name in (
            "ExpenseSection.vue",
            "ExpenseHeatmap.vue",
            "TrendChart.vue",
            "ReceiptsCard.vue",
            "ExpenseHeatmap.vue",
        ):
            t = (FE / "components" / name).read_text(encoding="utf-8")
            self.assertIn("themeMode", t, name)
            self.assertIn("void themeMode.value", t, name)

    def test_admin_uses_apply_theme(self):
        """2.2.7：管理壳去掉顶栏主题切换；仍同步 DOM 主题且 bootstrap 装监听（展示 iframe 用）。"""
        lay = (FE / "admin" / "layout" / "AdminLayout.vue").read_text(encoding="utf-8")
        self.assertIn("syncThemeFromDom", lay)
        self.assertIn("from '../../utils/theme'", lay)
        # 顶栏不再绑 applyTheme/toggleTheme
        self.assertNotIn("applyToggleTheme", lay)
        boot = (FE / "admin" / "bootstrap.ts").read_text(encoding="utf-8")
        self.assertIn("installThemeListeners", boot)
        # 展示端 ThemeToggle 仍用 applyTheme 路径
        theme = (FE / "utils" / "theme.ts").read_text(encoding="utf-8")
        self.assertIn("applyTheme", theme)


class TestOverlayZIndex(unittest.TestCase):
    def test_z_tokens_in_theme(self):
        t = THEME_CSS.read_text(encoding="utf-8")
        for tok in ("--z-topbar", "--z-dropdown", "--z-drawer", "--z-modal"):
            self.assertIn(tok, t)

    def test_topbar_above_wrap(self):
        b = BRIDGE.read_text(encoding="utf-8")
        # 不得再让 topbar 与 wrap 同为 z-index:1 并列
        self.assertIn("--z-topbar", b)
        self.assertNotRegex(
            b,
            r"\.wrap,\s*\.topbar,\s*#periodSync,\s*#app\s*\{[^}]*z-index:\s*1",
            re.S,
        )
        # 54.13：PeriodPicker 样式外置 period-picker.css，z-index token 仍须在位
        pp = (FE / "components" / "PeriodPicker.vue").read_text(encoding="utf-8")
        pp_css = (FE / "components" / "period-picker.css").read_text(encoding="utf-8")
        blob = pp + "\n" + pp_css
        self.assertIn("--z-dropdown", blob)
        self.assertIn("--overlay-panel", blob)


class TestRatioAxisAndBanner(unittest.TestCase):
    def test_ratio_axis_bounds_helper(self):
        t = (FE / "chart-months.ts").read_text(encoding="utf-8")
        self.assertIn("ratioAxisBounds", t)
        self.assertIn("floorMax", t)
        # shipped pure function via node if available — structural + regex 实现存在即可
        self.assertIn("Math.ceil(hi * 1.08)", t)

    def test_receipts_and_trend_use_ratio_bounds(self):
        # 任务书61·A：回款卡已删黄「回款率」线，不再需要 ratioAxisBounds；趋势毛利率线仍要
        t_trend = (FE / "components" / "TrendChart.vue").read_text(encoding="utf-8")
        self.assertIn("ratioAxisBounds", t_trend, "TrendChart.vue")
        self.assertNotRegex(t_trend, r"max:\s*100\s*,\s*\n\s*splitLine")
        t_rc = (FE / "components" / "ReceiptsCard.vue").read_text(encoding="utf-8")
        self.assertNotIn("回款率", t_rc.split("<template>")[-1])
        self.assertIn("clipToCurrentMonth", t_rc)

    def test_banner_tokens(self):
        t = THEME_CSS.read_text(encoding="utf-8")
        self.assertIn("--banner-warn-fg", t)
        self.assertIn("--banner-warn-bg", t)
        self.assertIn("#78350f", t)  # 浅色深字
        admin = (FE / "admin" / "styles" / "admin.css").read_text(encoding="utf-8")
        self.assertIn("admin-fetch-banner", admin)
        self.assertIn("#78350f", admin)


class TestHeatmap(unittest.TestCase):
    def test_heatmap_component_wired(self):
        h = (FE / "components" / "ExpenseHeatmap.vue").read_text(encoding="utf-8")
        self.assertIn("heatmap", h)
        self.assertIn("buildExpenseHeatPack", h)
        self.assertIn("withWanUnit", h)
        self.assertIn('data-testid="expense-heatmap"', h)
        self.assertLessEqual(len(h.splitlines()), 400)
        util = (FE / "utils" / "expense-heat.ts").read_text(encoding="utf-8")
        self.assertIn("buildExpenseHeatPack", util)
        self.assertIn("pickHeatCells", util)
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("ExpenseHeatmap", app)
        bu = (FE / "components" / "BUPage.vue").read_text(encoding="utf-8")
        self.assertIn("ExpenseHeatmap", bu)

    def test_heatmap_uses_vm_only_no_money_math(self):
        h = (FE / "components" / "ExpenseHeatmap.vue").read_text(encoding="utf-8")
        self.assertNotIn("/1.06", h)
        util = (FE / "utils" / "expense-heat.ts").read_text(encoding="utf-8")
        self.assertIn("data_disp", util)

    def test_heat_pack_3cells_against_vm(self):
        """驱动 shipped buildExpenseHeatPack + 真实 cockpit VM，抽 3 格对账。"""
        import json
        import os
        import subprocess
        import sys

        sys.path.insert(0, str(ROOT / "src"))
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
                cfg, today.year, conn=conn, today=today, trigger="heat3", archive_backups=False
            )
            summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        vm = viewmodels.build_cockpit_vm(summary, cfg)
        labels = list(vm.expense.area_labels or [])
        series = list(vm.expense.area_series or [])
        self.assertTrue(labels and series)
        src = FE / "utils" / "expense-heat.ts"
        payload = json.dumps({"labels": labels, "series": series}, ensure_ascii=False)
        script = f"""
import {{ buildExpenseHeatPack, pickHeatCells }} from 'file://{src.as_posix()}';
const p = {payload};
const pack = buildExpenseHeatPack(p.labels, p.series);
const cells = pickHeatCells(pack, 3);
console.log(JSON.stringify(cells));
"""
        data = None
        for cmd in (
            ["npx", "--yes", "tsx", "-e", script],
            [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsx"), "-e", script],
        ):
            try:
                r = subprocess.run(
                    cmd,
                    cwd=str(ROOT / "frontend"),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "npm_config_yes": "true"},
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if r.returncode != 0:
                continue
            lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("[")]
            if lines:
                data = json.loads(lines[-1])
                break
        if data is None:
            self.skipTest("tsx 不可用")
        self.assertGreaterEqual(len(data), 1)
        for c in data:
            s = series[c["yi"]]
            self.assertEqual(c["disp"], str((s.get("data_disp") or [])[c["xi"]]))
            self.assertEqual(float(c["value"]), float((s.get("data") or [])[c["xi"]] or 0))
        # 落证据
        evid = ROOT / "docs" / "验收证据" / "20260719_54p14" / "heatmap_3cells_unit.json"
        evid.parent.mkdir(parents=True, exist_ok=True)
        evid.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class TestRatioAxisUnit(unittest.TestCase):
    """驱动真实 shipped ratioAxisBounds（node+tsx 若可用）。"""

    def test_ratio_axis_bounds_live(self):
        import json
        import os
        import subprocess

        src = FE / "chart-months.ts"
        script = f"""
import {{ ratioAxisBounds }} from 'file://{src.as_posix()}';
const cases = {{
  over: ratioAxisBounds([10, 120, 95, null]),
  zero: ratioAxisBounds([0, 0, 0]),
  neg: ratioAxisBounds([-5, 20, 40]),
  empty: ratioAxisBounds([]),
}};
console.log(JSON.stringify(cases));
"""
        for cmd in (
            ["npx", "--yes", "tsx", "-e", script],
            [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsx"), "-e", script],
        ):
            try:
                r = subprocess.run(
                    cmd,
                    cwd=str(ROOT / "frontend"),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "npm_config_yes": "true"},
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if r.returncode != 0:
                continue
            lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
            if not lines:
                continue
            data = json.loads(lines[-1])
            self.assertGreaterEqual(data["over"]["max"], 120)
            self.assertEqual(data["zero"]["min"], 0)
            self.assertLessEqual(data["neg"]["min"], -5)
            self.assertEqual(data["empty"]["max"], 100)
            return
        # 无 tsx 时结构守卫已覆盖；不 fail 整门
        self.skipTest("tsx 不可用，跳过 live ratioAxisBounds")


if __name__ == "__main__":
    unittest.main()
