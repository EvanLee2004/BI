#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.7.1 live: clear cookies → login → KPI numbers → rank/structure click.

Usage:
  KANBAN_LIVE_BASE=http://127.0.0.1:8018 \\
  KANBAN_LIVE_ACCT=overall KANBAN_LIVE_PW=view2026 \\
  .venv/bin/python tests/frontend/playwright_2_7_1_live.py [OUT_DIR]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/验收证据/2_7_1/live"
BASE = (os.environ.get("KANBAN_LIVE_BASE") or "http://127.0.0.1:8018").rstrip("/")
ACCT = os.environ.get("KANBAN_LIVE_ACCT") or "overall"
PW = os.environ.get("KANBAN_LIVE_PW") or "view2026"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        (OUT / "live_env_fail.log").write_text(f"import fail: {e}\n", encoding="utf-8")
        return 2

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            (OUT / "live_env_fail.log").write_text(f"launch fail: {e}\n", encoding="utf-8")
            return 2
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        # clear all cookies first
        context.clear_cookies()
        page = context.new_page()
        try:
            page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
            page.screenshot(path=str(OUT / "01_login.png"), full_page=True)
            log.append(f"login page url={page.url}")

            # fill login
            for sel in [
                'input[name="account"]',
                'input[placeholder*="账号"]',
                'input[type="text"]',
                "#account",
            ]:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.fill(ACCT)
                    break
            for sel in [
                'input[name="password"]',
                'input[type="password"]',
                "#password",
            ]:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.fill(PW)
                    break
            for sel in [
                'button[type="submit"]',
                ".login-btn",
                'button:has-text("登录")',
                'text=登录',
            ]:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click()
                    break
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT / "02_after_login.png"), full_page=True)
            log.append(f"after login url={page.url}")
            if "/login" in page.url:
                log.append("FAIL still on login")
                (OUT / "live_notes.md").write_text(
                    "# 2.7.1 live FAIL\n\n仍在登录页\n\n" + "\n".join(log), encoding="utf-8"
                )
                return 1

            # KPI present
            body = page.content()
            has_kpi = any(
                x in body
                for x in ("kpi", "KPI", "下单", "回款", "毛利", "税前", "value_disp", "card")
            )
            # visible numbers (digits)
            text = page.inner_text("body")
            has_num = any(ch.isdigit() for ch in text)
            page.screenshot(path=str(OUT / "03_kpi.png"), full_page=True)
            log.append(f"has_kpi_hint={has_kpi} has_num={has_num}")

            # try click rank / structure
            clicked = False
            for sel in [
                'text=完整排名',
                'text=其余',
                'text=按客户',
                'text=按销售',
                ".rank-list",
                "[data-testid='rank-list']",
                "text=收入与毛利",
            ]:
                loc = page.locator(sel).first
                try:
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=3000)
                        clicked = True
                        page.wait_for_timeout(1500)
                        log.append(f"clicked {sel}")
                        break
                except Exception as e:
                    log.append(f"click skip {sel}: {e}")
            page.screenshot(path=str(OUT / "04_rank_or_structure.png"), full_page=True)
            log.append(f"clicked_rank_or_structure={clicked}")

            notes = [
                "# 2.7.1 live",
                "",
                f"- BASE: `{BASE}`",
                f"- account: `{ACCT}`",
                f"- url after login: `{page.url}`",
                f"- KPI/numbers visible: **{has_num}**",
                f"- rank/structure click attempted: **{clicked}**",
                f"- cookies after login: {context.cookies()}",
                "",
                "## log",
                "```",
                *log,
                "```",
            ]
            (OUT / "live_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
            ok = has_num and "/login" not in page.url
            return 0 if ok else 1
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
