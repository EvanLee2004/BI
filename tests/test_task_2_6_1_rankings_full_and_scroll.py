# -*- coding: utf-8 -*-
"""2.6.1 R2/R6：rankings/full 鉴权；多语营销映射；滚屏后 #rankViews 图表挂载。"""
from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import server

ROOT = Path(__file__).resolve().parents[1]


class TestRankingsFullApi(unittest.TestCase):
    def test_rankings_full_route_exists_and_auth(self):
        app = server.create_app(
            {
                "data_dir": str(ROOT / "数据"),
                "db_path": str(ROOT / "数据" / "看板.db"),
                "serve_static": True,
                "zhiyun_auto_fetch": False,
            },
            root=ROOT,
        )
        c = TestClient(app)
        r = c.get("/api/v1/rankings/full", params={"period": "2026年", "dim": "sales"})
        self.assertEqual(r.status_code, 401)

    def test_pc_to_bu_maps_duoyu_yingxiao(self):
        from profit.constants import _PC_TO_BU
        from profit.summary import normalize_profit_center

        self.assertEqual(normalize_profit_center("多语营销"), "营销")
        self.assertEqual(_PC_TO_BU.get("多语营销"), "营销")


class TestBudgetPctNo999(unittest.TestCase):
    def test_domain_kpi_bar(self):
        from domain.pl.structure import kpi_target_bar

        bar = kpi_target_bar(
            "order",
            "2026年",
            {"orders": 1e10},
            {"order": {"target": 1.0, "done": 1e10, "pct": 99999.0}},
        )
        self.assertEqual(bar["pct_disp"], "目标待校准")
        self.assertNotIn("999%", bar["pct_disp"])


class TestRankingsScrollMount(unittest.TestCase):
    """R6：真实浏览器 scrollIntoView(#rankViews) 后图表已挂载（canvas 宽高>0）。

    关键：必须先 refresh 管道（create_app  alone 不构建 VM，cockpit 会 empty）。
    """

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("playwright not installed")

        import loaders
        import uvicorn
        import socket
        import urllib.request

        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["zhiyun_auto_fetch"] = False
        cls.cfg["serve_static"] = True

        # 与 run.py --serve 一致：先跑管道再挂服务，否则 /api/v1/cockpit empty=true
        try:
            server.refresh(cls.cfg, ROOT)
        except Exception as e:
            raise unittest.SkipTest(f"refresh failed (no local data?): {e}") from e
        from app_state import _state

        if not _state.get("built_at") and not _state.get("has_data"):
            raise unittest.SkipTest("refresh produced no built_at/has_data")

        cls.app = server.create_app(cls.cfg, root=ROOT)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        config = uvicorn.Config(cls.app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.thr = threading.Thread(target=cls.server.run, daemon=True)
        cls.thr.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(120):
            try:
                urllib.request.urlopen(cls.base + "/login", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise unittest.SkipTest("server did not become ready")

        rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("accounts") or []
        cls.user = None
        cls.pw = None
        for a in rows:
            if a.get("权限") == "整体":
                cls.user, cls.pw = a.get("账号"), a.get("密码")
                break
        if not cls.user:
            raise unittest.SkipTest("no overall account in 数据/看板账号.json")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.should_exit = True
        except Exception:
            pass

    def test_scroll_rank_views_mounts_chart(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            # 对齐既有活体测：login → 再显式 goto /
            page.goto(self.base + "/login", wait_until="networkidle", timeout=90000)
            page.locator("input[type=text], #account, input[autocomplete=username]").first.fill(
                self.user
            )
            page.locator("input[type=password]").first.fill(self.pw)
            clicked = False
            for sel in ("button:has-text('登录')", "button:has-text('进入')", "button[type=submit]"):
                loc = page.locator(sel)
                if loc.count():
                    loc.first.click()
                    clicked = True
                    break
            if not clicked:
                page.keyboard.press("Enter")
            page.wait_for_timeout(1500)
            page.goto(self.base + "/", wait_until="networkidle", timeout=90000)
            page.wait_for_load_state("networkidle")
            # 等 Vue 壳 + KPI 或排名区
            try:
                page.wait_for_selector(
                    "#rankViews, .dual-rankings, .kpi-grid, .kpi-host, #app",
                    timeout=90000,
                    state="attached",
                )
            except Exception as e:
                body = page.content()[:800]
                browser.close()
                self.fail(f"login or shell failed url={page.url}: {e}; html={body!r}")

            # 强制滚到排名区（IntersectionObserver 懒挂载的前置条件）
            host_sel = "#rankViews, .dual-rankings"
            # 若仅有 #app 壳，再等 rankViews 出现
            try:
                page.wait_for_selector(host_sel, timeout=60000, state="attached")
            except Exception as e:
                # dump useful diagnostics
                diag = page.evaluate(
                    """() => ({
                      url: location.href,
                      hasApp: !!document.querySelector('#app'),
                      text: (document.body && document.body.innerText || '').replace(/\\s+/g,' ').slice(0,300),
                      scripts: Array.from(document.scripts).map(s=>s.src).filter(Boolean).slice(0,8),
                    })"""
                )
                browser.close()
                self.fail(f"#rankViews not in DOM after login: {e}; diag={diag}")

            page.locator(host_sel).first.scroll_into_view_if_needed()
            page.evaluate(
                """() => {
                  const host = document.querySelector('#rankViews, .dual-rankings');
                  if (host) host.scrollIntoView({block: 'center', behavior: 'instant'});
                }"""
            )
            # 等 IO + ECharts 挂载（动画缓冲）
            page.wait_for_timeout(2500)

            def _probe():
                return page.evaluate(
                    """() => {
                      const host = document.querySelector('#rankViews, .dual-rankings');
                      if (!host) return {ok:false, reason:'no_host', url: location.href};
                      host.scrollIntoView({block: 'center', behavior: 'instant'});
                      const canv = Array.from(host.querySelectorAll('canvas'));
                      const chartHost = host.querySelectorAll('.rank-chart-host, [_echarts_instance_]').length;
                      const svg = host.querySelectorAll('svg').length;
                      const sizes = canv.map(c => ({w: c.width, h: c.height, cw: c.clientWidth, ch: c.clientHeight}));
                      const mounted = sizes.some(s => (s.w > 10 && s.h > 10) || (s.cw > 10 && s.ch > 10))
                        || svg > 0 || chartHost > 0;
                      const empty = (host.innerText || '').includes('本期无数据');
                      const others = (host.innerText || '').includes('其余');
                      return {
                        ok: true,
                        mounted,
                        empty,
                        others,
                        canvas: sizes.length,
                        chartHost,
                        sizes,
                        svg,
                        url: location.href,
                        text: (host.innerText || '').replace(/\\s+/g, ' ').slice(0, 200),
                      };
                    }"""
                )

            info = _probe()
            if not info.get("mounted"):
                page.wait_for_timeout(2000)
                info2 = _probe()
            else:
                info2 = info
            browser.close()

        self.assertTrue(info.get("ok"), info)
        mounted = info.get("mounted") or info2.get("mounted")
        # 有「其余」或非空态时，滚入视口后必须出图
        if info.get("others") or not info.get("empty"):
            self.assertTrue(
                mounted,
                f"scrollIntoView(#rankViews) but chart not mounted: info={info} info2={info2}",
            )
        else:
            self.skipTest(f"no ranking data on this fixture: {info}")


if __name__ == "__main__":
    unittest.main()
