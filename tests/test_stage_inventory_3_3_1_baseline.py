# -*- coding: utf-8 -*-
"""3.3.1 阶段守卫：工程债卫生收口后的最小结构锁（非重实现业务）。

证明：
- VERSION == 3.3.1
- 无 render_*.py / static/templates/render 残留
- frontend_mode 恒 vue
- 分摊展示金额路径 int 分（A1 可复用 test_task_3_3_1）
- 管理端用户统计仍在（防误删 3.3.0）
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestStageInventory331Baseline(unittest.TestCase):
    def test_version_is_3_3_1(self):
        v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(v, "3.3.1", f"VERSION={v}")

    def test_no_render_module_residue(self):
        self.assertFalse((ROOT / "src" / "render.py").exists())
        for p in (ROOT / "src").glob("render_*.py"):
            self.fail(f"unexpected render residue: {p}")
        self.assertFalse((ROOT / "static" / "templates" / "render").exists())

    def test_frontend_mode_vue(self):
        import viewmodels

        self.assertEqual(viewmodels.frontend_mode({}), "vue")
        self.assertEqual(viewmodels.frontend_mode(None), "vue")

    def test_alloc_display_path_int_fen_markers(self):
        src = (ROOT / "src" / "profit" / "bu_alloc.py").read_text(encoding="utf-8")
        self.assertIn("dict[str, int]", src)
        self.assertIn("_share_by_pct", src)
        self.assertIn("mul_rates_fen", src)
        # 展示挪归属函数体不得再 round(float,2) 金额真相
        self.assertIn("3.3.1", src)

    def test_user_stats_still_shipped(self):
        """3.3.0 用户统计不得被本单误删。"""
        admin_views = ROOT / "frontend" / "src" / "admin" / "views"
        has_view = (admin_views / "UserStatsView.vue").is_file()
        router = (ROOT / "frontend" / "src" / "admin").rglob("*.ts")
        router_src = "\n".join(p.read_text(encoding="utf-8") for p in router)
        vue_src = "\n".join(
            p.read_text(encoding="utf-8") for p in (ROOT / "frontend" / "src" / "admin").rglob("*.vue")
        )
        blob = router_src + "\n" + vue_src
        self.assertTrue(
            has_view or "/admin/users" in blob or "UserStats" in blob,
            "user stats route/view missing",
        )
        # 后端访问统计表/路由仍在
        self.assertTrue((ROOT / "src" / "db" / "access_stats.py").is_file())


if __name__ == "__main__":
    unittest.main()
