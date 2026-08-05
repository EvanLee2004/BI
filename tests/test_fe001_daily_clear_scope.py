# -*- coding: utf-8 -*-
"""FE-001 / FE-003：区间排名跨 scope 清空 + 顶栏 session 失败收紧。

静态契约 + 结构证明 shipped 路径：
- 在线 loadMain / loadBu 成功与失败路径均 clearDaily
- TopBarActions 默认/catch 非 admin、导出失败收紧
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
STORE = FE / "stores" / "cockpit.ts"
TOPBAR = FE / "components" / "TopBarActions.vue"
DAILY = FE / "components" / "DailyQuery.vue"


def _fn_body(src: str, name: str) -> str:
    """Extract async/function body until next top-level function at same indent (2 spaces)."""
    m = re.search(
        rf"(async )?function {re.escape(name)}\b[\s\S]*?(?=\n  (async )?function |\n  return \{{)",
        src,
    )
    assert m, f"function {name} not found"
    return m.group(0)


class TestFe001DailyClearOnScopeSwitch(unittest.TestCase):
    def test_online_load_main_clears_daily_at_start_and_end(self):
        src = STORE.read_text(encoding="utf-8")
        body = _fn_body(src, "loadMain")
        # 在线路径（非 snapshot/archive）须 clearDaily
        self.assertIn("clearDaily()", body)
        # 起始清空：出现在 fetchCockpitVm 之前
        idx_clear = body.find("clearDaily()")
        idx_fetch = body.find("fetchCockpitVm")
        self.assertGreaterEqual(idx_clear, 0, "loadMain 须调用 clearDaily")
        self.assertGreater(idx_fetch, 0, "loadMain 须 fetchCockpitVm")
        self.assertLess(
            idx_clear,
            idx_fetch,
            "FE-001：clearDaily 须在 fetch 之前（scope 切换开始即清）",
        )
        # 失败路径也 clear
        catch = body[body.find("catch") :] if "catch" in body else ""
        self.assertIn(
            "clearDaily()",
            catch,
            "FE-001：loadMain 失败路径须 clearDaily，不留旧 daily",
        )

    def test_online_load_bu_clears_daily_at_start_and_end(self):
        src = STORE.read_text(encoding="utf-8")
        body = _fn_body(src, "loadBu")
        idx_clear = body.find("clearDaily()")
        idx_fetch = body.find("fetchBuVm")
        self.assertGreaterEqual(idx_clear, 0, "loadBu 须调用 clearDaily")
        self.assertGreater(idx_fetch, 0, "loadBu 须 fetchBuVm")
        self.assertLess(
            idx_clear,
            idx_fetch,
            "FE-001：loadBu clearDaily 须在 fetch 之前",
        )
        catch = body[body.find("catch") :] if "catch" in body else ""
        self.assertIn("clearDaily()", catch, "FE-001：loadBu 失败须 clearDaily")

    def test_clear_daily_resets_range(self):
        src = STORE.read_text(encoding="utf-8")
        body = _fn_body(src, "clearDaily")
        self.assertIn("dailyActive.value = false", body)
        self.assertIn("dailyDual.value = null", body)
        self.assertIn("dailyRange", body)

    def test_daily_query_discards_stale_response(self):
        src = DAILY.read_text(encoding="utf-8")
        self.assertIn("dailyQueryGen", src)
        self.assertIn("scopeAtStart", src)
        # 过期响应不写 store
        self.assertRegex(
            src,
            r"gen\s*!==\s*dailyQueryGen|dailyQueryGen\s*!==\s*gen",
        )


class TestFe003TopBarTightenOnSessionFail(unittest.TestCase):
    def test_defaults_not_admin(self):
        src = TOPBAR.read_text(encoding="utf-8")
        # 默认 isAdmin=false / canExportHtml=false（收紧）
        self.assertRegex(
            src,
            r"isAdmin\s*=\s*ref\(\s*false\s*\)",
            "FE-003：isAdmin 默认须 false，勿默认藏改密/退出",
        )
        self.assertRegex(
            src,
            r"canExportHtml\s*=\s*ref\(\s*false\s*\)",
            "FE-003：导出默认关，session 失败收紧",
        )

    def test_catch_tightens(self):
        src = TOPBAR.read_text(encoding="utf-8")
        # catch 块须 isAdmin=false 且 canExportHtml=false
        m = re.search(r"catch\s*\{([\s\S]*?)\n  \}", src)
        self.assertTrue(m, "TopBarActions onMounted catch")
        catch = m.group(1)
        self.assertIn("isAdmin.value = false", catch)
        self.assertIn("canExportHtml.value = false", catch)


if __name__ == "__main__":
    unittest.main()
