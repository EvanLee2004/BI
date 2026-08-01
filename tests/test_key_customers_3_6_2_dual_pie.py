# -*- coding: utf-8 -*-
"""3.6.2：重点客户双饼六档 + 说明? + 点饼联动映射。

驱动 shipped 纯函数（tsx）与 Vue 源码契约；禁止仅硬编码期望值绕过实现。
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
DIST = ROOT / "frontend" / "dist"
DIST_ASSETS = DIST / "assets"
TIER_POOL_TS = FE / "composables" / "keyCustomersTierPool.ts"
PIE_TS = FE / "charts" / "keyCustomersStructurePies.ts"
STRUCT = FE / "components" / "key-customers" / "KeyCustomersStructure.vue"
PANEL = FE / "components" / "key-customers" / "KeyCustomersPanel.vue"
USE = FE / "composables" / "useKeyCustomers.ts"
CSS = FE / "styles" / "components" / "KeyCustomersPanel.css"


def _run_tsx_import(module_path: Path, expr_js: str, named: list[str]) -> dict:
    url = module_path.resolve().as_uri()
    names = ", ".join(named)
    script = f"""
import {{ {names} }} from '{url}';
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
            last = (r.stderr or r.stdout or "")[:600]
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
        if not lines:
            last = f"no json in stdout: {r.stdout[:300]}"
            continue
        return json.loads(lines[-1])
    raise AssertionError(f"tsx must run shipped {module_path.name}: {last}")


class TestTierPoolMappingShipped(unittest.TestCase):
    """驱动 keyCustomersTierPool.ts 真函数。"""

    def test_pool_for_tier_sabe_cde(self):
        out = _run_tsx_import(
            TIER_POOL_TS,
            """({
              S: poolForTier('S'),
              A: poolForTier('a'),
              B: poolForTier('B'),
              C: poolForTier('C'),
              D: poolForTier('d'),
              E: poolForTier('E'),
              empty: poolForTier(''),
              junk: poolForTier('X'),
            })""",
            ["poolForTier"],
        )
        self.assertEqual(out["S"], "focus")
        self.assertEqual(out["A"], "focus")
        self.assertEqual(out["B"], "focus")
        self.assertEqual(out["C"], "nurture")
        self.assertEqual(out["D"], "nurture")
        self.assertEqual(out["E"], "longtail")
        self.assertEqual(out["empty"], "longtail")
        self.assertEqual(out["junk"], "longtail")

    def test_structure_tier_click_intent(self):
        out = _run_tsx_import(
            TIER_POOL_TS,
            """({
              s: structureTierClickIntent('S'),
              b: structureTierClickIntent('b'),
              c: structureTierClickIntent('C'),
              e: structureTierClickIntent('E'),
              none: structureTierClickIntent(''),
              nullish: structureTierClickIntent(null),
            })""",
            ["structureTierClickIntent"],
        )
        self.assertIsNone(out["none"])
        self.assertIsNone(out["nullish"])
        self.assertEqual(out["s"]["pool"], "focus")
        self.assertEqual(out["s"]["filterMode"], "all")
        self.assertEqual(out["s"]["tier"], "S")
        self.assertIn("S", out["s"]["ensureTiers"])
        self.assertIn("A", out["s"]["ensureTiers"])
        self.assertEqual(out["b"]["pool"], "focus")
        self.assertEqual(out["c"]["pool"], "nurture")
        self.assertEqual(out["c"]["ensureTiers"], ["C", "D"])
        self.assertEqual(out["e"]["pool"], "longtail")
        self.assertEqual(out["e"]["ensureTiers"], ["E"])

    def test_structure_tier_toggle_clear_and_set(self):
        """3.7.2：同档再点 clear；异档 set；clearStructureFilterState 回 default pool。"""
        out = _run_tsx_import(
            TIER_POOL_TS,
            """({
              setC: applyStructureTierToggle('C', '', 'focus'),
              clearC: applyStructureTierToggle('C', 'C', 'focus'),
              clearCcase: applyStructureTierToggle('c', 'C', 'nurture'),
              switchA: applyStructureTierToggle('A', 'C', 'focus'),
              empty: applyStructureTierToggle('', 'S', 'focus'),
              clearBtn: clearStructureFilterState('focus'),
              clearNurture: clearStructureFilterState('nurture'),
            })""",
            ["applyStructureTierToggle", "clearStructureFilterState"],
        )
        self.assertEqual(out["setC"]["kind"], "set")
        self.assertEqual(out["setC"]["tier"], "C")
        self.assertEqual(out["setC"]["pool"], "nurture")
        self.assertEqual(out["clearC"]["kind"], "clear")
        self.assertEqual(out["clearC"]["tier"], "")
        self.assertEqual(out["clearC"]["pool"], "focus")
        self.assertEqual(out["clearC"]["filterMode"], "all")
        self.assertEqual(out["clearCcase"]["kind"], "clear")
        self.assertEqual(out["clearCcase"]["pool"], "nurture")
        self.assertEqual(out["switchA"]["kind"], "set")
        self.assertEqual(out["switchA"]["tier"], "A")
        self.assertEqual(out["switchA"]["pool"], "focus")
        self.assertIsNone(out["empty"])
        self.assertEqual(out["clearBtn"]["kind"], "clear")
        self.assertEqual(out["clearBtn"]["tier"], "")
        self.assertEqual(out["clearBtn"]["pool"], "focus")
        self.assertIn("S", out["clearBtn"]["ensureTiers"])
        self.assertEqual(out["clearNurture"]["pool"], "nurture")


SEL_TS = FE / "composables" / "keyCustomersSelection.ts"


