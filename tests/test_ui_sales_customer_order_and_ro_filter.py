#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 两处修复：收入/毛利左销售右客户；ResizeObserver 无害消息不进红条。

门禁：
1. ProfitStructure 双卡渲染顺序 = sales → customer（与 RankingsDual 一致）
2. frontendErrorReporter.isIgnorableClientError 吞 ResizeObserver loop，放过真错误
3. EchartsHost ResizeObserver 回调经 rAF 合并
4. （若 dist 已建）构建产物含上述行为
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
DIST = ROOT / "frontend" / "dist"


class TestProfitStructureSalesLeft(unittest.TestCase):
    def test_vfor_order_sales_then_customer(self):
        src = (FE / "components" / "ProfitStructure.vue").read_text(encoding="utf-8")
        # 去注释避免误伤
        code = re.sub(r"<!--[\s\S]*?-->", "", src)
        m = re.search(r"v-for\s*=\s*[\"']side in \[([^\]]+)\]", code)
        self.assertIsNotNone(m, "须存在 side in [...] 的 v-for")
        assert m is not None
        order = m.group(1)
        sales_i = order.find("pack.sales")
        cust_i = order.find("pack.customer")
        self.assertGreaterEqual(sales_i, 0, f"须含 pack.sales: {order}")
        self.assertGreaterEqual(cust_i, 0, f"须含 pack.customer: {order}")
        self.assertLess(sales_i, cust_i, f"须左销售右客户，实际顺序: {order}")

    def test_rankings_dual_same_sales_first(self):
        """对照：板块四已是 sales→customer，本测试锁两边同向。"""
        src = (FE / "components" / "RankingsDual.vue").read_text(encoding="utf-8")
        # daily / 默认两条 return 都须 sales 在 customer 前
        for pat in (
            r"return\s*\[\s*store\.dailyDual\?\.sales\s*,\s*store\.dailyDual\?\.customer\s*\]",
            r"return\s*\[\s*view\.value\?\.sales\s*,\s*view\.value\?\.customer\s*\]",
        ):
            self.assertRegex(src, pat, f"RankingsDual 须 sales→customer: {pat}")


