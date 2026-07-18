#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P0 shipped 路径：shell 加载 rankings.js；fragments 含 views.rankings_view；
rank_views 由 JS 组装（非 Python 预渲染 HTML fill）。

验收：规范化后 JS 组装的排名区 == Python render_rankings 各周期拼接。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RUNNER = ROOT / "static" / "js" / "assemble" / "page_node_runner.js"
SHELL = ROOT / "static" / "shell.html"
SHELL_BU = ROOT / "static" / "shell-bu.html"


def _norm(s: str) -> str:
    return re.sub(r">\s+<", "><", s.replace("\n", ""))


def _extract_rank_block(html: str) -> str:
    """取 #rankViews 内层（排名区）。"""
    m = re.search(r'id="rankViews">(.*?)</div>\s*(?:<div id="rkCustom"|<div class="foot")', html, re.S)
    if m:
        return m.group(1)
    m = re.search(r'id="rankViews">(.*)', html, re.S)
    return m.group(1) if m else ""


class TestP0ShippedPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        import loaders
        import core
        import render
        import api_v1
        import assets

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cls.cfg = cfg
        cls.summary, cls.html, _, _ = core.generate(cfg, date(2026, 6, 30), trigger="b-p0-shipped")
        cls.logo = assets.load_logo_base64(cfg) or ""
        cls.pack = api_v1.cockpit_fragments(cls.summary, cfg, cls.logo, client=True)
        cls.render = render
        cls.api_v1 = api_v1

    def test_view_shell_deleted_vue_only(self):
        """54.4·C：看端 shell 已删；Vue dist 为唯一看端入口。"""
        self.assertFalse(SHELL.is_file(), "shell.html 应已删除")
        self.assertFalse(SHELL_BU.is_file(), "shell-bu.html 应已删除")
        dist = ROOT / "frontend" / "dist" / "index.html"
        self.assertTrue(dist.is_file(), "frontend/dist/index.html 须存在")
        t = dist.read_text(encoding="utf-8")
        self.assertIn('id="app"', t)

    def test_api_payload_has_views_not_server_rank_html(self):
        fr = self.pack["fragments"]
        views = self.pack["views"]
        self.assertIn("rankings_view", views)
        self.assertTrue(views["rankings_view"], "rankings_view 为空")
        self.assertIn("year_key", views)
        self.assertIn("period_keys", views)
        # 客户端路径：rank_views 必须空，逼 JS 组装
        self.assertEqual(fr.get("rank_views"), "")
        # 至少一个周期有 sales 显示串
        any_items = False
        for v in views["rankings_view"].values():
            if (v.get("sales") or {}).get("items"):
                any_items = True
                it = v["sales"]["items"][0]
                self.assertIn("order_disp", it)
                self.assertIn("receipt_disp", it)
        self.assertTrue(any_items)

    def test_js_assembled_rank_views_equals_python(self):
        """shipped：page.js + rankings.js + views → rank 区 == Python 各周期 render_rankings。"""
        import render

        meta = self.summary["meta"]
        yk = meta["year_key"]
        P = self.summary["periods"]
        all_keys = self.pack["views"]["period_keys"]
        # 任务书34：与 build_dashboard_fragments / page.js 一致——共享月度字典、脚本只注入一次
        store: dict = {}
        parts = [
            render._pv(
                k,
                yk,
                render.render_rankings(P[k], embed_full=True, monthly_store=store, emit_monthly_script=False),
            )
            for k in all_keys
            if k in P
        ]
        py_rank = render.monthly_data_script(store) + "".join(parts)
        # node assemble full page with client pack
        fr = dict(self.pack["fragments"])
        fr["rank_views"] = ""  # force JS path
        pack = {
            "fragments": fr,
            "views": self.pack["views"],
            "templates": {
                "dashboard_body": (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8"),
                "page_shell": (ROOT / "static/templates/render/page_shell.html").read_text(encoding="utf-8"),
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
            path = f.name
        r = subprocess.run(["node", str(RUNNER), path], capture_output=True, text=True, check=True)
        js_html = r.stdout
        js_rank = _extract_rank_block(js_html)
        self.assertTrue(js_rank.strip(), "JS 未产出 rankViews")
        self.assertEqual(
            _norm(py_rank),
            _norm(js_rank),
            f"排名区 mismatch\nPY[:200]={py_rank[:200]!r}\nJS[:200]={js_rank[:200]!r}",
        )
        # 铁证：JS 路径下 fragments.rank_views 输入为空
        self.assertEqual(fr["rank_views"], "")

    def test_page_js_no_money_ops_still(self):
        js = (ROOT / "static/js/assemble/page.js").read_text(encoding="utf-8")
        # 去掉注释再扫，避免 order_disp/ 等注释误伤
        code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        code = re.sub(r"//.*?$", "", code, flags=re.M)
        self.assertNotRegex(code, r"\bparseFloat\b|\bNumber\s*\(")
        self.assertNotRegex(code, r"\b(amount|order|receipt|money|revenue|profit|cost)\w*\s*[\+\-\*/]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
