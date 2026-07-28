#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.7.2 live: viewer KPI + admin refresh_status / health v1.

  KANBAN_LIVE_BASE=http://127.0.0.1:8018 \\
  KANBAN_LIVE_VIEW_ACCT=123 KANBAN_LIVE_VIEW_PW=8888 \\
  KANBAN_LIVE_ADMIN_ACCT=lushasha KANBAN_LIVE_ADMIN_PW=8888 \\
  .venv/bin/python tests/frontend/playwright_2_7_2_live.py [OUT_DIR]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/验收证据/2_7_2/live"
BASE = (os.environ.get("KANBAN_LIVE_BASE") or "http://127.0.0.1:8018").rstrip("/")
VIEW_ACCT = os.environ.get("KANBAN_LIVE_VIEW_ACCT") or "123"
VIEW_PW = os.environ.get("KANBAN_LIVE_VIEW_PW") or "8888"
ADMIN_ACCT = os.environ.get("KANBAN_LIVE_ADMIN_ACCT") or "lushasha"
ADMIN_PW = os.environ.get("KANBAN_LIVE_ADMIN_PW") or "8888"


def fill_login(page, acc, pw):
    for sel in ['input[name="account"]', 'input[type="text"]', "#account"]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.fill(acc)
            break
    for sel in ['input[name="password"]', 'input[type="password"]']:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.fill(pw)
            break
    for sel in ['button[type="submit"]', ".login-btn", 'button:has-text("登录")']:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            break


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
        try:
            # --- viewer ---
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.clear_cookies()
            page = ctx.new_page()
            page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
            page.screenshot(path=str(OUT / "01_login.png"), full_page=True)
            fill_login(page, VIEW_ACCT, VIEW_PW)
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT / "02_viewer_kpi.png"), full_page=True)
            text = page.inner_text("body")
            has_num = any(ch.isdigit() for ch in text)
            log.append(f"viewer url={page.url} has_num={has_num}")
            # health v1 via page evaluate
            hr = page.evaluate(
                """async () => {
                  const r = await fetch('/api/v1/health', {credentials:'same-origin'});
                  return {status:r.status, body: await r.json().catch(()=>null)};
                }"""
            )
            log.append(f"health_v1={hr}")
            old_h = page.evaluate(
                """async () => {
                  const r = await fetch('/api/health', {credentials:'same-origin'});
                  return r.status;
                }"""
            )
            log.append(f"old_health_status={old_h}")
            ctx.close()

            # --- admin ---
            ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx2.clear_cookies()
            page2 = ctx2.new_page()
            page2.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
            fill_login(page2, ADMIN_ACCT, ADMIN_PW)
            page2.wait_for_timeout(2500)
            # go admin
            page2.goto(f"{BASE}/admin", wait_until="networkidle", timeout=90000)
            page2.wait_for_timeout(2000)
            page2.screenshot(path=str(OUT / "03_admin.png"), full_page=True)
            # refresh_status v1
            rs = page2.evaluate(
                """async () => {
                  const r = await fetch('/api/v1/admin/refresh_status', {credentials:'same-origin'});
                  const t = await r.text();
                  return {status:r.status, text:t.slice(0,200)};
                }"""
            )
            log.append(f"refresh_status_v1={rs}")
            # try click 更新 if visible (don't wait pipeline)
            for sel in ['text=更新数据', 'button:has-text("更新")', '[data-testid="refresh"]']:
                loc = page2.locator(sel).first
                try:
                    if loc.count() and loc.is_visible():
                        log.append(f"found refresh control {sel}")
                        # do not click to avoid long pipeline in live; screenshot only
                        break
                except Exception:
                    pass
            # open ledger/adjust related
            page2.goto(f"{BASE}/admin/review/ledger", wait_until="networkidle", timeout=90000)
            page2.wait_for_timeout(1500)
            page2.screenshot(path=str(OUT / "04_admin_ledger.png"), full_page=True)
            log.append(f"admin ledger url={page2.url}")
            ctx2.close()

            notes = [
                "# 2.7.2 live",
                "",
                f"- BASE: `{BASE}`",
                f"- viewer has_num: **{has_num}**",
                f"- health v1 status: **{(hr or {}).get('status')}** old /api/health: **{old_h}**",
                f"- refresh_status v1: **{(rs or {}).get('status')}**",
                "",
                "## log",
                "```",
                *log,
                "```",
            ]
            (OUT / "live_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
            ok = (
                has_num
                and (hr or {}).get("status") == 200
                and old_h == 404
                and (rs or {}).get("status") == 200
            )
            return 0 if ok else 1
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
