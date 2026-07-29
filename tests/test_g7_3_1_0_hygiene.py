#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G7 · 3.1.0 工程卫生：无壳符号、无死 js、无 fragments 注册、状态无 HTML 碎片。"""

from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestG7Hygiene310(unittest.TestCase):
    def test_no_render_modules_or_templates(self):
        self.assertEqual(list((ROOT / "src").glob("render*.py")), [])
        self.assertFalse((ROOT / "static" / "templates" / "render").exists())

    def test_no_legacy_static_js(self):
        self.assertFalse((ROOT / "static" / "js" / "cockpit.js").exists())
        self.assertFalse((ROOT / "static" / "js" / "cockpit-bu.js").exists())
        self.assertFalse((ROOT / "static" / "js" / "assemble").exists())

    def test_live_templates_remain(self):
        self.assertTrue((ROOT / "static" / "templates" / "export" / "snapshot_shell.html").is_file())
        self.assertTrue((ROOT / "static" / "templates" / "charts").is_dir())
        self.assertTrue((ROOT / "static" / "templates" / "partials").is_dir())

    def test_api_v1_shells_gone(self):
        import api_v1

        for name in (
            "build_cockpit_views",
            "build_bu_cockpit_views",
            "cockpit_fragments",
            "client_strip_fragments",
            "fragments_client_fields_empty",
            "_CLIENT_ASSEMBLE_FIELDS",
        ):
            self.assertFalse(hasattr(api_v1, name), name)

    def test_cockpit_fragments_routes_unregistered(self):
        src = (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/v1/cockpit/fragments")', src)
        self.assertNotIn('@app.get("/api/v1/cockpit/bu/{name}/fragments")', src)

    def test_core_refresh_no_build_cockpit_views(self):
        core_src = (ROOT / "src" / "core.py").read_text(encoding="utf-8")
        ref_src = (ROOT / "src" / "refresh_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("build_cockpit_views(", core_src)
        self.assertNotIn("build_cockpit_views(", ref_src)
        # 允许注释提及已删名；禁止仍定义/调用函数
        self.assertNotIn("def assemble_export_html", ref_src)
        self.assertNotIn("assemble_export_html(", ref_src)

    def test_production_src_no_import_render(self):
        import re

        pat = re.compile(r"(?:^|\s)(?:import render\b|from render\b)")
        hits = []
        for path in (ROOT / "src").rglob("*.py"):
            if path.name.startswith("render"):
                hits.append(str(path))
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if pat.search(line) and not line.lstrip().startswith("#"):
                    hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()}")
        self.assertEqual(hits, [], "src still loads render module:\n" + "\n".join(hits[:20]))

    def test_generate_state_shape(self):
        if not (ROOT / "_golden_data").exists():
            self.skipTest("缺 _golden_data")
        import core
        import loaders

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        summary, html, _ing, bu_pages = core.generate(
            cfg, datetime.date(2026, 6, 30), trigger="g7"
        )
        self.assertEqual(html, "")
        self.assertFalse(summary.get("_fragments"))
        self.assertTrue(summary.get("_views"))
        for name, page in (bu_pages or {}).items():
            self.assertNotIn("fragments", page, name)
            self.assertTrue(page.get("views"), name)

    def test_reload_script_exists(self):
        p = ROOT / "deploy" / "linux" / "reload_kanban.sh"
        self.assertTrue(p.is_file(), "缺 deploy/linux/reload_kanban.sh")
        text = p.read_text(encoding="utf-8")
        self.assertIn("run.py", text)
        self.assertNotIn("password", text.lower().replace("passwordless", ""))


if __name__ == "__main__":
    unittest.main()
