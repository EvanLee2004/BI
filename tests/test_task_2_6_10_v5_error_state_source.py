# -*- coding: utf-8 -*-
"""2.6.10：ErrorState 源码路径守卫 — 失败时清 VM、按状态码出口。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestErrorStateSourceGuards(unittest.TestCase):
    def test_load_bu_clears_vm_on_error(self):
        src = (FE / "stores/cockpit.ts").read_text(encoding="utf-8")
        # 失败路径必须清空 vm，避免旧页挡住 ErrorState
        self.assertIn("vm.value = null", src)
        self.assertIn("noteError(e)", src)
        # 不再依赖测试专用 __no_such 短路径
        self.assertNotIn("__no_such", src)

    def test_app_error_state_and_auth_required(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("authRequired", app)
        self.assertIn("ErrorState", app)
        self.assertNotIn("error.includes('未登录')", app)
        # 无 VM 兜底
        self.assertIn("!store.vm", app)

    def test_error_primary_covers_403_and_404(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("st === 403 || st === 404", app)
        self.assertIn("回我的业务线", app)


if __name__ == "__main__":
    unittest.main()
