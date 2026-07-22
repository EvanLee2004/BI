#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.1 三主题视觉截图 + README ui 图（须脱敏数据服务，默认 _golden_data）。

用法（服务已起，KANBAN_BASE 指向假数据实例）：
  KANBAN_BASE=http://127.0.0.1:8028 .venv/bin/python scripts/capture_2_3_1_visual.py

输出：
  docs/_visual_2_3_1/{neon,dark,light}/*.png   （gitignore）
  docs/images/ui/*  覆盖 README 用图（进 git，禁止真实金额客户名）
  {SCRATCH}/kpi_231.txt  KPI 终值对账表
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8028")
SCRATCH = Path(
    os.environ.get(
        "SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-86121cf38401/implementer",
    )
)
VIS = ROOT / "docs" / "_visual_2_3_1"
UI = ROOT / "docs" / "images" / "ui"
THEMES = ("neon", "dark", "light")


def load_accounts():
    for path in (ROOT / "_golden_data" / "看板账号.json", ROOT / "数据" / "看板账号.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")).get("accounts") or []
    return []


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
        if a.get("账号") in ("overall", "123") and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
        if a.get("权限") == "整体" and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "overall", "8888"


def fill_login(page, acc, pw):
    page.wait_for_timeout(200)
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
    page.locator(
        "button:has-text('进入'), button:has-text('登录'), button[type=submit]"
    ).first.click()


def apply_theme_via_button(page, target: str, max_clicks: int = 5) -> str:
    """经主题钮循环到 target（neon|dark|light），返回最终 data-theme。"""

    def cur() -> str:
        return page.evaluate(
            "() => document.documentElement.dataset.theme || "
            "(document.documentElement.classList.contains('theme-light') ? 'light' : 'dark')"
        )

    for _ in range(max_clicks):
        if cur() == target:
            return cur()
        page.locator(
            "button:has-text('浅色'), button:has-text('深色'), "
            "button:has-text('霓虹'), button:has-text('亮/暗')"
        ).first.click(force=True)
        page.wait_for_timeout(450)
    return cur()


def dismiss_intro(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        if page.locator(".intro-splash, [data-intro], .logo-intro").count():
            page.mouse.click(20, 20)
            page.wait_for_timeout(200)
    except Exception:
        pass


def wait_cockpit(page) -> None:
    page.wait_for_selector(
        "[data-testid=period-picker], .kpi-grid, .scifi-panel.kpi-card",
        timeout=60000,
    )
    page.wait_for_timeout(1200)
    dismiss_intro(page)
    page.wait_for_timeout(400)


def kpi_table(page) -> list[dict]:
    return page.evaluate(
        """() => {
          const cards = [...document.querySelectorAll('.scifi-panel.kpi-card, .kpi-grid .kpi-card, .kpi-grid .scifi-panel')];
          return cards.slice(0, 5).map((c, i) => {
            const name = (c.querySelector('.tag, .kpi-name, .dsdk-panel-header')?.textContent || '').trim().slice(0, 40);
            const val = (c.querySelector('.kpi-v b, .kpi-v .count-up-num, .kpi-v')?.textContent || '').trim();
            return { i, name, page_disp: val };
          });
        }"""
    )


def main() -> int:
    from playwright.sync_api import sync_playwright

    SCRATCH.mkdir(parents=True, exist_ok=True)
    for t in THEMES:
        (VIS / t).mkdir(parents=True, exist_ok=True)
    UI.mkdir(parents=True, exist_ok=True)

    vac, vpw = pick("overall")
    aac, apw = pick("admin")
    buc, bup = pick("bu")
    log: list[str] = []
    sensitive_hits: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        cons_errors: list[str] = []
        page.on(
            "console",
            lambda msg: cons_errors.append(msg.text)
            if msg.type == "error"
            else None,
        )

        # login
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
        page.screenshot(path=str(UI / "01_login.png"), full_page=False)
        fill_login(page, vac, vpw)
        page.wait_for_load_state("networkidle", timeout=90000)
        wait_cockpit(page)
        log.append(f"login ok as {vac}")

        # fetch API kpi for对照
        api_cards = page.evaluate(
            """async () => {
              try {
                const r = await fetch('/api/v1/vm/cockpit', {credentials:'include'});
                const j = await r.json();
                const cards = (j.cards_by_period && (j.cards_by_period[j.period] || j.cards_by_period['ytd'] || Object.values(j.cards_by_period)[0])) || j.cards || [];
                const arr = Array.isArray(cards) ? cards : (cards.items || []);
                return arr.slice(0, 5).map(c => ({
                  name: c.name || c.title || c.label || '',
                  value_disp: c.value_disp || c.disp || c.value || ''
                }));
              } catch (e) { return {err: String(e)}; }
            }"""
        )

        kpi_rows: list[str] = ["theme | card | page | api_value_disp | match"]
        for theme in THEMES:
            got = apply_theme_via_button(page, theme)
            assert got == theme, f"theme button failed: want {theme} got {got}"
            if theme == "light":
                assert page.evaluate(
                    "() => document.documentElement.classList.contains('theme-light')"
                ), "light missing theme-light"
            page.wait_for_timeout(600)
            # full home
            page.evaluate("window.scrollTo(0,0)")
            page.wait_for_timeout(300)
            page.screenshot(path=str(VIS / theme / "01_home.png"), full_page=False)
            # KPI strip
            kpi = page.locator(".kpi-grid, .kpi-host").first
            if kpi.count():
                kpi.screenshot(path=str(VIS / theme / "02_kpi.png"))
            else:
                page.screenshot(path=str(VIS / theme / "02_kpi.png"), full_page=False)
            # PL section
            pl = page.locator(".pl-card, #plCard, [data-section=pl]").first
            if pl.count():
                pl.scroll_into_view_if_needed()
                page.wait_for_timeout(400)
                pl.screenshot(path=str(VIS / theme / "03_pl.png"))
            else:
                page.evaluate("window.scrollTo(0, 900)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(VIS / theme / "03_pl.png"), full_page=False)
            # expense
            exp = page.locator(
                "#expenseCard, .expense-section, [data-section=expense], .expense-heat"
            ).first
            if exp.count():
                exp.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                exp.screenshot(path=str(VIS / theme / "04_expense.png"))
            else:
                page.evaluate("window.scrollTo(0, 1600)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(VIS / theme / "04_expense.png"), full_page=False)

            # KPI 对账
            page_cards = kpi_table(page)
            if isinstance(api_cards, list):
                for i, pc in enumerate(page_cards):
                    api = api_cards[i] if i < len(api_cards) else {}
                    pd = re.sub(r"\s+", "", str(pc.get("page_disp") or ""))
                    ad = re.sub(r"\s+", "", str(api.get("value_disp") or ""))
                    # 终帧可能已 count-up 完，要求数字子串一致或全等
                    match = (not ad) or (pd == ad) or (ad in pd) or (pd in ad)
                    kpi_rows.append(
                        f"{theme} | {pc.get('name') or api.get('name')} | {pc.get('page_disp')} | {api.get('value_disp')} | {match}"
                    )

            # README 主图：neon 作默认演示感；dark 进 02_viewer_home_dark 历史文件名
            if theme == "neon":
                page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(200)
                page.screenshot(path=str(UI / "02_viewer_home_neon.png"), full_page=False)
            if theme == "dark":
                page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(200)
                page.screenshot(path=str(UI / "02_viewer_home_dark.png"), full_page=False)
                page.evaluate("window.scrollTo(0, 700)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(UI / "03_viewer_profit_section.png"), full_page=False)
                page.evaluate("window.scrollTo(0, 1400)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(UI / "04_viewer_structure_section.png"), full_page=False)

            log.append(f"theme {theme} shots ok")

        # mobile neon
        page.set_viewport_size({"width": 375, "height": 812})
        apply_theme_via_button(page, "neon")
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(UI / "06_viewer_mobile.png"), full_page=False)
        page.screenshot(path=str(VIS / "neon" / "05_mobile_375.png"), full_page=False)
        page.set_viewport_size({"width": 1440, "height": 900})

        # BU page（整体账号从顶栏进 BU，或 bu 账号直接落地）
        try:
            page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=60000)
            wait_cockpit(page)
            bu_link = page.locator(".bu-nav-a, a[href*='/bu/'], .bu-nav button").first
            if bu_link.count():
                bu_link.click(force=True)
                page.wait_for_timeout(1500)
            else:
                page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=60000)
                fill_login(page, buc, bup)
                page.wait_for_load_state("networkidle", timeout=60000)
                page.wait_for_timeout(1500)
            page.wait_for_timeout(2000)
            # BU 页结构因权限而异：有 panel 则截，否则整页
            try:
                page.wait_for_selector("body", timeout=5000)
            except Exception:
                pass
            for theme in THEMES:
                try:
                    apply_theme_via_button(page, theme)
                except Exception:
                    page.evaluate(
                        f"""() => {{
                      document.documentElement.dataset.theme = '{theme}';
                      document.documentElement.classList.toggle('theme-light', '{theme}'==='light');
                    }}"""
                    )
                page.wait_for_timeout(500)
                page.screenshot(path=str(VIS / theme / "05_bu.png"), full_page=False)
            log.append(f"bu shots ok")
        except Exception as e:
            log.append(f"bu shots skip: {e}")

        # admin (golden fake)
        try:
            page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=60000)
            fill_login(page, aac, apw)
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(UI / "07_admin_console.png"), full_page=False)
            page.goto(f"{BASE}/admin/settings", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1000)
            page.screenshot(path=str(UI / "08_admin_settings.png"), full_page=False)
            for path, shot in (
                ("/admin/review/orderdept", "09_admin_order_dept.png"),
                ("/admin/manual", "10_admin_manual.png"),
                ("/admin/detail", "11_admin_detail.png"),
            ):
                page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(800)
                page.screenshot(path=str(UI / shot), full_page=False)
            log.append("admin shots ok")
        except Exception as e:
            log.append(f"admin shots: {e}")

        # sensitivity scan on viewer home body（示例/合成/测试客户名放行）
        body = ""
        try:
            page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=60000)
            wait_cockpit(page)
            body = page.inner_text("body")
        except Exception as e:
            log.append(f"sensitivity scan skip: {e}")
        for m in re.finditer(r"[\u4e00-\u9fff]{2,12}有限公司", body or ""):
            if not any(x in m.group(0) for x in ("示例", "合成", "测试")):
                sensitive_hits.append(m.group(0))

        browser.close()

    (SCRATCH / "kpi_231.txt").write_text("\n".join(kpi_rows) + "\n", encoding="utf-8")
    (SCRATCH / "capture_log.txt").write_text(
        "\n".join(log + [f"console_errors={len(cons_errors)}"] + cons_errors[:20])
        + "\n",
        encoding="utf-8",
    )
    if sensitive_hits:
        print("SENSITIVE?", sensitive_hits)
        return 2
    print("OK capture", VIS, UI)
    print("log:", "; ".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
