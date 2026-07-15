#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-BU shipped：BU client 路径（strip fragments + build_bu_cockpit_views + page.js）
经 node 组装出的 HTML ≡ Python assemble_bu_dashboard_html（规范化全等）。

覆盖：回款区、公共分摊 pl_tag、排名「其余」.rk-full / 收入 .pr-full（铁律12）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RUNNER = ROOT / "static" / "js" / "assemble" / "page_node_runner.js"

# 15 名销售 → 双血条 top10 后必有「其余」（golden 里均有交付）
_SALES = [
    "员工003",
    "员工001",
    "员工028",
    "员工015",
    "员工013",
    "员工019",
    "员工023",
    "员工010",
    "员工024",
    "员工007",
    "员工034",
    "员工030",
    "员工005",
    "员工038",
    "员工022",
]
_BU = "传统营销"


def _norm(s: str) -> str:
    return re.sub(r">\s+<", "><", s.replace("\n", ""))


class TestBuShippedAssemble(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        import loaders
        import core
        import db
        import api_v1
        import assets
        import bu

        cls.tmp = Path(tempfile.mkdtemp(prefix="bu_shipped_"))
        db_copy = cls.tmp / "golden.db"
        shutil.copy2(ROOT / "_golden_data" / "看板.db", db_copy)

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = str(db_copy.resolve())
        cfg["zhiyun_auto_fetch"] = False
        cfg["show_delivered_unpaid"] = False
        cls.cfg = cfg

        # BU 配置写到 tmp/_golden_data/（load_bu_config(cfg, root=tmp)）
        bucfg_dir = cls.tmp / "_golden_data"
        bucfg_dir.mkdir(parents=True, exist_ok=True)
        (bucfg_dir / "BU配置.json").write_text(
            json.dumps({"bus": [{"name": _BU, "销售": _SALES}]}, ensure_ascii=False),
            encoding="utf-8",
        )

        conn = db.connect(cfg)
        # 按月分摊比例 → public_allocation.enabled + pl_tag「含公共分摊」
        for m in range(1, 7):
            db.set_alloc_ratio(conn, f"2026-{m:02d}", _BU, 35.0, "b-bu-test")
        logo = assets.load_logo_base64(cfg) or ""
        pages = core.build_bu_pages(cfg, conn, date(2026, 6, 30), logo, root=cls.tmp)
        conn.close()

        if _BU not in pages:
            raise unittest.SkipTest(f"BU 页未生成: keys={list(pages)}")
        cls.page = pages[_BU]
        cls.py_html = cls.page["html"]
        fr_full = cls.page["fragments"]
        summary = cls.page["summary"]

        # client 路径：strip + BU views（与 server BU fragments 一致）
        cls.fr_client = api_v1.client_strip_fragments(fr_full)
        cls.views = api_v1.build_bu_cockpit_views(_BU, summary, cfg)

        # 前置条件：本用例依赖的业务特征必须存在
        assert cls.views.get("receipts_html"), "缺 receipts_html"
        assert cls.views.get("pl_tag"), "缺 pl_tag（应有分摊或直记标签）"
        yk = cls.views.get("year_key") or "2026年"
        rv = (cls.views.get("rankings_view") or {}).get(yk) or {}
        sales_blk = rv.get("sales") or {}
        assert sales_blk.get("embed_full") and sales_blk.get("full_items"), "排名缺 embed_full/full_items（铁律12）"

    def test_client_fragments_strip_bu_fields(self):
        import api_v1

        for f in api_v1._CLIENT_ASSEMBLE_FIELDS:
            if f in self.fr_client:
                self.assertEqual(self.fr_client.get(f), "", f"client 须 strip {f}")

    def test_views_are_bu_not_overall(self):
        self.assertEqual(self.views.get("scope"), "BU")
        self.assertIn("receipts_html", self.views)
        self.assertIn("pl_tag", self.views)
        # 整体页字段不应作为 BU 主回款通道
        self.assertNotIn("receipts_budget", self.views)
        self.assertIn("含公共分摊", self.views.get("pl_tag") or "")

    def test_node_client_assemble_equals_python_bu_html(self):
        pack = {
            "fragments": self.fr_client,
            "views": self.views,
            "templates": {
                "dashboard_body": (ROOT / "static/templates/render/bu_body.html").read_text(encoding="utf-8"),
                "page_shell": (ROOT / "static/templates/render/page_shell.html").read_text(encoding="utf-8"),
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
            path = f.name
        r = subprocess.run(["node", str(RUNNER), path], capture_output=True, text=True, check=True)
        js_html = r.stdout
        self.assertEqual(
            _norm(self.py_html),
            _norm(js_html),
            f"BU node assemble ≠ Python html; len py={len(self.py_html)} js={len(js_html)}",
        )

    def test_markers_receipts_alloc_rank_full(self):
        """组装结果须含回款、分摊标签、本地全量排名锚点。"""
        pack = {
            "fragments": self.fr_client,
            "views": self.views,
            "templates": {
                "dashboard_body": (ROOT / "static/templates/render/bu_body.html").read_text(encoding="utf-8"),
                "page_shell": (ROOT / "static/templates/render/page_shell.html").read_text(encoding="utf-8"),
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
            path = f.name
        r = subprocess.run(["node", str(RUNNER), path], capture_output=True, text=True, check=True)
        html = r.stdout
        for m in ("含公共分摊", "rk-full", "pr-full", "dual-grid", "管理利润表", "下单/回款"):
            self.assertIn(m, html, m)
        # 铁律12：不得在 BU 组装脚本路径引入全公司 API 字面（组装结果/壳侧）
        self.assertNotIn("/api/profit_ranking", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
