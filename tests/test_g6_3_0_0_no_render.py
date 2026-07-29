#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G6 · 3.0.0：render 驾驶舱双轨物理删除。"""
from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 装载字面：顶层 import/from 或 import_module("render...")
_LOAD_RE = re.compile(
    r"(?:^|\s)(?:import render\b|from render\b)|importlib\.import_module\(\s*[\"']render"
)


class TestG6RenderPhysicallyRemoved(unittest.TestCase):
    def test_no_render_py_modules(self):
        hits = list((ROOT / "src").glob("render*.py"))
        self.assertEqual(hits, [], f"仍有 render 模块: {hits}")

    def test_no_render_templates_dir(self):
        p = ROOT / "static" / "templates" / "render"
        self.assertFalse(p.exists(), f"templates/render 仍存在: {p}")

    def test_import_render_fails(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("render")

    def test_src_tests_no_render_load(self):
        hits = []
        for base in ("src", "tests"):
            for path in (ROOT / base).rglob("*.py"):
                if path.name.startswith("render"):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                # 退役守卫 / 本闸测：允许 assertRaises(import_module)
                if "TestRenderRetired" in text or path.name == "test_g6_3_0_0_no_render.py":
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if not _LOAD_RE.search(line):
                        continue
                    s = line.lstrip()
                    if s.startswith("#"):
                        continue
                    # 否定断言 / 文档闸
                    if any(
                        k in line
                        for k in (
                            "不得",
                            "禁止",
                            "零 import",
                            "仍含",
                            "assertNot",
                            "assertFalse",
                            "re.compile",
                        )
                    ):
                        continue
                    hits.append(f"{path.relative_to(ROOT)}:{i}:{line.rstrip()}")
        self.assertEqual(hits, [], "仍有业务装载 render:\n" + "\n".join(hits[:40]))

    def test_json_views_and_export_pack_without_render(self):
        if not (ROOT / "_golden_data").exists():
            self.skipTest("缺 _golden_data")
        import api_v1
        import core
        import db
        import loaders
        from export_html import SNAPSHOT_KIND, assemble_export_pack

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        views = api_v1.build_json_views(summary, cfg)
        self.assertTrue(views.get("rankings_view") is not None)
        pack = assemble_export_pack(scope="整体", state={"summary": summary, "bu_pages": {}}, cfg=cfg)
        self.assertEqual(pack.get("kind"), SNAPSHOT_KIND)


if __name__ == "__main__":
    unittest.main()
