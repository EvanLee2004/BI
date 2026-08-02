# -*- coding: utf-8 -*-
"""3.7.5 G3：看端三组件契约守卫（ReceiptsCard / 重点客户 / 热力 / HelpPopover）。

热力：驱动 shipped buildExpenseHeatPack，fen 输入 + data_disp 断言图例万级显示串。
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
SCRATCH = Path(
    os.environ.get(
        "GROK_SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-dfd6854ab604/implementer",
    )
)


class TestReceiptsCard375(unittest.TestCase):
    def test_year_progress_side_and_aria(self):
        vue = (FE / "components/ReceiptsCard.vue").read_text(encoding="utf-8")
        self.assertIn('aria-label="下单/回款摘要"', vue)
        self.assertIn('data-testid="rc-year-progress"', vue)
        self.assertIn("rc-metric-value", vue)
        self.assertIn("order_remain_disp", vue)
        self.assertIn("receipt_remain_disp", vue)
        self.assertIn("barMaxWidth: 28", vue)
        self.assertIn("barGap: '12%'", vue)
        self.assertNotRegex(vue, r"orders\s*\+\s*receipts|parseFloat\(.*disp")

    def test_backend_remain_fields(self):
        src = (ROOT / "src/viewmodels/__init__.py").read_text(encoding="utf-8")
        self.assertIn("remain_disp", src)
        self.assertIn("remain_hint", src)


class TestKeyCustomersSummary375(unittest.TestCase):
    def test_three_cards_no_silent_summary(self):
        vue = (FE / "components/key-customers/KeyCustomersSummary.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-testid="kc-card-total"', vue)
        self.assertIn('data-testid="kc-card-contrib"', vue)
        self.assertIn('data-testid="kc-card-near"', vue)
        self.assertNotIn('data-testid="kc-card-silent"', vue)
        self.assertIn("kc-summary-cards--triple", vue)
        panel = (FE / "components/key-customers/KeyCustomersPanel.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("KeyCustomersInsight", panel)
        self.assertIn("HelpPopover", panel)


class TestHelpPopover375(unittest.TestCase):
    def test_hover_pin_esc_place(self):
        vue = (FE / "components/base/HelpPopover.vue").read_text(encoding="utf-8")
        self.assertIn("placePanel", vue)
        self.assertIn("Teleport", vue)
        self.assertIn("Escape", vue)
        self.assertIn("onHoverIn", vue)
        self.assertIn("togglePin", vue)
        self.assertIn("DataModal", vue)
        self.assertIn("isNarrow", vue)


class TestExpenseHeat375(unittest.TestCase):
    def test_pack_structure_strings(self):
        util = (FE / "utils/expense-heat.ts").read_text(encoding="utf-8")
        self.assertIn("missingMap", util)
        self.assertIn("vmin_disp", util)
        self.assertIn("vmax_disp", util)
        self.assertIn("legend_range", util)
        self.assertIn("unit:", util)
        vue = (FE / "components/ExpenseHeatmap.vue").read_text(encoding="utf-8")
        self.assertIn("expense-heatmap-legend", vue)
        self.assertIn("vmin_disp", vue)
        self.assertIn("withWanUnit", vue)
        self.assertIn("暂无数据", vue)
        self.assertIn("确认 0", vue)
        # 图例不得直接插值 p.vmin / p.vmax 数值（分）
        self.assertNotIn("最小 ${p.vmin}", vue)
        self.assertNotIn("最大 ${p.vmax}", vue)

    def test_buildExpenseHeatPack_legend_uses_data_disp_not_fen(self):
        """驱动 shipped buildExpenseHeatPack：fen 大数 + data_disp 万级 → 图例 disp 是万串。

        例：123456789 分 → data_disp "123.5"；图例 vmax_disp 须为 123.5，禁止 123456789。
        """
        SCRATCH.mkdir(parents=True, exist_ok=True)
        util = FE / "utils" / "expense-heat.ts"
        # 模拟后端：data=分，data_disp=fmt_wan(分)
        series = [
            {
                "name": "管理费用",
                "data": [0, 123456789, 50000000],
                "data_disp": ["0.0", "123.5", "50.0"],
            },
            {
                "name": "营销费用",
                "data": [1000000, None, 25000000],
                "data_disp": ["1.0", "", "25.0"],
            },
        ]
        labels = ["1月", "2月", "3月"]
        payload = json.dumps({"labels": labels, "series": series}, ensure_ascii=False)
        script = f"""
import {{ buildExpenseHeatPack }} from 'file://{util.as_posix()}';
const p = {payload};
const pack = buildExpenseHeatPack(p.labels, p.series);
console.log(JSON.stringify({{
  vmax: pack.vmax,
  vmin: pack.vmin,
  vmid: pack.vmid,
  vmax_disp: pack.vmax_disp,
  vmin_disp: pack.vmin_disp,
  vmid_disp: pack.vmid_disp,
  unit: pack.unit,
  legend_range: pack.legend_range,
  missing_23: pack.missingMap['1,1'],
  disp_max: pack.dispMap['1,0'],
}}));
"""
        data = None
        last_err = ""
        for cmd in (
            [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsx"), "-e", script],
            ["npx", "--yes", "tsx", "-e", script],
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
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                last_err = str(e)
                continue
            if r.returncode != 0:
                last_err = (r.stderr or r.stdout or "")[:500]
                continue
            for ln in reversed(r.stdout.splitlines()):
                ln = ln.strip()
                if ln.startswith("{"):
                    data = json.loads(ln)
                    break
            if data is not None:
                break
        logp = SCRATCH / "heat_pack_fen_disp.log"
        logp.write_text(
            json.dumps({"data": data, "err": last_err}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.assertIsNotNone(data, f"tsx 未能跑 buildExpenseHeatPack: {last_err}")
        assert data is not None
        # 着色尺仍是分（与 data 同尺）
        self.assertEqual(data["vmax"], 123456789)
        # 图例显示串必须是万级，禁止把分原样当「万」
        self.assertEqual(data["vmax_disp"], "123.5")
        self.assertNotEqual(str(data["vmax_disp"]), str(data["vmax"]))
        self.assertNotIn("123456789", data["legend_range"])
        self.assertIn("123.5", data["legend_range"])
        self.assertEqual(data["unit"], "万")
        # 缺失格（营销 2 月：无 num 无 disp）
        self.assertTrue(data.get("missing_23") is True or data.get("missing_23") is True)
        self.assertEqual(data["disp_max"], "123.5")


if __name__ == "__main__":
    unittest.main()
