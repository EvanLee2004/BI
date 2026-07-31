# -*- coding: utf-8 -*-
"""3.6.1：首屏板块顺序 + 重点客户体验 + 昨天 + HELP 分级行。

驱动 shipped 纯函数（tsx）与 domain/packer；禁止仅 grep 过关。
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
PAGER_TS = FE / "composables" / "keyCustomersPager.ts"
DAILY_TS = FE / "utils" / "dailyDates.ts"
APP = FE / "App.vue"
BU = FE / "components" / "BUPage.vue"
DQ = FE / "components" / "DailyQuery.vue"
POOL = FE / "components" / "key-customers" / "KeyCustomersPool.vue"
CSS = FE / "styles" / "components" / "KeyCustomersPanel.css"
COMPUTE = ROOT / "src" / "domain" / "key_customers" / "compute.py"


def _run_tsx_import(module_path: Path, expr_js: str, named: list[str]) -> dict:
    """tsx 加载 shipped 模块，eval 表达式返回 JSON 对象。"""
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


class TestSectionOrder361(unittest.TestCase):
    EXPECTED = [
        "基本情况",
        "下单与回款",
        "重点客户下单情况追踪",
        "经营利润",
        "收入与毛利结构",
        "费用明细",
    ]

    def test_app_and_bu_six_sections(self):
        for path in (APP, BU):
            text = path.read_text(encoding="utf-8")
            titles = re.findall(r'class="sec-t">([^<]+)', text)
            self.assertEqual(titles, self.EXPECTED, f"{path.name}: {titles}")
            # 重点客户独占第三节（sec 标题序）；组件 import 行可能在文件前部，勿用 index 比 import
            self.assertIn("重点客户下单情况追踪", text)
            i_ord = text.index('sec-t">下单与回款')
            i_kc = text.index('sec-t">重点客户下单情况追踪')
            i_pl = text.index('sec-t">经营利润')
            self.assertLess(i_ord, i_kc)
            self.assertLess(i_kc, i_pl)
            # 模板里 KC 标签落在「三」与「四」之间
            tmpl = text.split("<template>")[-1] if "<template>" in text else text
            self.assertRegex(
                tmpl,
                r"重点客户下单情况追踪[\s\S]*?KeyCustomersPanel[\s\S]*?经营利润",
            )


class TestHelpLineTiersDomain(unittest.TestCase):
    def test_help_line_tiers_from_range_disp(self):
        from domain.key_customers.compute import (
            HELP_LINE_TIERS,
            HELP_LINES,
            PANEL_TITLE,
            TIER_ORDER,
            TIER_RANGE_DISP,
        )

        self.assertEqual(PANEL_TITLE, "重点客户下单情况追踪")
        self.assertIn(HELP_LINE_TIERS, HELP_LINES)
        self.assertTrue(HELP_LINE_TIERS.startswith("分级（自然年下单预估本币）："))
        # 与 TIER_RANGE_DISP 一致：阈值只改 domain
        for tid in TIER_ORDER:
            body = TIER_RANGE_DISP[tid].removesuffix("万")
            self.assertIn(f"{tid}{body}", HELP_LINE_TIERS)
        self.assertTrue(HELP_LINE_TIERS.endswith("万"))
        # 期望口径样例（与拍板文案一致）
        self.assertIn("S≥200", HELP_LINE_TIERS)
        self.assertIn("A[80,200)", HELP_LINE_TIERS)
        self.assertIn("E(0,3)", HELP_LINE_TIERS)

    def test_packer_emits_help_line_tiers(self):
        from domain.key_customers.compute import HELP_LINE_TIERS
        from viewmodels.key_customers import _kc_empty_shell

        shell = _kc_empty_shell()
        lines = shell.get("help_lines") or []
        self.assertIn(HELP_LINE_TIERS, lines)
        self.assertEqual(shell.get("panel_title"), "重点客户下单情况追踪")

    def test_vue_no_hardcoded_tier_wan_thresholds(self):
        """Vue 源禁止硬编码 200万/80万 等业务阈值。"""
        hits = []
        for p in (FE / "components" / "key-customers").rglob("*.vue"):
            text = p.read_text(encoding="utf-8")
            for pat in (r"200\s*万", r"80\s*万", r"30\s*万", r"\[80,200\)"):
                if re.search(pat, text):
                    hits.append(f"{p.name}:{pat}")
        use = FE / "composables" / "useKeyCustomers.ts"
        if use.is_file():
            t = use.read_text(encoding="utf-8")
            for pat in (r"200\s*万", r"80\s*万"):
                if re.search(pat, t):
                    hits.append(f"useKeyCustomers.ts:{pat}")
        self.assertEqual(hits, [], f"Vue 硬编码阈值: {hits}")


class TestKeyCustomersPagerShipped(unittest.TestCase):
    """驱动 keyCustomersPager.ts 真函数。"""

    def test_page_size_20_and_slice(self):
        items = list(range(45))
        out = _run_tsx_import(
            PAGER_TS,
            f"""(() => {{
              const items = {items};
              const page1 = slicePage(items, 1);
              const page2 = slicePage(items, 2);
              const page3 = slicePage(items, 3);
              return {{
                pageSize: KC_POOL_PAGE_SIZE,
                pages: pageCount(items.length),
                page1Len: page1.length,
                page2First: page2[0],
                page2Last: page2[page2.length - 1],
                page3Len: page3.length,
                idx_p1_0: rowIndex1Based(1, 0),
                idx_p2_0: rowIndex1Based(2, 0),
                idx_p2_last: rowIndex1Based(2, 19),
                empty: slicePage([], 1).length,
                clampOver: clampPage(99, items.length),
                info: pageInfoDisp(2, items.length),
                range: pageRangeDisp(2, items.length),
              }};
            }})()""",
            [
                "KC_POOL_PAGE_SIZE",
                "pageCount",
                "clampPage",
                "slicePage",
                "rowIndex1Based",
                "pageInfoDisp",
                "pageRangeDisp",
            ],
        )
        self.assertEqual(out["pageSize"], 20)
        self.assertEqual(out["pages"], 3)
        self.assertEqual(out["page1Len"], 20)
        self.assertEqual(out["page2First"], 20)
        self.assertEqual(out["page2Last"], 39)
        self.assertEqual(out["page3Len"], 5)
        self.assertEqual(out["idx_p1_0"], 1)
        self.assertEqual(out["idx_p2_0"], 21)
        self.assertEqual(out["idx_p2_last"], 40)
        self.assertEqual(out["empty"], 0)
        self.assertEqual(out["clampOver"], 3)
        self.assertIn("第 2/3 页", out["info"])
        self.assertEqual(out["range"], "21–40 / 共 45")

    def test_ui_wires_pager_and_index(self):
        pool = POOL.read_text(encoding="utf-8")
        self.assertIn("kc-pager", pool)
        self.assertIn("kc-page-prev", pool)
        self.assertIn("kc-page-next", pool)
        self.assertIn("rowDisplayIndex", pool)
        self.assertIn("kc-row-idx", pool)
        use = (FE / "composables" / "useKeyCustomers.ts").read_text(encoding="utf-8")
        self.assertIn("KC_POOL_PAGE_SIZE", use)
        self.assertIn("listPage.value = 1", use)
        self.assertIn("pagedPoolItems", use)
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".kc-row__idx", css)
        self.assertIn("var(--ink", css)


class TestYesterdayYmdShipped(unittest.TestCase):
    def test_yesterday_cross_month_and_year(self):
        out = _run_tsx_import(
            DAILY_TS,
            """(() => ({
              mid: yesterdayYmd(new Date(2026, 6, 15)),
              monthStart: yesterdayYmd(new Date(2026, 6, 1)),
              yearStart: yesterdayYmd(new Date(2026, 0, 1)),
              thisMonth: thisMonthRangeYmd(new Date(2026, 6, 15)),
            }))()""",
            ["yesterdayYmd", "thisMonthRangeYmd"],
        )
        self.assertEqual(out["mid"], "2026-07-14")
        self.assertEqual(out["monthStart"], "2026-06-30")
        self.assertEqual(out["yearStart"], "2025-12-31")
        self.assertEqual(out["thisMonth"]["start"], "2026-07-01")
        self.assertEqual(out["thisMonth"]["end"], "2026-07-15")

    def test_daily_query_yesterday_left_of_month(self):
        dq = DQ.read_text(encoding="utf-8")
        self.assertIn('data-testid="daily-yesterday"', dq)
        self.assertIn("setYesterday", dq)
        self.assertIn("yesterdayYmd", dq)
        self.assertLess(dq.find("daily-yesterday"), dq.find("daily-this-month"))
        self.assertIn("handEdit.value = true", dq)


class TestReceiptsCardPolishContract(unittest.TestCase):
    def test_keeps_null_empty_months_and_css_color(self):
        rc = (FE / "components" / "ReceiptsCard.vue").read_text(encoding="utf-8")
        self.assertIn("empty(i) ? null", rc)
        self.assertIn("cssColor", rc)
        self.assertIn("borderRadius", rc)
        self.assertIn("peakIndex", rc)
        self.assertNotIn("from 'echarts'", rc)


if __name__ == "__main__":
    unittest.main()
