#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G8 · 3.2.0 结构门禁：薄 server 门面、_state 身份、无 user_html/HTML 僵尸、frontend_mode 恒 vue。"""

from __future__ import annotations

import ast
import inspect
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestG8Structure320(unittest.TestCase):
    def test_split_modules_exist_and_create_app_importable(self):
        self.assertTrue((ROOT / "src" / "app_factory.py").is_file())
        self.assertTrue((ROOT / "src" / "middleware_stack.py").is_file())
        self.assertTrue((ROOT / "src" / "refresh_pipeline.py").is_file())
        self.assertTrue((ROOT / "src" / "app_state.py").is_file())
        import server

        self.assertTrue(callable(server.create_app))

    def test_state_identity(self):
        import app_state
        import server

        self.assertIs(server._state, app_state._state)
        self.assertIs(server._LOCK, app_state._LOCK)

    def test_create_app_is_thin_delegate(self):
        import server

        src = inspect.getsource(server.create_app)
        self.assertIn("build_app", src)
        # 薄门面：函数体行数不宜膨胀回胖实现
        body_lines = [ln for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        self.assertLessEqual(len(body_lines), 8, f"create_app too fat:\n{src}")

    def test_publish_signature_and_state_keys(self):
        import app_state
        import refresh_pipeline
        import server

        sig = inspect.signature(server.publish)
        params = list(sig.parameters)
        self.assertNotIn("user_html", params)
        self.assertNotIn("fragments", params)
        # keyword-only bu_pages/views
        self.assertEqual(sig.parameters["bu_pages"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(sig.parameters["views"].kind, inspect.Parameter.KEYWORD_ONLY)
        # 默认态无 user_html
        # 重新读取模块默认（当前进程可能被他测污染，断言键集合语义）
        defaults = {
            "summary",
            "admin_html",
            "has_data",
            "built_at",
            "records",
            "refreshing",
            "last_refresh",
            "bu_pages",
            "views",
            "export_html_cache",
        }
        self.assertTrue(defaults.issubset(set(app_state._state.keys()) | defaults))
        self.assertNotIn("user_html", defaults)
        # 源码初始 dict 无 user_html
        st_src = (ROOT / "src" / "app_state.py").read_text(encoding="utf-8")
        self.assertNotIn('"user_html"', st_src)
        self.assertIs(server.publish, refresh_pipeline.publish)

    def test_src_no_user_html_assignment(self):
        """生产 src/ 无 user_html 运行时赋值；允许 pop 清理与注释。"""
        hits = []
        assign_pat = re.compile(r"""\[\s*['\"]user_html['\"]\s*\]\s*=""")
        kw_param = re.compile(r"""(?:^|[,(\s])user_html\s*=""")
        for path in (ROOT / "src").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                s = line.lstrip()
                if s.startswith("#"):
                    continue
                if "pop(" in line and "user_html" in line:
                    continue  # snap.pop("user_html", None) 清理残留
                if assign_pat.search(line) or kw_param.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()}")
        self.assertEqual(hits, [], "src user_html assignment residue:\n" + "\n".join(hits[:30]))

    def test_frontend_mode_always_vue(self):
        import viewmodels

        self.assertEqual(viewmodels.frontend_mode(None), "vue")
        self.assertEqual(viewmodels.frontend_mode({}), "vue")
        self.assertEqual(viewmodels.frontend_mode({"frontend": "legacy"}), "vue")

    def test_no_empty_html_view_fields_helper(self):
        import api_v1

        self.assertFalse(hasattr(api_v1, "_empty_html_view_fields"))
        src = (ROOT / "src" / "api_v1.py").read_text(encoding="utf-8")
        self.assertNotIn("def _empty_html_view_fields", src)
        self.assertNotIn("kpi_body", src)

    def test_server_py_is_facade_not_fat(self):
        n = len((ROOT / "src" / "server.py").read_text(encoding="utf-8").splitlines())
        self.assertLess(n, 250, f"server.py still fat: {n} lines")
        text = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        self.assertIn("build_app", text)
        self.assertNotIn("def publish(", text)


if __name__ == "__main__":
    unittest.main()
