# -*- coding: utf-8 -*-
"""3.7.11 · BU 页时间段查询隔离（ISO-01 / 01b / 02 / 05 / 09 / 16 / 18）。

驱动 shipped buildDailyQueryUrl + 源码静态契约 + 后端鉴权：
- BU scope → /api/v1/bu_daily?bu=…
- 整体 → /api/v1/daily（无 bu）
- 纯 BU 调 daily=403；有权限 bu_daily 本 BU=200
- RankingsDual/ProfitStructure/useKeyCustomers 在 BU 下带 bu=
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

FE = ROOT / "frontend" / "src"
URL_TS = FE / "utils" / "buildDailyQueryUrl.ts"
DQ = FE / "components" / "DailyQuery.vue"
RANK = FE / "components" / "RankingsDual.vue"
PROFIT = FE / "components" / "ProfitStructure.vue"
KC = FE / "composables" / "useKeyCustomers.ts"

import accounts  # noqa: E402
import bu  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
from support import fake_bu_page, fake_main_frags, fake_views  # noqa: E402


def _run_tsx_import(module_path: Path, expr_js: str, named: list[str]) -> dict:
    """tsx 加载 shipped 模块，eval 表达式返回 JSON 对象。"""
    url = module_path.resolve().as_uri()
    names = ", ".join(named)
    script = f"""
