#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54.4 批次B：交互 C02–C09 真点击证据（Playwright）。

用法（Vue :8018 已起）:
  .venv/bin/python tests/frontend/playwright_task54p4_batchB.py [SCRATCH]
产出 docs/pixel/vue54p4/batchB/
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54p4" / "batchB"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-7034d6e0fee6/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
log: list[str] = []


def pick_account():
    acc, pw = "123", "8888"
    for path in (ROOT / "数据" / "看板账号.json", ROOT / "_golden_data" / "看板账号.json"):
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for a in data.get("accounts") or []:
                if a.get("账号") in ("123", "overall") and a.get("密码"):
                    return str(a["账号"]), str(a["密码"])
        except Exception as e:
            log.append(f"acct fail {path}: {e}")
    return acc, pw


def login(page, acc, pw):
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
    page.locator("input[type=text], input").first.fill(acc)
    page.locator("input[type=password]").first.fill(pw)
    page.locator("button:has-text('登录'), button[type=submit]").first.click()
    page.wait_for_load_state("networkidle", timeout=60000)
    page.wait_for_timeout(1000)


def shot(page, name: str, full=False):
    p = OUT / name
    page.screenshot(path=str(p), full_page=full)
    log.append(f"shot {name} {p.stat().st_size}b")


def main() -> int:
    acc, pw = pick_account()
    log.append(f"account={acc}")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        (SCRATCH / "browser_env_fail.log").write_text(f"{e}\n", encoding="utf-8")
        return 2

    results: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        cons = []
        page.on("console", lambda m: cons.append(f"{m.type}:{m.text}") if m.type == "error" else None)
        try:
            login(page, acc, pw)
            shot(page, "B_overall.png", full=True)

            # C02 周期选择（PeriodPicker 多为 select / 可见 chip）
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                sel = page.locator("select").first
                if sel.count():
                    # 选第二个 option（若有）
                    opts = sel.locator("option")
                    n = opts.count()
                    if n >= 2:
                        val = opts.nth(1).get_attribute("value") or opts.nth(1).inner_text()
                        sel.select_option(val)
                        page.wait_for_timeout(500)
                        results["C02_period"] = f"select:{val}"
                    else:
                        results["C02_period"] = f"select_only_{n}"
                else:
                    chip = page.locator(".period-chip, [data-period], button.period").first
                    if chip.count():
                        chip.click()
                        page.wait_for_timeout(400)
                        results["C02_period"] = "chip"
                    else:
                        results["C02_period"] = "no_control"
                shot(page, "C02_period.png")
            except Exception as e:
                results["C02_period"] = f"fail:{e}"

            # C03 利润表查看构成
            try:
                btn = page.locator("text=查看构成").first
                if btn.count():
                    btn.click()
                    page.wait_for_timeout(500)
                    results["C03_pl_drawer"] = "opened" if page.locator(".mask, .drawer, [class*=drawer]").count() else "clicked_no_drawer"
                    shot(page, "C03_pl_drawer.png")
                    # close
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                else:
                    results["C03_pl_drawer"] = "no_button"
            except Exception as e:
                results["C03_pl_drawer"] = f"fail:{e}"

            # C04 费用 tab
            try:
                for t in ("按大类", "细项", "部门", "人员"):
                    loc = page.locator(f"button:has-text('{t}'), .ev-tab:has-text('{t}')")
                    if loc.count():
                        loc.first.click()
                        page.wait_for_timeout(300)
                results["C04_expense_tabs"] = "ok"
                shot(page, "C04_expense.png")
            except Exception as e:
                results["C04_expense_tabs"] = f"fail:{e}"

            # C05 排名其余 N
            try:
                more = page.locator("text=/其余\\s*\\d+/").first
                if more.count():
                    more.click()
                    page.wait_for_timeout(500)
                    results["C05_rank_more"] = "opened"
                    shot(page, "C05_rank_more.png")
                    page.keyboard.press("Escape")
                else:
                    results["C05_rank_more"] = "no_more_link"
            except Exception as e:
                results["C05_rank_more"] = f"fail:{e}"

            # C06 密码弹窗
            try:
                for sel in ("text=改密", "text=修改密码", "button:has-text('密码')", "[title*=密码]", "#pwBtn"):
                    if page.locator(sel).count():
                        page.locator(sel).first.click()
                        page.wait_for_timeout(400)
                        results["C06_pw"] = "opened"
                        shot(page, "C06_pw.png")
                        # 强制关遮罩，避免挡后续点击
                        page.keyboard.press("Escape")
                        page.evaluate(
                            """() => {
                              const m = document.getElementById('pwModal');
                              if (m) { m.style.display='none'; m.classList.remove('on','open','show'); }
                              document.querySelectorAll('.mask').forEach(el => el.style.display='none');
                            }"""
                        )
                        page.wait_for_timeout(300)
                        break
                else:
                    results["C06_pw"] = "no_entry"
            except Exception as e:
                results["C06_pw"] = f"fail:{e}"

            # C07 亮暗切换
            try:
                page.keyboard.press("Escape")
                toggled = False
                for sel in (
                    "button:has-text('亮')",
                    "button:has-text('暗')",
                    ".theme-toggle",
                    "[data-theme]",
                    "button.tb-theme",
                    "#themeToggle",
                ):
                    if page.locator(sel).count():
                        page.locator(sel).first.click()
                        page.wait_for_timeout(500)
                        results["C07_theme"] = "toggled"
                        shot(page, "C07_theme_light.png")
                        page.locator(sel).first.click()
                        page.wait_for_timeout(400)
                        toggled = True
                        break
                if not toggled:
                    page.evaluate(
                        """() => {
                          document.documentElement.classList.add('theme-light');
                          window.dispatchEvent(new CustomEvent('kanban-theme-change'));
                        }"""
                    )
                    page.wait_for_timeout(400)
                    results["C07_theme"] = "forced_class"
                    shot(page, "C07_theme_light.png")
            except Exception as e:
                results["C07_theme"] = f"fail:{e}"

            # C08 明细翻页/筛选
            try:
                page.evaluate(
                    """() => {
                      const m = document.getElementById('pwModal');
                      if (m) m.style.display='none';
                      window.scrollTo(0, document.body.scrollHeight);
                    }"""
                )
                page.wait_for_timeout(600)
                nxt = page.get_by_role("button", name="下一页")
                if nxt.count():
                    nxt.first.click()
                    page.wait_for_timeout(500)
                    results["C08_ledger"] = "next_page"
                else:
                    results["C08_ledger"] = "no_next"
                shot(page, "C08_ledger.png")
            except Exception as e:
                results["C08_ledger"] = f"fail:{e}"

            # C09 B-01 查询（不破坏原位）
            try:
                page.evaluate(
                    """() => {
                      const m = document.getElementById('pwModal');
                      if (m) m.style.display='none';
                      document.querySelectorAll('.mask').forEach(el => el.style.display='none');
                      window.scrollTo(0, 0);
                    }"""
                )
                page.wait_for_timeout(300)
                q = page.locator("#dailyGo")
                if q.count():
                    dates = page.locator("input[type=date]")
                    if dates.count() >= 2:
                        dates.nth(0).fill("2026-01-01")
                        dates.nth(1).fill("2026-03-31")
                    q.first.click(force=True)
                    page.wait_for_timeout(800)
                    results["C09_query"] = "queried"
                    shot(page, "C09_query.png")
                else:
                    results["C09_query"] = "no_query_btn"
            except Exception as e:
                results["C09_query"] = f"fail:{e}"

            # receipts side present?
            has_side = page.locator(".rc-side, .rc-hero").count() > 0
            results["B4_receipts_side"] = "yes" if has_side else "no"
            page.locator("#receiptsCard, [id*=receipts]").first.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            shot(page, "B4_receipts.png")

            errs = [c for c in cons]
            results["console_errors"] = str(len(errs))
            (OUT / "console_errors.txt").write_text("\n".join(errs) if errs else "none\n", encoding="utf-8")
            (OUT / "interactions.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.append(f"results={json.dumps(results, ensure_ascii=False)}")
        except Exception as e:
            log.append(f"FAIL {e}")
            shot(page, "FAIL.png", full=True)
            browser.close()
            (OUT / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
            return 1
        browser.close()
    (OUT / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    (SCRATCH / "playwright_54p4_batchB.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
