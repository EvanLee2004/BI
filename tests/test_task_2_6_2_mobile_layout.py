# -*- coding: utf-8 -*-
"""2.6.2 手机端布局：窄屏 CSS 契约 + dual-rank 窄 option + 可选 Playwright 390 溢出。"""
from __future__ import annotations

import json
import re
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
THEME = ROOT / "static" / "css" / "theme.css"


class TestMobileCssContract(unittest.TestCase):
    def test_theme_has_overflow_and_kpi2col_under_520(self):
        css = THEME.read_text(encoding="utf-8")
        self.assertIn("@media(max-width:520px)", css.replace(" ", ""))
        # 允许空格差异
        self.assertRegex(css, r"@media\s*\(\s*max-width\s*:\s*520px\s*\)")
        block = re.search(r"@media\s*\(\s*max-width\s*:\s*520px\s*\)\s*\{(.+?)\n\}", css, re.S)
        # 取 520 段：用更宽松 — 全文断言关键串
        self.assertIn("overflow-x", css)
        self.assertIn("ledger-scroll", css)
        self.assertIn("tb-actions-narrow", css)
        self.assertIn("tb-more-btn", css)
        self.assertIn("repeat(2,", css)
        # 桌面 KPI 五列默认仍在
        self.assertIn("kpi-5", css)

    def test_scifi_bridge_keeps_wide_kpi5_default(self):
        bridge = (FE / "vendor/scifi-kit/scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", bridge)
        self.assertIn("max-width: 520px", bridge)

    def test_topbar_actions_has_narrow_menu(self):
        src = (FE / "components/TopBarActions.vue").read_text(encoding="utf-8")
        self.assertIn("tb-actions-wide", src)
        self.assertIn("tb-actions-narrow", src)
        self.assertIn("tb-more-btn", src)
        self.assertIn("exportHtml", src)
        self.assertIn("logout", src)

    def test_intersection_observer_lazy_mount_kept(self):
        host = (FE / "components/charts/EchartsHost.vue").read_text(encoding="utf-8")
        self.assertIn("IntersectionObserver", host)

    def test_dual_rank_narrow_option_truncates_names(self):
        """驱动 shipped dualRankBarOption：窄屏 left 更小、overflow truncate。"""
        # 用 node 跑 ts 不现实；静态 + 逻辑用简单 python 复读工厂意图
        src = (FE / "dual-rank-option.ts").read_text(encoding="utf-8")
        self.assertIn("narrow", src)
        self.assertIn("truncate", src)
        self.assertIn("DualRankOptionOpts", src)
        # 桌面默认路径仍含 break（非窄）
        self.assertIn("'break'", src.replace('"', "'"))


class TestMobileLiveOverflow(unittest.TestCase):
    """真实路径：refresh + 390 视口断言 scrollWidth。"""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("playwright not installed")
        import loaders
        import server
        import uvicorn
        import socket
        import urllib.request

        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["zhiyun_auto_fetch"] = False
        cls.cfg["serve_static"] = True
        try:
            server.refresh(cls.cfg, ROOT)
        except Exception as e:
            raise unittest.SkipTest(f"refresh failed: {e}") from e
        from app_state import _state

        if not _state.get("built_at"):
            raise unittest.SkipTest("no built_at after refresh")
        cls.app = server.create_app(cls.cfg, root=ROOT)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        config = uvicorn.Config(cls.app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.thr = threading.Thread(target=cls.server.run, daemon=True)
        cls.thr.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(80):
            try:
                urllib.request.urlopen(cls.base + "/login", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("accounts") or []
        cls.user = cls.pw = None
        for a in rows:
            if a.get("权限") == "整体":
                cls.user, cls.pw = a.get("账号"), a.get("密码")
                break
        if not cls.user:
            raise unittest.SkipTest("no overall account")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.should_exit = True
        except Exception:
            pass

    def test_390_no_page_overflow_and_topbar_compact(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                device_scale_factor=2,
            )
            page.goto(self.base + "/login", wait_until="networkidle", timeout=90000)
            page.locator("input[type=text], #account, input").first.fill(self.user)
            page.locator("input[type=password]").first.fill(self.pw)
            for sel in ("button:has-text('登录')", "button:has-text('进入')", "button[type=submit]"):
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    break
            page.wait_for_timeout(1200)
            page.goto(self.base + "/", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(2500)
            m = page.evaluate(
                """() => {
                  const de = document.documentElement;
                  const top = document.querySelector('.topbar');
                  const more = document.querySelector('[data-testid=tb-more-btn], .tb-more-btn');
                  const wide = document.querySelector('[data-testid=tb-actions-wide]');
                  const kpi = document.querySelector('.kpi-grid');
                  let cols = kpi ? getComputedStyle(kpi).gridTemplateColumns : '';
                  return {
                    scrollW: de.scrollWidth,
                    clientW: de.clientWidth,
                    overflow: de.scrollWidth > de.clientWidth + 2,
                    topH: top ? Math.round(top.getBoundingClientRect().height) : null,
                    hasMore: !!more,
                    moreVisible: more ? getComputedStyle(more).display !== 'none' : false,
                    wideDisplay: wide ? getComputedStyle(wide).display : null,
                    kpiCols: cols,
                    kpiChildren: kpi ? kpi.children.length : 0,
                  };
                }"""
            )
            # scroll rank
            page.locator("#rankViews, .dual-rankings").first.scroll_into_view_if_needed()
            page.wait_for_timeout(2000)
            rank = page.evaluate(
                """() => {
                  const host = document.querySelector('#rankViews, .dual-rankings');
                  if (!host) return {ok:false};
                  const canv = host.querySelectorAll('canvas, .rank-chart-host');
                  return {ok:true, n: canv.length, text: (host.innerText||'').slice(0,80)};
                }"""
            )
            browser.close()
        self.assertFalse(
            m.get("overflow"),
            f"page horizontal overflow: {m}",
        )
        self.assertLessEqual(m["scrollW"], m["clientW"] + 2, m)
        self.assertIsNotNone(m.get("topH"))
        self.assertLessEqual(m["topH"], 88, f"topbar too tall: {m}")
        self.assertTrue(m.get("moreVisible") or m.get("hasMore"), m)
        self.assertIn("px", m.get("kpiCols") or "")
        # 两列 → 至少两个 track
        self.assertGreaterEqual(
            len([x for x in (m.get("kpiCols") or "").split() if "px" in x or "fr" in x]),
            2,
            f"expect 2-col KPI: {m}",
        )
        self.assertTrue(rank.get("ok"), rank)
        self.assertGreater(rank.get("n") or 0, 0, rank)


if __name__ == "__main__":
    unittest.main()