import {{ {names} }} from '{url}';
const out = ({expr_js});
console.log(JSON.stringify(out));
"""
    env = {**os.environ, "npm_config_yes": "true"}
    candidates = [
        [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsx"), "-e", script],
        ["npx", "--yes", "tsx", "-e", script],
    ]
    last = ""
    for cmd in candidates:
        try:
            r = subprocess.run(
                cmd,
                cwd=str(ROOT / "frontend"),
                capture_output=True,
                text=True,
                timeout=90,
                env=env,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            last = str(e)
            continue
        if r.returncode != 0:
            last = (r.stderr or r.stdout or "")[:600]
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
        if not lines:
            last = f"no json in stdout: {r.stdout[:300]}"
            continue
        return json.loads(lines[-1])
    raise AssertionError(f"tsx must run shipped {module_path.name}: {last}")


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


def _write_accts(cfg, root, rows):
    accounts.save_accounts(cfg, root, rows)


class TestBuildDailyQueryUrlShipped(unittest.TestCase):
    """驱动 buildDailyQueryUrl.ts 真函数（禁止 re-implement）。"""

    def test_bu_scope_uses_bu_daily_with_bu(self):
        out = _run_tsx_import(
            URL_TS,
            """(() => {
              const u = buildDailyQueryUrl({
                scope: 'bu',
                buName: '多语营销',
                start: '2026-06-01',
                end: '2026-06-30',
                top: 2000,
              });
              return { u };
            })()""",
            ["buildDailyQueryUrl"],
        )
        u = out["u"]
        self.assertTrue(u.startswith("/api/v1/bu_daily?"), u)
        self.assertIn("bu=", u)
        self.assertIn(quote("多语营销", safe=""), u)
        self.assertIn("start=2026-06-01", u)
        self.assertIn("end=2026-06-30", u)
        self.assertIn("top=2000", u)
        self.assertNotIn("/api/v1/daily?", u)

    def test_main_scope_uses_daily_no_bu(self):
        out = _run_tsx_import(
            URL_TS,
            """(() => {
              const u = buildDailyQueryUrl({
                scope: 'main',
                buName: '',
                start: '2026-06-01',
                end: '2026-06-30',
                top: 2000,
              });
              return { u };
            })()""",
            ["buildDailyQueryUrl"],
        )
        u = out["u"]
        self.assertTrue(u.startswith("/api/v1/daily?"), u)
        self.assertNotIn("bu=", u)
        self.assertNotIn("bu_daily", u)
        self.assertIn("start=2026-06-01", u)
        self.assertIn("top=2000", u)

    def test_bu_scope_without_name_falls_back_to_daily(self):
        """scope=bu 但无 buName → 保守走 daily（避免空 bu= 400 语义不清）。"""
        out = _run_tsx_import(
            URL_TS,
            """(() => {
              const a = buildDailyQueryUrl({ scope: 'bu', buName: '', start: '2026-01-01', end: '2026-01-02' });
              const b = buildDailyQueryUrl({ scope: 'bu', buName: null, start: '2026-01-01', end: '2026-01-02' });
              return { a, b };
            })()""",
            ["buildDailyQueryUrl"],
        )
        self.assertTrue(out["a"].startswith("/api/v1/daily?"), out["a"])
        self.assertTrue(out["b"].startswith("/api/v1/daily?"), out["b"])

    def test_default_top_2000(self):
        out = _run_tsx_import(
            URL_TS,
            """(() => {
              const u = buildDailyQueryUrl({ scope: 'main', start: '2026-08-01', end: '2026-08-04' });
              return { u };
            })()""",
            ["buildDailyQueryUrl"],
        )
        self.assertIn("top=2000", out["u"])


class TestDailyQuerySourceContract(unittest.TestCase):
    """源码静态：DailyQuery 在 bu 分支用 bu_daily，禁止写死只打 daily。"""

    def test_imports_and_uses_build_daily_query_url(self):
        src = DQ.read_text(encoding="utf-8")
        self.assertIn("buildDailyQueryUrl", src)
        self.assertIn("from '../utils/buildDailyQueryUrl'", src)
        self.assertIn("buildDailyQueryUrl({", src)
        # runQuery 不得再写死 '/api/v1/daily?start='
        self.assertNotRegex(
            src,
            r"['\"]/api/v1/daily\?start=",
            "DailyQuery 禁止写死只打 /api/v1/daily",
        )
        # 注释/字符串应出现 bu_daily 与 scope 语义
        self.assertIn("bu_daily", src)
        self.assertIn("store.scope", src)
        self.assertIn("store.buName", src)
        # 昨天/本月必须走 runQuery（共用 URL 逻辑）
        self.assertIn("runQuery()", src)
        self.assertRegex(src, r"function setYesterday[\s\S]*?runQuery\(\)")
        self.assertRegex(src, r"function setThisMonth[\s\S]*?runQuery\(\)")

    def test_util_file_exports_and_contains_both_paths(self):
        util = URL_TS.read_text(encoding="utf-8")
        self.assertIn("export function buildDailyQueryUrl", util)
        self.assertIn("/api/v1/bu_daily", util)
        self.assertIn("/api/v1/daily", util)
        self.assertIn("scope === 'bu'", util)


class TestBuQRegressionIso050916(unittest.TestCase):
    """ISO-05/09/16：BU scope 下 full/profit/tier 必须带 bu=。"""

    def _assert_buq(self, path: Path, api_fragment: str):
        src = path.read_text(encoding="utf-8")
        self.assertIn("store.scope === 'bu'", src, path.name)
        self.assertIn("store.buName", src, path.name)
        self.assertIn("&bu=${encodeURIComponent(store.buName)}", src, path.name)
        self.assertIn(api_fragment, src, path.name)

    def test_rankings_dual_full_has_buq(self):
        self._assert_buq(RANK, "/api/v1/rankings/full")
        # ISO-18：daily 模式优先 full_items（修 ISO-01 后 dual 已是本 BU）
        src = RANK.read_text(encoding="utf-8")
        self.assertIn("full_items", src)
        self.assertIn("dailyOn", src)

    def test_profit_structure_has_buq(self):
        self._assert_buq(PROFIT, "/api/v1/rankings/profit")

    def test_key_customers_tier_has_buq(self):
        self._assert_buq(KC, "/api/v1/key-customers/tier")


class TestApiBuDailyAuth(unittest.TestCase):
    """后端：纯 BU 调 daily=403；有权限 bu_daily 本 BU=200；他 BU=403。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(
            self.cfg,
            self.tmp,
            [
                {"name": "BU甲", "销售": ["销售A"]},
                {"name": "BU乙", "销售": ["销售B"]},
            ],
        )
        _write_accts(
            self.cfg,
            self.tmp,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管理员甲",
                    "权限": "管理员",
                    "密码": server.DEFAULT_PW,
                },
                {
                    "账号": "overall",
                    "显示名": "整体甲",
                    "权限": "整体",
                    "密码": server.DEFAULT_VIEW_PW,
                },
                {
                    "账号": "user_a",
                    "显示名": "甲负责人",
                    "权限": "BU甲",
                    "密码": server.DEFAULT_VIEW_PW,
                },
            ],
        )
        server._state["fragments"] = fake_main_frags("USER-MAIN")
        server._state["views"] = fake_views("USER-MAIN")
        server._state["bu_pages"] = {
            "BU甲": fake_bu_page("BU甲", "PAGE-A"),
            "BU乙": fake_bu_page("BU乙", "PAGE-B"),
        }
        server._state["admin_html"] = "ready"
        server._state["has_data"] = True
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _login(self, account, pw):
        c = self._client()
        r = c.post("/login", data={"account": account, "password": pw})
        self.assertIn(r.status_code, (200, 303), r.text[:200])
        return c

    def test_pure_bu_daily_403(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        q = {"start": "2026-06-01", "end": "2026-06-30", "top": 2000}
        r = c.get("/api/v1/daily", params=q)
        self.assertEqual(r.status_code, 403, r.text[:300])

    def test_bu_daily_own_bu_200(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        q = {
            "bu": "BU甲",
            "start": "2026-06-01",
            "end": "2026-06-30",
            "top": 2000,
        }
        r = c.get("/api/v1/bu_daily", params=q)
        self.assertEqual(r.status_code, 200, r.text[:400])
        body = r.json()
        self.assertEqual(body.get("bu"), "BU甲")
        self.assertIn("dual_rankings", body)

    def test_bu_daily_other_bu_403(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        q = {
            "bu": "BU乙",
            "start": "2026-06-01",
            "end": "2026-06-30",
            "top": 2000,
        }
        r = c.get("/api/v1/bu_daily", params=q)
        self.assertEqual(r.status_code, 403, r.text[:300])

    def test_admin_bu_daily_ok_and_main_daily_ok(self):
        c = self._login("lushasha", server.DEFAULT_PW)
        q_range = {"start": "2026-06-01", "end": "2026-06-30", "top": 2000}
        r_main = c.get("/api/v1/daily", params=q_range)
        self.assertEqual(r_main.status_code, 200, r_main.text[:300])
        r_bu = c.get("/api/v1/bu_daily", params={**q_range, "bu": "BU甲"})
        self.assertEqual(r_bu.status_code, 200, r_bu.text[:300])
        self.assertEqual(r_bu.json().get("bu"), "BU甲")

    def test_overall_daily_ok(self):
        c = self._login("overall", server.DEFAULT_VIEW_PW)
        r = c.get(
            "/api/v1/daily",
            params={"start": "2026-06-01", "end": "2026-06-30", "top": 2000},
        )
        self.assertEqual(r.status_code, 200, r.text[:300])


if __name__ == "__main__":
    unittest.main(verbosity=2)
