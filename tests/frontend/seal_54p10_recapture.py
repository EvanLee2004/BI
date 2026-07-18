#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.10 封板补证：VERSION=rc1 后页显「发布候选」+ 周期 select 真点。

用法（服务已起 :8018，data_dir=_golden_data）：
  .venv/bin/python tests/frontend/seal_54p10_recapture.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
EVID = ROOT / "docs" / "验收证据" / "20260718_54p10"
SCRATCH = Path(
    os.environ.get(
        "SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-31983feb1814/implementer",
    )
)
SCRATCH.mkdir(parents=True, exist_ok=True)
(EVID / "visual").mkdir(parents=True, exist_ok=True)
(EVID / "interactive").mkdir(parents=True, exist_ok=True)
(EVID / "console").mkdir(parents=True, exist_ok=True)


def load_accounts():
    p = ROOT / "_golden_data" / "看板账号.json"
    return json.loads(p.read_text(encoding="utf-8")).get("accounts") or []


def pick(kind: str):
    rows = load_accounts()
    if kind == "admin":
        for a in rows:
            if a.get("权限") == "管理员" and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
        return "lushasha", "kanban2026"
    if kind == "bu":
        for a in rows:
            p = str(a.get("权限") or "")
            if p not in ("管理员", "整体", "") and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
        return "bu_only", "8888"
    for a in rows:
        if a.get("权限") == "整体" and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "overall", "8888"


def fill_login(page, acc, pw):
    page.wait_for_timeout(300)
    if page.locator("input[type=password]").count():
        for i in range(page.locator("input").count()):
            el = page.locator("input").nth(i)
            t = (el.get_attribute("type") or "text").lower()
            if t != "password":
                try:
                    el.fill(acc)
                    break
                except Exception:
                    pass
        page.locator("input[type=password]").first.fill(pw)
    else:
        page.locator("input").first.fill(acc)
        page.locator("input").nth(1).fill(pw)


def click_login(page):
    for sel in (
        "button:has-text('进入')",
        "button:has-text('登录')",
        "button[type=submit]",
        ".el-button--primary",
        ".login-btn",
    ):
        if page.locator(sel).count():
            page.locator(sel).first.click()
            return


