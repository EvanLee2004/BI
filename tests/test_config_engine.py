#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·4：配置引擎 ≥15 例。"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain import config_engine as ce  # noqa: E402


def _conn():
    c = sqlite3.connect(":memory:")
    ce.ensure_schema(c)
    return c


class TestConfigEngine(unittest.TestCase):
    def test_01_default_export(self):
        d = ce.default_config_from_hardcoded()
        self.assertIn("报表大类白名单", d)
        self.assertIsInstance(d["报表大类白名单"], list)

    def test_02_seed(self):
        c = _conn()
        n = ce.seed_if_empty(c)
        self.assertGreater(n, 0)
        self.assertEqual(ce.seed_if_empty(c), 0)

    def test_03_load_all(self):
        c = _conn()
        ce.seed_if_empty(c)
        d = ce.load_all(c, use_cache=False)
        self.assertTrue(d["报表大类白名单"])

    def test_04_validate_ok(self):
        self.assertEqual(ce.validate_invariants(ce.default_config_from_hardcoded()), [])

    def test_05_validate_dup(self):
        errs = ce.validate_invariants({"报表大类白名单": ["A", "A"]})
        self.assertTrue(any("重复" in e for e in errs))

    def test_06_validate_orphan_map(self):
        errs = ce.validate_invariants(
            {"报表大类白名单": ["管理费用"], "费用细类到大类映射": {"x": "不存在"}}
        )
        self.assertTrue(any("悬空" in e for e in errs))

    def test_07_save_ok(self):
        c = _conn()
        ce.seed_if_empty(c)
        ver, errs = ce.save_config(c, "手填项清单", ["a", "b"], operator="t")
        self.assertEqual(errs, [])
        self.assertGreaterEqual(ver, 1)

    def test_08_save_reject_bad(self):
        c = _conn()
        ce.seed_if_empty(c)
        ver, errs = ce.save_config(c, "报表大类白名单", ["A", "A"], operator="t")
        self.assertEqual(ver, 0)
        self.assertTrue(errs)

    def test_09_change_then_load(self):
        c = _conn()
        ce.seed_if_empty(c)
        ce.save_config(c, "手填项清单", ["X"], operator="t")
        d = ce.load_all(c, use_cache=False)
        self.assertEqual(d["手填项清单"], ["X"])

    def test_10_rollback(self):
        c = _conn()
        # 不 seed，直接两版再回滚到第一版
        v1, _ = ce.save_config(c, "手填项清单", ["v1"], operator="t")
        v2, _ = ce.save_config(c, "手填项清单", ["v2"], operator="t")
        self.assertEqual(v1, 1)
        self.assertEqual(v2, 2)
        ok = ce.rollback_key(c, "手填项清单", 1, operator="t")
        self.assertTrue(ok)
        d = ce.load_all(c, use_cache=False)
        self.assertEqual(d["手填项清单"], ["v1"])

    def test_11_cache_invalidate(self):
        c = _conn()
        ce.seed_if_empty(c)
        ce.load_all(c)
        ce.invalidate_cache()
        d = ce.load_all(c)
        self.assertIn("报表大类白名单", d)

    def test_12_keys_complete(self):
        d = ce.default_config_from_hardcoded()
        for k in ce.DEFAULT_KEYS:
            self.assertIn(k, d)

    def test_13_empty_map_ok(self):
        self.assertEqual(
            ce.validate_invariants({"报表大类白名单": ["A"], "费用细类到大类映射": {}}),
            [],
        )

    def test_14_rollback_missing(self):
        c = _conn()
        ce.seed_if_empty(c)
        self.assertFalse(ce.rollback_key(c, "手填项清单", 99))

    def test_15_version_bumps(self):
        c = _conn()
        ce.seed_if_empty(c)
        v1, _ = ce.save_config(c, "去税类别白名单", ["a"], operator="t")
        v2, _ = ce.save_config(c, "去税类别白名单", ["a", "b"], operator="t")
        self.assertEqual(v2, v1 + 1)

    def test_16_default_stable_twice(self):
        a = ce.default_config_from_hardcoded({"expense_report_categories": ["工资"]})
        b = ce.default_config_from_hardcoded({"expense_report_categories": ["工资"]})
        self.assertEqual(a, b)


class TestCaliberApiOffline54(unittest.TestCase):
    """任务书54·A：口径配置 HTTP 面下线；引擎内核仍可用。"""

    def test_admin_html_no_caliber_card(self):
        """任务书65：扫 Vue 管理端源，确认口径配置卡已下线。"""
        admin_src = ROOT / "frontend" / "src" / "admin"
        parts = []
        for pth in admin_src.rglob("*"):
            if pth.suffix in (".vue", ".ts") and pth.is_file():
                parts.append(pth.read_text(encoding="utf-8"))
        blob = "\n".join(parts)
        self.assertNotIn("setCardCaliber", blob)
        self.assertNotIn("caliberLoad", blob)
        self.assertNotIn("/api/config/caliber", blob)
        # 「口径配置」整卡名不得出现在设置页（其它文案可含「口径」）
        settings = (admin_src / "views" / "SettingsView.vue").read_text(encoding="utf-8")
        self.assertNotIn("口径配置", settings)

    def test_golden_admin_no_caliber_card(self):
        g = (ROOT / "golden" / "admin_baseline.html").read_text(encoding="utf-8")
        self.assertNotIn("setCardCaliber", g)
        self.assertNotIn("口径配置", g)

    def test_routes_register_is_noop(self):
        """config_engine_api.register 不再挂载 /api/config/caliber*。"""
        from fastapi import FastAPI
        from routes import config_engine_api

        app = FastAPI()
        # 签名与其它 routes 一致；register 为空操作
        config_engine_api.register(app, object())
        paths = {getattr(r, "path", None) for r in app.routes}
        self.assertNotIn("/api/config/caliber", paths)
        self.assertNotIn("/api/config/caliber/rollback", paths)
        src = (ROOT / "src" / "routes" / "config_engine_api.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/config/caliber")', src)
        self.assertNotIn('@app.post("/api/config/caliber")', src)


if __name__ == "__main__":
    unittest.main()