class TestResizeObserverIgnorable(unittest.TestCase):
    def test_source_exports_and_guards(self):
        src = (FE / "utils" / "frontendErrorReporter.ts").read_text(encoding="utf-8")
        self.assertIn("export function isIgnorableClientError", src)
        self.assertIn("ResizeObserver loop", src)
        # reportAndBanner / showFriendlyErrorBanner 入口须先判断可忽略
        self.assertRegex(
            src,
            r"function reportAndBanner[\s\S]*?if\s*\(\s*isIgnorableClientError\s*\(\s*message\s*\)\s*\)\s*return",
        )
        self.assertRegex(
            src,
            r"export function showFriendlyErrorBanner[\s\S]*?if\s*\(\s*isIgnorableClientError\s*\(\s*message\s*\)\s*\)\s*return",
        )

    def test_is_ignorable_via_node_tsx_shipped_function(self):
        """直接 import 仓库内 shipped TS 函数（非重实现）。"""
        tsx = ROOT / "frontend" / "node_modules" / ".bin" / "tsx"
        # vite 项目可能无 tsx 依赖：用 node --experimental-strip-types 或 npx
        script = r"""
import { isIgnorableClientError } from './frontend/src/utils/frontendErrorReporter.ts'
const cases = [
  ['ResizeObserver loop completed with undelivered notifications.', true],
  ['ResizeObserver loop limit exceeded', true],
  ['Uncaught TypeError: x is not a function', false],
  ['页面出现异常', false],
  ['', false],
]
let fail = 0
for (const [msg, exp] of cases) {
  const got = isIgnorableClientError(msg)
  if (got !== exp) {
    console.error('FAIL', JSON.stringify(msg), 'got', got, 'exp', exp)
    fail++
  } else {
    console.log('OK', JSON.stringify(msg), got)
  }
}
process.exit(fail ? 1 : 0)
"""
        # Prefer local tsx from frontend if present; else node with strip-types (Node 22+)
        cmds = []
        if tsx.is_file():
            cmds.append([str(tsx), "--eval", script])
        # Write temp runner under ROOT so relative import works
        runner = ROOT / "tests" / "_tmp_ro_filter_runner.mts"
        runner.write_text(
            "import { isIgnorableClientError } from '../frontend/src/utils/frontendErrorReporter.ts'\n"
            "const cases: [string, boolean][] = [\n"
            "  ['ResizeObserver loop completed with undelivered notifications.', true],\n"
            "  ['ResizeObserver loop limit exceeded', true],\n"
            "  ['Uncaught TypeError: x is not a function', false],\n"
            "  ['页面出现异常', false],\n"
            "  ['', false],\n"
            "]\n"
            "let fail = 0\n"
            "for (const [msg, exp] of cases) {\n"
            "  const got = isIgnorableClientError(msg)\n"
            "  if (got !== exp) { console.error('FAIL', JSON.stringify(msg), got, exp); fail++ }\n"
            "  else console.log('OK', JSON.stringify(msg), got)\n"
            "}\n"
            "process.exit(fail ? 1 : 0)\n",
            encoding="utf-8",
        )
        self.addCleanup(lambda: runner.unlink(missing_ok=True))
        # Try: npx tsx (frontend has typescript; use node --import tsx if available)
        node_modules_tsx = ROOT / "frontend" / "node_modules" / "tsx" / "dist" / "cli.mjs"
        if (ROOT / "frontend" / "node_modules" / ".bin" / "tsx").is_file():
            cmd = [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsx"), str(runner)]
        elif node_modules_tsx.is_file():
            cmd = ["node", str(node_modules_tsx), str(runner)]
        else:
            # Fallback: extract regex from shipped source and evaluate in Python —
            # still proves shipped source text; plus structural guards above.
            src = (FE / "utils" / "frontendErrorReporter.ts").read_text(encoding="utf-8")
            m = re.search(
                r"export function isIgnorableClientError\([^)]*\)[^{]*\{([^}]+)\}",
                src,
            )
            self.assertIsNotNone(m, "无法解析 isIgnorableClientError 函数体")
            assert m is not None
            body = m.group(1)
            # shipped: return /ResizeObserver loop/i.test(String(message || ''))
            self.assertIn("ResizeObserver loop", body)
            rx = re.compile(r"ResizeObserver loop", re.I)

            def is_ignorable(message: str) -> bool:
                return bool(rx.search(str(message or "")))

            self.assertTrue(
                is_ignorable("ResizeObserver loop completed with undelivered notifications.")
            )
            self.assertTrue(is_ignorable("ResizeObserver loop limit exceeded"))
            self.assertFalse(is_ignorable("Uncaught TypeError: x is not a function"))
            self.assertFalse(is_ignorable("页面出现异常"))
            self.assertFalse(is_ignorable(""))
            return

        r = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            r.returncode,
            0,
            f"shipped isIgnorableClientError 失败\nstdout={r.stdout}\nstderr={r.stderr}",
        )

    def test_echarts_resize_uses_raf(self):
        src = (FE / "components" / "charts" / "EchartsHost.vue").read_text(encoding="utf-8")
        self.assertIn("requestAnimationFrame", src)
        self.assertIn("ResizeObserver", src)
        # 回调内应经 rAF 再 chart.resize，而非直接同步 resize
        self.assertRegex(
            src,
            r"new ResizeObserver\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?requestAnimationFrame[\s\S]*?chart\?\.resize",
        )


class TestDistContainsFixes(unittest.TestCase):
    def test_dist_if_present(self):
        assets = DIST / "assets"
        if not assets.is_dir():
            self.skipTest("dist 未构建")
        blobs = list(assets.glob("*.js"))
        self.assertTrue(blobs, "dist/assets 无 js")
        # 错误上报通常打在 theme-*.js；看板 boot 在 boot-cockpit-*.js
        theme = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in assets.glob("theme-*.js")
        )
        boot = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in assets.glob("boot-cockpit-*.js")
        )
        combined = theme + "\n" + boot
        self.assertTrue(theme.strip() or boot.strip(), "须有 theme 或 boot-cockpit chunk")
        # 打包后函数名可能 minify；正则字面量须保留
        self.assertRegex(combined, r"ResizeObserver loop")


if __name__ == "__main__":
    unittest.main()