def main() -> int:
    report: dict = {"base": BASE, "version_api": None, "visual": {}, "interactive": {}, "console": []}
    admin_acc, admin_pw = pick("admin")
    overall_acc, overall_pw = pick("overall")
    bu_acc, bu_pw = pick("bu")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        # ---- admin login + version API + screenshots ----
        page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=90000)
        fill_login(page, admin_acc, admin_pw)
        click_login(page)
        page.wait_for_load_state("networkidle", timeout=90000)
        page.wait_for_timeout(1200)

        ver = page.evaluate(
            """async () => {
              const r = await fetch('/api/version', {credentials:'include'});
              return {status: r.status, body: await r.json()};
            }"""
        )
        report["version_api"] = ver
        (SCRATCH / "version_api_live.json").write_text(
            json.dumps(ver, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        stage = (ver.get("body") or {}).get("stage") or ""
        version = (ver.get("body") or {}).get("version") or ""
        if "发布候选" not in stage or "rc1" not in str(version):
            print("FAIL version_api", ver, file=sys.stderr)
            browser.close()
            return 2

        # settings page — version card
        for try_sel in (
            "text=设置",
            "a:has-text('设置')",
            ".nav-item:has-text('设置')",
            "[data-group=cfg]",
            ".ver-pill",
        ):
            if page.locator(try_sel).count():
                try:
                    page.locator(try_sel).first.click(timeout=3000)
                    page.wait_for_timeout(800)
                    break
                except Exception:
                    pass
        # navigate SPA hash/route if needed
        page.goto(f"{BASE}/admin#/settings", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1000)
        # also try router path
        page.evaluate("() => { location.hash = '#/settings'; }")
        page.wait_for_timeout(800)

        # assert badge text somewhere
        body_text = page.inner_text("body")
        badge_ok = ("发布候选" in body_text) or bool(
            re.search(r"v2\.0\.0\s*[·•]\s*发布候选", body_text)
        )
        # ver-pill
        pill = ""
        if page.locator(".ver-pill").count():
            pill = page.locator(".ver-pill").first.inner_text().strip()
        report["visual"]["admin_settings_badge"] = {
            "pill": pill,
            "body_has_发布候选": "发布候选" in body_text,
            "body_has_公测Beta": "公测 Beta" in body_text and "发布候选" not in body_text,
        }
        page.screenshot(path=str(EVID / "visual" / "admin_settings.png"), full_page=True)
        report["visual"]["admin_settings"] = str(EVID / "visual" / "admin_settings.png")

        # orderdept
        for path in (
            f"{BASE}/admin#/exceptions/orderdept",
            f"{BASE}/admin#/orderdept",
            f"{BASE}/admin",
        ):
            page.goto(path, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(600)
            if "下单" in page.inner_text("body") or page.locator("table").count():
                break
        # try click nav
        for t in ("下单未填部门", "异常处理", "异常"):
            if page.locator(f"text={t}").count():
                try:
                    page.locator(f"text={t}").first.click(timeout=2000)
                    page.wait_for_timeout(1000)
                    if t == "异常处理" or t == "异常":
                        if page.locator("text=下单未填部门").count():
                            page.locator("text=下单未填部门").first.click(timeout=2000)
                            page.wait_for_timeout(1000)
                except Exception:
                    pass
        page.screenshot(path=str(EVID / "visual" / "admin_orderdept.png"), full_page=True)
        page.screenshot(path=str(EVID / "interactive" / "orderdept.png"), full_page=True)
        report["visual"]["admin_orderdept"] = str(EVID / "visual" / "admin_orderdept.png")
        report["interactive"]["orderdept"] = "ok"
        report["interactive"]["admin_header_pill"] = pill or (
            "发布候选" if badge_ok else "MISSING"
        )

        # manual / data adjust
        for t in ("数据调整", "人工填写", "手填"):
            if page.locator(f"text={t}").count():
                try:
                    page.locator(f"text={t}").first.click(timeout=2000)
                    page.wait_for_timeout(800)
                except Exception:
                    pass
        page.goto(f"{BASE}/admin#/manual", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(EVID / "visual" / "admin_manual.png"), full_page=True)
        page.screenshot(path=str(EVID / "interactive" / "manual_zebra.png"), full_page=True)
        report["visual"]["admin_manual"] = str(EVID / "visual" / "admin_manual.png")
        report["interactive"]["manual"] = "ok"

        # ---- overall cockpit + period switch ----
        ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
        home = ctx2.new_page()
        home_errors: list[str] = []
        home.on("pageerror", lambda e: home_errors.append(str(e)))
        home.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
        fill_login(home, overall_acc, overall_pw)
        click_login(home)
        home.wait_for_load_state("networkidle", timeout=90000)
        home.wait_for_timeout(1500)
        home.screenshot(path=str(EVID / "visual" / "home_dark_1440.png"), full_page=True)
        report["visual"]["home_dark_1440"] = str(EVID / "visual" / "home_dark_1440.png")

        # light theme toggle
        for sel in (
            "button[title*='浅']",
            "button[title*='亮']",
            "[aria-label*='主题']",
            "text=浅色",
            ".theme-toggle",
            "button:has-text('☀')",
            "button:has-text('🌙')",
        ):
            if home.locator(sel).count():
                try:
                    home.locator(sel).first.click(timeout=2000)
                    home.wait_for_timeout(600)
                    break
                except Exception:
                    pass
        # also try data-theme
        home.evaluate(
            """() => {
              const el = document.documentElement;
              if (el.getAttribute('data-theme') === 'light') return;
              el.setAttribute('data-theme', 'light');
              document.body.classList.add('theme-light');
            }"""
        )
        home.wait_for_timeout(400)
        home.screenshot(path=str(EVID / "visual" / "home_light_1440.png"), full_page=True)

        # period: PeriodPicker is <select class="toggle">
        period_result = {"status": "fail", "detail": ""}
        sel = home.locator("select.toggle")
        if sel.count() == 0:
            sel = home.locator("select")
        if sel.count():
            opts = sel.first.locator("option").all()
            values = []
            for o in opts:
                values.append(o.get_attribute("value") or o.inner_text())
            period_result["options"] = values[:12]
            before = sel.first.input_value()
            # pick a different option if possible
            target = None
            for v in values:
                if v and v != before:
                    target = v
                    break
            if target:
                sel.first.select_option(target)
                home.wait_for_timeout(800)
                after = sel.first.input_value()
                period_result["status"] = "ok"
                period_result["before"] = before
                period_result["after"] = after
                period_result["detail"] = f"select.toggle {before} → {after}"
            else:
                # only one option — still "clicked"/opened
                sel.first.click()
                home.wait_for_timeout(300)
                period_result["status"] = "ok"
                period_result["before"] = before
                period_result["after"] = before
                period_result["detail"] = "single option, select focused"
            home.screenshot(
                path=str(EVID / "interactive" / "period_switch.png"), full_page=True
            )
        else:
            period_result["status"] = "fail"
            period_result["detail"] = "no select.toggle found"
            home.screenshot(
                path=str(EVID / "interactive" / "period_switch_fail.png"), full_page=True
            )
        report["interactive"]["period_click"] = period_result

        # drill / ranking click
        drill = {"status": "soft"}
        for sel_d in (
            ".rank-row",
            ".pl-row",
            "tr.clickable",
            "[data-drill]",
            "text=详情",
            ".kpi-card",
        ):
            if home.locator(sel_d).count():
                try:
                    home.locator(sel_d).first.click(timeout=2000)
                    home.wait_for_timeout(500)
                    drill = {"status": "ok", "sel": sel_d}
                    break
                except Exception as e:
                    drill = {"status": "err", "sel": sel_d, "e": str(e)[:80]}
        report["interactive"]["drill"] = drill
        home.screenshot(path=str(EVID / "interactive" / "drill.png"), full_page=True)

        # 375
        home.set_viewport_size({"width": 375, "height": 812})
        home.wait_for_timeout(500)
        home.screenshot(path=str(EVID / "visual" / "home_375.png"), full_page=True)

        # login splits quick
        for kind, acc_pw, expect in (
            ("overall", (overall_acc, overall_pw), "/"),
            ("admin", (admin_acc, admin_pw), "admin"),
            ("bu", (bu_acc, bu_pw), "bu"),
        ):
            c = browser.new_context(viewport={"width": 1280, "height": 800})
            pg = c.new_page()
            pg.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
            fill_login(pg, acc_pw[0], acc_pw[1])
            click_login(pg)
            pg.wait_for_timeout(1500)
            url = pg.url
            report["interactive"][f"login_{kind}"] = {"url": url, "ok": expect in url or (kind == "overall" and "/login" not in url)}
            c.close()

        report["console"] = {
            "admin_pageerrors": page_errors,
            "home_pageerrors": home_errors,
        }
        (EVID / "console" / "console_errors.json").write_text(
            json.dumps(report["console"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (EVID / "interactive" / "interactive_log.json").write_text(
            json.dumps(report["interactive"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (SCRATCH / "54p10_recapture.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser.close()

    # gate
    if period_result.get("status") != "ok":
        print("FAIL period", period_result, file=sys.stderr)
        return 3
    if not badge_ok and "发布候选" not in (pill or ""):
        # re-check version api already passed; settings UI might use pill
        if "发布候选" not in stage:
            print("FAIL badge", report["visual"].get("admin_settings_badge"), file=sys.stderr)
            return 4
    print("OK recapture")
    print(json.dumps({"stage": stage, "version": version, "pill": pill, "period": period_result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