class TestSelectCustomerReselectClear372(unittest.TestCase):
    """3.7.2：无对比时再点同一客户 → 取消选中；有对比不拆 compareKeys。"""

    def test_reselect_clears_when_no_compare(self):
        out = _run_tsx_import(
            SEL_TS,
            """({
              first: selectCustomerState({ selectedKey: '', compareKeys: [] }, 'k1'),
              again: selectCustomerState({ selectedKey: 'k1', compareKeys: [] }, 'k1'),
              other: selectCustomerState({ selectedKey: 'k1', compareKeys: [] }, 'k2'),
              inCompare: selectCustomerState(
                { selectedKey: 'k1', compareKeys: ['k1', 'k2'] },
                'k1',
              ),
              outsideCompare: selectCustomerState(
                { selectedKey: 'k1', compareKeys: ['k1'] },
                'k9',
              ),
            })""",
            ["selectCustomerState"],
        )
        self.assertEqual(out["first"]["selectedKey"], "k1")
        self.assertEqual(out["again"]["selectedKey"], "")
        self.assertEqual(out["again"]["compareKeys"], [])
        self.assertEqual(out["other"]["selectedKey"], "k2")
        self.assertEqual(out["inCompare"]["selectedKey"], "k1")
        self.assertEqual(out["inCompare"]["compareKeys"], ["k1", "k2"])
        self.assertEqual(out["outsideCompare"]["selectedKey"], "k9")
        self.assertEqual(out["outsideCompare"]["compareKeys"], [])


class TestStructurePieValueShipped(unittest.TestCase):
    def test_segment_pie_value_uses_count_or_wo(self):
        out = _run_tsx_import(
            PIE_TS,
            """({
              c: segmentPieValue('count', { id: 'S', count: 3, wo: 50, count_disp: '3户' }),
              a: segmentPieValue('amount', { id: 'S', count: 3, wo: 42.5, amount_disp: '100万' }),
              z: segmentPieValue('count', { id: 'E', count: 0, wo: 0 }),
              has: structureHasData([
                { id: 'S', count: 1, wo: 10 },
                { id: 'A', count: 0, wo: 0 },
              ]),
              empty: structureHasData([]),
            })""",
            ["segmentPieValue", "structureHasData"],
        )
        self.assertEqual(out["c"], 3)
        self.assertEqual(out["a"], 42.5)
        self.assertEqual(out["z"], 0)
        self.assertTrue(out["has"])
        self.assertFalse(out["empty"])


class TestDualPieAndHelpDomContract(unittest.TestCase):
    def test_structure_vue_dual_pie_hooks(self):
        src = STRUCT.read_text(encoding="utf-8")
        panel = PANEL.read_text(encoding="utf-8")
        use = USE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        for needle in (
            'data-testid="kc-structure-pies"',
            'data-testid="kc-pie-count"',
            'data-testid="kc-pie-amount"',
            "buildKeyCustomersStructurePieOption",
            "tier-click",
        ):
            self.assertIn(needle, src, needle)
        # 不再默认渲染结构条主区
        self.assertNotIn('data-testid="kc-structure-bars"', src)
        self.assertNotIn('data-testid="kc-structure-bars"', panel)
        # 说明?：无默认大段 kc-help 块；统一 HelpPopover（3.7.4）
        self.assertNotRegex(
            panel,
            r'data-testid="kc-help"(?![-\w])',
            "禁止默认整块 kc-help 长文",
        )
        self.assertIn("HelpPopover", panel)
        self.assertIn('test-id="kc-help"', panel)
        help = (FE / "components" / "base" / "HelpPopover.vue").read_text(encoding="utf-8")
        self.assertIn("testId + '-btn'", help)
        self.assertIn("testId + '-popover'", help)
        self.assertIn("helpLines", panel)
        # 联动：composable 调用 pure toggle/clear + ensure（3.7.2）
        self.assertIn("onStructureTierClick", use)
        self.assertIn("applyStructureTierToggle", use)
        self.assertIn("clearStructureFilter", use)
        self.assertIn('data-testid="kc-clear-structure"', src)
        self.assertIn("kc-structure-pies", css)
        self.assertIn("kc-help-btn", help)
        # 禁止组件内 style 块
        self.assertNotRegex(src, r"<style\b")
        self.assertNotRegex(panel, r"<style\b")

    def test_domain_pool_for_tier_matches_frontend_matrix(self):
        """后端 domain 与前端 pure 矩阵一致（S/A/B focus…）。"""
        from domain.key_customers import pool_for_tier

        fe = _run_tsx_import(
            TIER_POOL_TS,
            """({
              S: poolForTier('S'), A: poolForTier('A'), B: poolForTier('B'),
              C: poolForTier('C'), D: poolForTier('D'), E: poolForTier('E'),
            })""",
            ["poolForTier"],
        )
        for tid in ("S", "A", "B", "C", "D", "E"):
            self.assertEqual(fe[tid], pool_for_tier(tid), tid)


class TestDistHasDualPieIfBuilt(unittest.TestCase):
    def test_dist_key_customers_chunk(self):
        if not DIST_ASSETS.is_dir():
            self.skipTest("frontend/dist not built")
        blobs = []
        for g in ("*KeyCustomers*", "*keyCustomers*"):
            blobs.extend(DIST_ASSETS.glob(g))
        if not blobs:
            # 可能打进主 chunk
            blobs = list(DIST_ASSETS.glob("*.js"))[:20]
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in blobs)
        self.assertTrue(text.strip(), "dist empty")
        # 至少有一处双饼 testid 或 class
        self.assertTrue(
            "kc-structure-pies" in text or "kc-pie-count" in text,
            "dist 须含双饼标记",
        )
        self.assertNotIn("kc-structure-bars", text)


if __name__ == "__main__":
    unittest.main()
