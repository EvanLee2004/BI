#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书58：R-50 费用明细日级 + R-51 下单与回款「本月」活体。

用法（服务已起 :8018 或 KANBAN_BASE）:
  .venv/bin/python tests/frontend/playwright_task58_dates.py [SCRATCH]

产出：docs/验收证据/20260719_58/ + scratch 日志。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "docs" / "验收证据" / "20260719_58"
EVID.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-e681ee82467c/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
(SCRATCH / "shots").mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
ACCT = os.environ.get("KANBAN_ACCT_OVERALL", "123")
PW = os.environ.get("KANBAN_PW_OVERALL", "8888")
log: list[str] = []
page_errors: list[str] = []
console_errors: list[str] = []


def pick_account() -> None:
    global ACCT, PW
    try:
        acc_path = ROOT / "数据" / "看板账号.json"
        if not acc_path.is_file():
            return
        data = json.loads(acc_path.read_text(encoding="utf-8"))
        rows = data.get("accounts") or []
        for want in (ACCT, "123", "overall", "lushasha"):
            for a in rows:
                if a.get("账号") == want and str(a.get("密码") or "").strip():
                    ACCT = want
                    PW = str(a["密码"])
                    return
    except Exception as e:
        log.append(f"account pick fail: {e}")


def set_theme(page, light: bool) -> None:
    page.evaluate(
        """(light) => {
      const r = document.documentElement;
      if (light) r.classList.add('theme-light'); else r.classList.remove('theme-light');
      try { localStorage.setItem('cockpit-theme', light ? 'light' : 'dark'); } catch(e) {}
      window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light } }));
    }""",
        light,
    )
    page.wait_for_timeout(400)


def login(page) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
    for sel in ("input[type=text]", "#account", "input"):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.fill(ACCT)
                break
        except Exception:
            pass
    for sel in ("input[type=password]", "#password"):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.fill(PW)
                break
        except Exception:
            pass
    for sel in ("button:has-text('登录')", "button[type=submit]", "button"):
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click()
                break
        except Exception:
            pass
    page.wait_for_timeout(2000)
    # 等 cockpit 或 费用明细 出现
    for _ in range(30):
        if page.locator("text=费用明细").count() or page.locator("#dailyPanel").count():
            break
        page.wait_for_timeout(500)


def parse_total(page) -> int:
    """从 SciFiPanel tag「共 N 行」解析。"""
    texts = page.locator(".scifi-panel").filter(has_text="费用明细").all_inner_texts()
    blob = "\n".join(texts)
    m = re.search(r"共\s*(\d+)\s*行", blob)
    if not m:
        # 全局搜
        blob = page.inner_text("body")
        m = re.search(r"共\s*(\d+)\s*行", blob)
    return int(m.group(1)) if m else -1


def shot(page, name: str) -> None:
    p = EVID / name
    page.screenshot(path=str(p), full_page=False)
    p2 = SCRATCH / "shots" / name
    page.screenshot(path=str(p2), full_page=False)
    log.append(f"shot {p} size={p.stat().st_size}")


