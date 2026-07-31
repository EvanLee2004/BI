# -*- coding: utf-8 -*-
"""3.6.0 G4：重点客户金额轴 — 驱动 shipped 纯函数 + dist 契约。

禁止 source-grep theater：须执行 resolveAmountAxisMax / selectedVsGlobalAxisProbe，
并断言 2/20/50/100/200 万选中组合；dist 重建后不得再把 amountAxis.max 并入 Y 上限。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
AXIS_TS = FE / "charts" / "keyCustomersAxis.ts"
CHART_TS = FE / "charts" / "keyCustomersChart.ts"
DIST = ROOT / "frontend" / "dist"


def _run_axis_node(expr_js: str) -> dict:
    """用 tsx 加载 shipped keyCustomersAxis.ts 并 eval 表达式（须返回 JSON 对象）。"""
    axis_url = AXIS_TS.resolve().as_uri()
    script = f"""
import {{
  resolveAmountAxisMax,
  peakOfSeries,
  selectedVsGlobalAxisProbe,
  AMOUNT_AXIS_HEADROOM,
}} from '{axis_url}';
const out = ({expr_js});
console.log(JSON.stringify(out));
"""
    env = {**os.environ, "npm_config_yes": "true"}
    candidates = [
        [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsx"), "-e", script],
        ["npx", "--yes", "tsx", "-e", script],
    ]
    last = ""
    for cmd in candidates:
        try:
            r = subprocess.run(
                cmd,
                cwd=str(ROOT / "frontend"),
                capture_output=True,
                text=True,
                timeout=90,
                env=env,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            last = str(e)
            continue
        if r.returncode != 0:
            last = (r.stderr or r.stdout or "")[:500]
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
        if not lines:
            last = f"no json in stdout: {r.stdout[:300]}"
            continue
        return json.loads(lines[-1])
    raise AssertionError(f"tsx must run shipped keyCustomersAxis.ts: {last}")


class TestResolveAmountAxisMaxShipped(unittest.TestCase):
    """驱动 frontend/src/charts/keyCustomersAxis.ts 真函数。"""

    def test_two_vs_two_hundred_selected_only(self):
        """选中 2 万客户时轴=2×1.08；即使 global amount_axis.max=200 也不得抬轴。"""
        out = _run_axis_node(
            "selectedVsGlobalAxisProbe({ selectedPeaksWan: [2], globalAxisMaxWan: 200 })"
        )
        self.assertAlmostEqual(out["axisMax"], 2 * 1.08, places=6)
        self.assertEqual(out["selectedPeak"], 2)
        # 若错误使用 global，小客高度比会变成 2/200=0.01；正确为选中峰值/200
        self.assertLess(out["ratioIfUsedGlobal"], 0.02)

    def test_combo_peaks_2_20_50_100_200(self):
        """多组合：轴=当前选中峰值 max ×1.08，与全局 200 无关。"""
        combos = [
            ([2], 2),
            ([2, 20], 20),
            ([20, 50], 50),
            ([50, 100], 100),
            ([100, 200], 200),
            ([2, 200], 200),
            ([2, 20, 50, 100, 200], 200),
        ]
        for peaks, expect_peak in combos:
            out = _run_axis_node(
                f"selectedVsGlobalAxisProbe({{ selectedPeaksWan: {peaks}, globalAxisMaxWan: 999 }})"
            )
            self.assertAlmostEqual(
                out["axisMax"],
                expect_peak * 1.08,
                places=6,
                msg=f"peaks={peaks} global=999 → axisMax should be {expect_peak * 1.08}, got {out}",
            )

    def test_resolve_ignores_global_explicit(self):
        out = _run_axis_node(
            "{ a: resolveAmountAxisMax(2, 200), b: resolveAmountAxisMax(200, 2), c: resolveAmountAxisMax(0, 100), h: AMOUNT_AXIS_HEADROOM }"
        )
        self.assertAlmostEqual(out["a"], 2 * 1.08, places=6)
        self.assertAlmostEqual(out["b"], 200 * 1.08, places=6)
        self.assertEqual(out["c"], 0)
        self.assertEqual(out["h"], 1.08)

    def test_headroom_constant_is_1_08(self):
        """P2-01：固定 headroom 常量 = 1.08。"""
        out = _run_axis_node("{ h: AMOUNT_AXIS_HEADROOM, m: resolveAmountAxisMax(100, null) }")
        self.assertEqual(out["h"], 1.08)
        self.assertAlmostEqual(out["m"], 108.0, places=6)

    def test_peak_of_series(self):
        out2 = _run_axis_node("{ peak: peakOfSeries([null, 2, 20, null, 5]) }")
        self.assertEqual(out2["peak"], 20)


class TestChartWiresAxisHelper(unittest.TestCase):
    def test_chart_imports_and_calls_resolve(self):
        src = CHART_TS.read_text(encoding="utf-8")
        self.assertIn("resolveAmountAxisMax", src)
        self.assertIn("from './keyCustomersAxis'", src.replace('"', "'") if False else src)
        self.assertIn("resolveAmountAxisMax(localMax", src)
        # 禁止旧写法 Math.max(Number(amountAxis?.max)
        self.assertNotRegex(src, r"Number\(amountAxis\?\.max\)")


class TestDistShippedNoGlobalAxisMax(unittest.TestCase):
    def test_dist_key_customers_bundle_ignores_amount_axis_max_for_y(self):
        """重建后的 dist 不得出现 amountAxis.max 并入 Y 上限的旧模式。"""
        bundles = list(DIST.glob("assets/*KeyCustomers*")) + list(
            DIST.glob("assets/*keyCustomers*")
        )
        # vite 可能把 chart 打进 KeyCustomersPanel chunk
        if not bundles:
            bundles = list(DIST.glob("assets/*.js"))
        self.assertTrue(bundles, "frontend/dist/assets missing — must rebuild dist into candidate")
        joined = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in bundles)
        # 旧 bug：Z=Math.max(null==(l=e.amountAxis)?void 0:l.max,p,0) 或 amountAxis.max
        bad = re.search(
            r"amountAxis[^;]{0,40}\.max[^;]{0,40}localMax|Math\.max\([^)]*amountAxis[^)]*max",
            joined,
        )
        self.assertIsNone(
            bad,
            f"dist still merges amountAxis.max into Y-axis: {bad.group(0)[:120] if bad else ''}",
        )
        # 正向：应含 resolve 语义或仅 localMax 路径（minified 可能内联为 p 变量）
        # 至少 HELP 或 compare 5 / 不得默认 3 客
        self.assertNotIn("最多 3 客比较", joined)


class TestCompareMaxFiveEndToEnd(unittest.TestCase):
    def test_help_line_and_vm_say_five(self):
        from domain.key_customers.compute import HELP_LINE_CLICK

        self.assertIn("5 客", HELP_LINE_CLICK)
        self.assertNotIn("3 客", HELP_LINE_CLICK)
        vm_src = (ROOT / "src/viewmodels/key_customers.py").read_text(encoding="utf-8")
        self.assertIn('"compare_max": 5', vm_src)
        fe = (FE / "composables/useKeyCustomers.ts").read_text(encoding="utf-8")
        # 缺 VM 时 fallback 5 而非 3
        self.assertRegex(fe, r":\s*5\b|Math\.min\(5")


if __name__ == "__main__":
    unittest.main()
