# -*- coding: utf-8 -*-
"""3.5.0 重点客户：共同金额尺度 / 月状态 / 类型单源 / 架构守卫。

驱动真实 domain compute + packer +（若存在）chart 纯函数契约；禁止 re-implement 金额公式。
"""
from __future__ import annotations

import datetime
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


def _fen_wan(wan: float) -> int:
    return int(round(float(wan) * 10_000 * 100))


COLS = {"order_amount": "下单预估额", "order_date": "下单日期"}


def _row(name: str, fen: int, month: int, year: int = 2026, sales: str = "甲") -> dict:
    return {
        "客户": name,
        "销售": sales,
        "下单预估额": fen,
        "下单日期": f"{year}-{month:02d}-15",
    }


def _peak_month_row(rows: list[dict]) -> dict:
    """取金额模式峰值点（优先 value_wan；禁止用自峰值 wo 当金额）。"""
    best = None
    best_v = -1.0
    for r in rows:
        vw = r.get("value_wan")
        if vw is None:
            continue
        if float(vw) > best_v:
            best_v = float(vw)
            best = r
    if best is not None:
        return best
    # 旧契约回退：会让语义测红
    return max(rows, key=lambda r: float(r.get("wo") or 0))


class TestAmountSharedScale(unittest.TestCase):
    """2万 vs 200万：金额 plot 共同单位约 1:100，不得同为峰值 100。"""

    def test_two_vs_two_hundred_wan_not_both_100(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        today = datetime.date(2026, 7, 15)
        rows = [
            _row("小2万", _fen_wan(2), 7),
            _row("大200万", _fen_wan(200), 7),
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=today)
        vm = pack_key_customers(raw, embed_full=True, today=today)
        monthly = vm.get("monthly") or {}
        self.assertTrue(monthly, "须有 monthly")

        peaks = {}
        for k, mrows in monthly.items():
            p = _peak_month_row(mrows)
            peaks[k] = p
            # 新契约：必须有 value_wan
            self.assertIn("value_wan", p)
            self.assertIsNotNone(p.get("value_wan"), k)

        small = next(p for k, p in peaks.items() if "小2万" in k)
        big = next(p for k, p in peaks.items() if "大200万" in k)
        s_wan = float(small["value_wan"])
        b_wan = float(big["value_wan"])
        self.assertAlmostEqual(s_wan, 2.0, places=3)
        self.assertAlmostEqual(b_wan, 200.0, places=3)
        ratio = s_wan / b_wan
        self.assertAlmostEqual(ratio, 0.01, places=4)
        # 旧 bug：双方 wo 峰值都是 100
        if small.get("wo") is not None and big.get("wo") is not None:
            # 节奏指数可同为 100；金额不得用它当 plot
            pass
        self.assertNotEqual(s_wan, b_wan)

        axis = vm.get("amount_axis") or {}
        self.assertEqual(axis.get("unit"), "万")
        name = str(axis.get("name") or "")
        self.assertIn("月下单金额", name)
        self.assertIn("万", name)
        self.assertGreaterEqual(float(axis.get("max") or 0), 200.0 * 0.9)

        chart = vm.get("chart") or {}
        self.assertEqual(chart.get("default_mode"), "amount")
        yname = str(chart.get("y_axis_name_amount") or axis.get("name") or "")
        self.assertIn("月下单金额", yname)


class TestMonthStatusSemantics(unittest.TestCase):
    def test_future_missing_not_zero_actual(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        today = datetime.date(2026, 7, 15)
        rows = [_row("仅7月", _fen_wan(10), 7)]
        raw = compute_key_customers(rows, 2026, COLS, today=today)
        vm = pack_key_customers(raw, embed_full=True, today=today)
        mkey = next(iter(vm["monthly"]))
        by_i = {int(r["i"]): r for r in vm["monthly"][mkey]}
        # 8–12 未来：missing + null
        for mi in range(8, 13):
            r = by_i[mi]
            self.assertEqual(r.get("status"), "missing", mi)
            self.assertIsNone(r.get("value_fen"), mi)
            self.assertIsNone(r.get("value_wan"), mi)
        # 7 月未完结
        self.assertEqual(by_i[7].get("status"), "incomplete")
        self.assertIsNotNone(by_i[7].get("value_fen"))
        # 1–6 已过：actual，无单则为 0 不是 missing
        for mi in range(1, 7):
            r = by_i[mi]
            self.assertEqual(r.get("status"), "actual", mi)
            self.assertEqual(int(r.get("value_fen") or 0), 0, mi)


class TestRhythmDisclaimer(unittest.TestCase):
    def test_rhythm_not_default_and_disclaimer(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        today = datetime.date(2026, 7, 15)
        raw = compute_key_customers([_row("A", _fen_wan(10), 5)], 2026, COLS, today=today)
        vm = pack_key_customers(raw, embed_full=True, today=today)
        chart = vm.get("chart") or {}
        self.assertEqual(chart.get("default_mode"), "amount")
        disc = str(chart.get("rhythm_disclaimer") or "")
        self.assertIn("峰值=100", disc)
        self.assertIn("节奏", disc)
        self.assertIn("不比较金额", disc)


class TestPackerSingleSource(unittest.TestCase):
    def test_no_dual_implementation_in_packers(self):
        text = (ROOT / "src" / "viewmodels" / "packers.py").read_text(encoding="utf-8")
        self.assertNotIn("def _kc_pack_item", text)
        self.assertNotIn("mx_m = max((float(v) for v in months)", text)
        self.assertIn("from viewmodels.key_customers import", text)
        self.assertTrue((ROOT / "src" / "viewmodels" / "key_customers.py").is_file())


class TestFrontendTypeAndKeyGuards(unittest.TestCase):
    def test_no_vm_suite_in_panel(self):
        # 实现文件：key-customers/ 下；根入口可为 re-export shell
        impl = FE / "components" / "key-customers" / "KeyCustomersPanel.vue"
        shell = FE / "components" / "KeyCustomersPanel.vue"
        self.assertTrue(impl.is_file() or shell.is_file(), "KeyCustomersPanel 必须存在")
        paths = [p for p in (impl, shell) if p.is_file()]
        # 合并源（含子组件）查重类型定义
        texts = []
        for p in paths:
            texts.append(p.read_text(encoding="utf-8"))
        kc_dir = FE / "components" / "key-customers"
        if kc_dir.is_dir():
            for p in kc_dir.glob("*.vue"):
                texts.append(p.read_text(encoding="utf-8"))
        joined = "\n".join(texts)
        self.assertNotRegex(joined, r"export type KeyCustomersVM\b")
        self.assertNotRegex(joined, r"export type KcItem\b")
        # 实现路径须引用权威类型（composable / 子组件）
        use = FE / "composables" / "useKeyCustomers.ts"
        self.assertTrue(use.is_file())
        ut = use.read_text(encoding="utf-8")
        self.assertIn("types/vm", ut)

    def test_row_key_not_index_only(self):
        files = list((FE / "components").rglob("*KeyCustomer*.vue"))
        files += list((FE / "components" / "key-customers").rglob("*.vue")) if (
            FE / "components" / "key-customers"
        ).exists() else []
        hits = []
        for p in files:
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if "v-for" in line and ("filteredPoolItems" in line or "poolItems" in line):
                    # 下一行或同行 :key
                    window = "\n".join(text.splitlines()[i - 1 : i + 3])
                    if re.search(r":key=\"['\"]row['\"]\s*\+\s*idx", window):
                        hits.append(f"{p.name}:{i}")
                    if re.search(r":key=\"idx\"", window):
                        hits.append(f"{p.name}:{i}")
        self.assertEqual(hits, [], f"可重排客户行禁止 index key: {hits}")

    def test_chart_uses_value_wan_not_wo_for_amount(self):
        chart_paths = [
            FE / "charts" / "keyCustomersChart.ts",
            FE / "components" / "KeyCustomersPanel.vue",
            FE / "components" / "key-customers" / "KeyCustomersPanel.vue",
        ]
        texts = []
        for p in chart_paths:
            if p.is_file():
                texts.append(p.read_text(encoding="utf-8"))
        joined = "\n".join(texts)
        self.assertTrue(joined, "须有 chart 或 panel 源")
        # 金额模式须读 value_wan
        self.assertIn("value_wan", joined)
        # 不得把 yAxis max 钉死 100 作为金额默认
        if "keyCustomersChart.ts" in "".join(str(p) for p in chart_paths if p.is_file()):
            c = (FE / "charts" / "keyCustomersChart.ts").read_text(encoding="utf-8")
            self.assertIn("月下单金额", c)
            self.assertNotRegex(
                c,
                r"max:\s*100\s*,\s*\n\s*show:\s*false",
                "金额模式不得隐藏 0-100 轴",
            )


class TestSelectionSSotPure(unittest.TestCase):
    """选择/对比 SSOT：优先测 pure helper；否则源码契约。"""

    def test_selection_helper_or_source_contract(self):
        sel = FE / "composables" / "keyCustomersSelection.ts"
        use = FE / "composables" / "useKeyCustomers.ts"
        if sel.is_file():
            t = sel.read_text(encoding="utf-8")
            self.assertIn("resolveSeriesKeys", t)
            self.assertIn("selectCustomer", t)
            # 比较模式优先；点非对比客清比较
            self.assertTrue(
                "clearCompare" in t or "compareKeys" in t,
                "selection helper 须处理 compare",
            )
        elif use.is_file():
            t = use.read_text(encoding="utf-8")
            self.assertIn("compareKeys", t)
            self.assertIn("selectCustomer", t)
        else:
            self.fail("须有 useKeyCustomers.ts 或 keyCustomersSelection.ts")


class TestDataIntegrityVm(unittest.TestCase):
    def test_integrity_fields_from_summary_meta(self):
        from viewmodels import build_cockpit_vm

        summary = {
            "meta": {
                "year": 2026,
                "year_key": "2026年",
                "health": {
                    "result": "黄",
                    "warnings": [
                        "手填缺 5 个月未录（2026-01、2026-02、2026-03、2026-04、2026-05）：缺月按 0 计，请当月补填",
                        "内部译员(智云) 有 1 行归属日期晚于今天（样例 2026-10-31），已计入对应未来月、不拦截",
                    ],
                },
                "built_at": "2026-07-30 20:44:14",
            },
            "kpi": {},
            "trend": [],
            "pl": {},
            "expense": {},
            "rankings": {},
            "receipts": {},
            "key_customers": None,
        }
        # 最小 summary 可能不完整；直接测 pack 函数
        try:
            from viewmodels.integrity import pack_data_integrity
        except ImportError:
            from viewmodels.packers import pack_data_integrity  # type: ignore

        di = pack_data_integrity(summary)
        self.assertEqual(di.get("health_result"), "黄")
        self.assertGreaterEqual(int(di.get("missing_manual_count") or 0), 5)
        self.assertGreaterEqual(int(di.get("future_record_count") or 0), 1)
        self.assertTrue(di.get("as_of") or di.get("built_at") or di.get("as_of_disp"))
        notes = " ".join(str(x) for x in (di.get("notes") or di.get("warnings") or []))
        self.assertTrue("手填" in notes or di.get("missing_manual_count"))
        # 不造金额
        self.assertNotIn("amount_fabricated", di)


class TestReloadHelpers(unittest.TestCase):
    def test_reload_script_checks_pid_and_marker(self):
        script = (ROOT / "deploy" / "linux" / "reload_kanban.sh").read_text(encoding="utf-8")
        self.assertTrue("pid" in script.lower() or "PID" in script)
        self.assertRegex(script, r"git_commit|runtime_version|runtime_commit")
        self.assertIn("OLD_PID", script)
        self.assertIn("new_pid", script)
        # 不得把磁盘 VERSION 单独当成功
        self.assertIn("NOT success", script)
        self.assertIn("health=200", script)


if __name__ == "__main__":
    unittest.main()