def main() -> int:
    pick_account()
    log.append(f"BASE={BASE} ACCT={ACCT}")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log.append(f"import fail: {e}")
        (SCRATCH / "r50_r51_playwright.log").write_text("\n".join(log) + "\n", encoding="utf-8")
        return 2

    today = date.today()
    month_start = today.replace(day=1).isoformat()
    today_s = today.isoformat()
    year = today.year
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)[:300]))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text[:300]) if msg.type == "error" else None,
        )
        login(page)

        # --- R-50 ---
        page.locator("text=费用明细").first.scroll_into_view_if_needed()
        page.wait_for_timeout(800)
        tools = page.locator("[data-testid=ledger-date-tools]")
        assert tools.count(), "ledger-date-tools missing"
        df = page.locator("#ledgerDateFrom, [data-testid=ledger-date-from]").first
        dt = page.locator("#ledgerDateTo, [data-testid=ledger-date-to]").first
        assert df.count() and dt.count(), "date inputs missing"

        # 开 show_all 便于有真实行数做区间断言（期间费用口径可能更少但也应变化）
        sa = page.locator("[data-testid=ledger-show-all] input")
        if sa.count() and not sa.is_checked():
            sa.check()
            page.wait_for_timeout(1000)

        total_year = parse_total(page)
        log.append(f"total_default={total_year} from={df.input_value()} to={dt.input_value()}")
        assert total_year > 0, f"expected ledger rows after show_all, got {total_year}"

        # 缩到 1 月前半：行数应变小
        df.fill("2026-01-01")
        dt.fill("2026-01-15")
        page.locator("[data-testid=ledger-query]").click()
        page.wait_for_timeout(1200)
        total_jan = parse_total(page)
        log.append(f"total_jan1_15={total_jan}")
        assert total_jan >= 0, "parse total failed after query"
        assert total_jan < total_year, f"narrow range must reduce rows {total_jan} vs year {total_year}"
        assert total_jan > 0, "jan slice should have rows"

        # 本月
        page.locator("[data-testid=ledger-this-month]").click()
        page.wait_for_timeout(1200)
        assert df.input_value() == month_start, f"本月起 {df.input_value()} != {month_start}"
        assert dt.input_value() == today_s, f"本月止 {dt.input_value()} != {today_s}"
        total_month = parse_total(page)
        log.append(f"total_month={total_month}")

        # 返回本年
        page.locator("[data-testid=ledger-restore-year]").click()
        page.wait_for_timeout(1200)
        # 年可能来自 VM year_key
        y_from = df.input_value()
        y_to = dt.input_value()
        log.append(f"after restore year from={y_from} to={y_to}")
        assert y_from.endswith("-01-01") and y_to.endswith("-12-31"), f"返回本年 not full year {y_from}~{y_to}"
        total_restore = parse_total(page)
        log.append(f"total_restore={total_restore}")
        assert total_restore == total_year, f"restore year total {total_restore} != {total_year}"

        # 导出：请求拦截抽验参数
        export_url = {"u": ""}

        def on_req(req):
            if "/api/v1/vm/ledger/export" in req.url:
                export_url["u"] = req.url

        page.on("request", on_req)
        with page.expect_download(timeout=15000) as di:
            page.locator("[data-testid=ledger-export]").click()
        _ = di.value
        log.append(f"export_url={export_url['u']}")
        assert "date_from=" in export_url["u"] or "date_to=" in export_url["u"], "export missing date params"

        # 深色控件区
        set_theme(page, False)
        page.locator("[data-testid=ledger-date-tools]").scroll_into_view_if_needed()
        shot(page, "ledger_dates_dark_1440.png")
        page.locator("#dailyPanel").scroll_into_view_if_needed()
        shot(page, "daily_month_dark_1440.png")

        # 浅色
        set_theme(page, True)
        page.locator("[data-testid=ledger-date-tools]").scroll_into_view_if_needed()
        shot(page, "ledger_dates_light_1440.png")
        page.locator("#dailyPanel").scroll_into_view_if_needed()
        shot(page, "daily_month_light_1440.png")

        # 375
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(400)
        page.locator("[data-testid=ledger-date-tools]").scroll_into_view_if_needed()
        shot(page, "ledger_dates_dark_375.png")  # theme may still light; re-dark
        set_theme(page, False)
        page.locator("[data-testid=ledger-date-tools]").scroll_into_view_if_needed()
        shot(page, "ledger_dates_dark_375.png")
        page.locator("#dailyPanel").scroll_into_view_if_needed()
        shot(page, "daily_month_dark_375.png")
        set_theme(page, True)
        page.locator("[data-testid=ledger-date-tools]").scroll_into_view_if_needed()
        shot(page, "ledger_dates_light_375.png")
        page.locator("#dailyPanel").scroll_into_view_if_needed()
        shot(page, "daily_month_light_375.png")

        # 恢复宽屏做 R-51
        page.set_viewport_size({"width": 1440, "height": 900})
        set_theme(page, False)
        page.locator("#dailyPanel").scroll_into_view_if_needed()
        page.wait_for_timeout(400)

        # R-51 本月
        page.locator("#dailyThisMonth, [data-testid=daily-this-month]").first.click()
        page.wait_for_timeout(2000)
        s = page.locator("#dailyS").input_value()
        e = page.locator("#dailyE").input_value()
        log.append(f"daily this month s={s} e={e}")
        assert s == month_start and e == today_s, f"daily 本月 {s}~{e}"
        sum_text = page.locator("#dailySum").inner_text()
        log.append(f"dailySum={sum_text}")
        assert month_start[:7] in sum_text or s in sum_text or "~" in sum_text, "sum should reflect range"

        # 手选同区间再查，摘要区间一致
        page.locator("#dailyS").fill(month_start)
        page.locator("#dailyE").fill(today_s)
        page.locator("#dailyGo").click()
        page.wait_for_timeout(1500)
        sum2 = page.locator("#dailySum").inner_text()
        log.append(f"dailySum hand={sum2}")
        # 数字段应一致（去掉空白）
        def nums(t: str) -> str:
            return re.sub(r"\s+", "", t)

        assert nums(sum_text) == nums(sum2) or (s in sum2 and e in sum2), f"hand vs 本月 mismatch {sum_text!r} vs {sum2!r}"

        page.locator("#dailyClose").click()
        page.wait_for_timeout(800)
        log.append(f"after restore dailySum={page.locator('#dailySum').inner_text()!r}")

        browser.close()

    pe = [x for x in page_errors if x.strip()]
    ce = [x for x in console_errors if x.strip() and "favicon" not in x.lower()]
    log.append(f"page_errors={pe}")
    log.append(f"console_errors={ce}")
    ok = not pe and not ce and total_jan >= 0
    log.append(f"PASS={ok}")
    (SCRATCH / "r50_r51_playwright.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
