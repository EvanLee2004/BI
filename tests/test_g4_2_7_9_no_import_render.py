#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G4 · 2.7.9：生产 JSON/VM 路径零 import render；显示辅助在 viewmodels.format。

真路径：
- 静态闸：src/ 业务文件（非 render*.py）无 `import render` / `from render`
- format 辅助与迁前同构（_esc / _rank_amt / attach_monthly）
- 生产 recompute/generate/build_bu_pages 只调 build_json_*_views（非 HTML build_cockpit_views）
- 阻断 importlib 装载 render 后，build_json_views / build_cockpit_vm 仍返回 order_disp
"""
from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 业务侧禁止的字面模式（与 G4 验收 rg 一致；无词界会命中 render_widgets 等）
_RENDER_IMPORT_RE = re.compile(r"import render|from render")
FAKE = ROOT / "_golden_data"


def _business_py_files() -> list[Path]:
    src = ROOT / "src"
    out = []
    for p in src.rglob("*.py"):
        if p.name.startswith("render"):
            continue
        out.append(p)
    return sorted(out)


class TestG4NoImportRender(unittest.TestCase):
    """业务代码静态零 import render / from render。"""

    def test_business_src_zero_import_render(self):
        """与验收 `rg "import render|from render" src/ --glob '!render*.py'` 同口径（含注释/文档串）。"""
        hits: list[str] = []
        for path in _business_py_files():
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if _RENDER_IMPORT_RE.search(line):
                    rel = path.relative_to(ROOT)
                    hits.append(f"{rel}:{i}:{line.rstrip()}")
        self.assertEqual(
            hits,
            [],
            "业务 src 仍含 import render|from render（含 render_widgets 等子串命中）:\n"
            + "\n".join(hits[:40]),
        )

    def test_production_ship_uses_json_views_not_html_cockpit(self):
        """core / refresh_pipeline 生产路径只调 build_json_*，不调 build_cockpit_views。"""
        core_src = (ROOT / "src" / "core.py").read_text(encoding="utf-8")
        ref_src = (ROOT / "src" / "refresh_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("build_json_views", core_src)
        self.assertIn("build_json_bu_views", core_src)
        self.assertIn("build_json_views", ref_src)
        # 禁止生产装运仍绑 HTML cockpit views
        self.assertNotIn("build_cockpit_views(", core_src)
        self.assertNotIn("build_bu_cockpit_views(", core_src)
        self.assertNotIn("build_cockpit_views(", ref_src)
        self.assertNotIn("build_bu_cockpit_views(", ref_src)


class TestG4FormatParity(unittest.TestCase):
    """迁后 format 辅助与 charts.esc / 金额口径等价。"""

    def test_esc_rank_amt_parity(self):
        import charts
        from viewmodels.format import _esc, _rank_amt

        samples = ["", "a&b", '<x "y">', "客户甲"]
        for s in samples:
            self.assertEqual(_esc(s), charts.esc(s), s)
        self.assertEqual(_rank_amt(0), "0.0万")
        self.assertTrue(_rank_amt(12345600).endswith("万"))
        self.assertTrue(_rank_amt(-100).startswith("−"))

    def test_attach_monthly_structure(self):
        from viewmodels.format import _merge_dual_rank, attach_monthly_to_dual

        o_rk = {
            "items": [{"name": "甲", "amount": 100.0}, {"name": "乙", "amount": 50.0}],
            "full_items": [{"name": "甲", "amount": 100.0}, {"name": "乙", "amount": 50.0}],
        }
        r_rk = {
            "items": [{"name": "甲", "amount": 80.0}, {"name": "乙", "amount": 40.0}],
            "full_items": [{"name": "甲", "amount": 80.0}, {"name": "乙", "amount": 40.0}],
        }
        dual = _merge_dual_rank(o_rk, r_rk, top=10)
        store: dict = {}
        out = attach_monthly_to_dual(
            dual, {"甲": {"order": [1] * 12, "receipt": [2] * 12}}, year=2026, dim="sales", store=store
        )
        self.assertTrue(out.get("items"))
        self.assertTrue(out["items"][0].get("mkey"))
        self.assertIn(out["items"][0]["mkey"], store)
        self.assertEqual(len(store[out["items"][0]["mkey"]]), 12)
        self.assertIn("order_disp", store[out["items"][0]["mkey"]][0])


class TestG4VmPathNoRenderImport(unittest.TestCase):
    """装运 VM/JSON 入口：rankings_view 含显示字段。"""

    def test_rankings_view_for_period_display_fields(self):
        import api_v1

        period = {
            "range": ("2026-01-01", "2026-01-31"),
            "rankings": {
                "orders_by_sales": {
                    "items": [{"name": "销售A", "amount": 1000000}],
                    "full_items": [{"name": "销售A", "amount": 1000000}],
                },
                "receipts_by_sales": {
                    "items": [{"name": "销售A", "amount": 800000}],
                    "full_items": [{"name": "销售A", "amount": 800000}],
                },
                "orders_by_customer": {
                    "items": [{"name": "客户B", "amount": 500000}],
                    "full_items": [{"name": "客户B", "amount": 500000}],
                },
                "receipts_by_customer": {
                    "items": [{"name": "客户B", "amount": 400000}],
                    "full_items": [{"name": "客户B", "amount": 400000}],
                },
            },
            "rankings_monthly": {"year": 2026, "sales": {}, "customer": {}},
        }
        view = api_v1.rankings_view_for_period(period, embed_full=False)
        self.assertTrue(view.get("visible"))
        sales = view.get("sales") or {}
        self.assertFalse(sales.get("empty"))
        item = (sales.get("items") or [None])[0]
        self.assertIsNotNone(item)
        assert item is not None
        self.assertIn("order_disp", item)
        self.assertIn("receipt_disp", item)
        self.assertIn("name_esc", item)
        self.assertTrue(str(item["order_disp"]).endswith("万"))


class TestG4JsonViewsRenderBlocked(unittest.TestCase):
    """生产 JSON 路径：阻断 importlib render 后仍能装 rankings / VM。"""

    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        import loaders
        import core
        import datetime as dt

        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "_golden_data"
        cls.cfg["zhiyun_auto_fetch"] = False
        cls.cfg["period_pin"] = {"year": 2026, "month": 7}
        today = loaders.pinned_today(cls.cfg) if hasattr(loaders, "pinned_today") else dt.date(2026, 7, 15)
        import db

        conn = db.connect(cls.cfg, ROOT)
        try:
            cls.summary = core.summary_from_conn(cls.cfg, conn, today)
        finally:
            conn.close()

    def _block_render(self):
        real = importlib.import_module

        def guarded(name, *a, **k):
            base = str(name).split(".", 1)[0]
            if base == "render" or str(name).startswith("render"):
                raise ImportError(f"G4 blocked: {name}")
            return real(name, *a, **k)

        return mock.patch("importlib.import_module", side_effect=guarded)

    def test_build_json_views_with_render_blocked(self):
        import api_v1

        with self._block_render():
            views = api_v1.build_json_views(self.summary, self.cfg)
        self.assertTrue(views.get("year_key") or views.get("period_keys"))
        rk = views.get("rankings_view") or {}
        self.assertTrue(rk, "rankings_view 不得空")
        # 3.2.0：生产 views 无 HTML 僵尸字段
        for z in ("kpi_body", "pl_body", "donut_body", "trend_html", "svg_html"):
            self.assertNotIn(z, views)
        # 任取一周期有 order_disp
        sample = next(iter(rk.values()))
        sales = (sample.get("sales") or {})
        items = sales.get("items") or []
        self.assertTrue(items, "双榜 items 不得空")
        self.assertIn("order_disp", items[0])
        self.assertTrue(str(items[0]["order_disp"]).endswith("万"))

    def test_build_cockpit_vm_with_render_blocked(self):
        import viewmodels

        with self._block_render():
            vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        dump = vm.model_dump()
        ranks = dump.get("rankings") or {}
        rv = ranks.get("rankings_view") or {}
        self.assertTrue(rv, "VM rankings_view 不得空")
        sample = next(iter(rv.values()))
        items = ((sample.get("sales") or {}).get("items")) or []
        self.assertTrue(items)
        self.assertIn("order_disp", items[0])
        # KPI 结构化 cards 有数（packers，不依赖 render）
        cards = (dump.get("kpi") or {}).get("cards_by_period") or {}
        self.assertTrue(cards)

    def test_build_json_bu_views_with_render_blocked(self):
        import api_v1

        with self._block_render():
            views = api_v1.build_json_bu_views("数据", self.summary, self.cfg)
        self.assertEqual(views.get("scope"), "BU")
        self.assertEqual(views.get("bu_name"), "数据")
        rk = views.get("rankings_view") or {}
        self.assertTrue(rk)
        sample = next(iter(rk.values()))
        # BU embed_full：有其余时可能有 full_items
        sales = sample.get("sales") or {}
        self.assertIn("items", sales)


if __name__ == "__main__":
    unittest.main()
