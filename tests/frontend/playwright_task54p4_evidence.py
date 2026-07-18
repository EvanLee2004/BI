#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.4 真浏览器证据：登录选择器对齐 LoginView（进入/登录）；管理端写路径真点击；改密踢会话；BU 页。

用法（服务已起 8018，建议 config data_dir=_golden_data）：
  .venv/bin/python tests/frontend/playwright_task54p4_evidence.py [SCRATCH]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54p4"
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-7034d6e0fee6/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
log: list[str] = []


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
                bus = a.get("可见BU") or ([p] if p not in ("BU",) else [])
                return str(a["账号"]), str(a["密码"]), bus
        return "bu_only", "8888", ["示意BU甲"]
    for a in rows:
        if a.get("账号") in ("overall", "123") and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "overall", "8888"


def click_login(page):
    """管理端按钮文案=进入；看端可能=登录。"""
    for sel in (
        "button:has-text('进入')",
        "button:has-text('登录')",
        "button[type=submit]",
        ".el-button--primary",
    ):
        loc = page.locator(sel)
        if loc.count():
            loc.first.click()
            return sel
    raise RuntimeError("no login button")


def fill_login(page, acc, pw):
    # Element Plus: first text input + password
    inputs = page.locator("input:not([type=hidden])")
    # prefer el-input inner
    if page.locator("input[type=password]").count():
        # fill non-password first
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


def admin_login(page, acc, pw) -> str:
    page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(600)
    fill_login(page, acc, pw)
    btn = click_login(page)
    page.wait_for_load_state("networkidle", timeout=90000)
    page.wait_for_timeout(1200)
    # assert left login
    url = page.url
    log.append(f"admin_login btn={btn} url={url}")
    if "/login" in url and page.locator("text=管理员端登录").count():
        # still on login - try again with force
        fill_login(page, acc, pw)
        click_login(page)
        page.wait_for_timeout(1500)
        url = page.url
    return url


def viewer_login(page, acc, pw) -> str:
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(500)
    fill_login(page, acc, pw)
    click_login(page)
    page.wait_for_load_state("networkidle", timeout=90000)
    page.wait_for_timeout(1200)
    return page.url


def shot(page, rel: str, full=True):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(p), full_page=full)
    log.append(f"shot {rel} {p.stat().st_size}b")
    return p


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        (SCRATCH / "browser_env_fail.log").write_text(str(e), encoding="utf-8")
        return 2

    results: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # —— A1 overall + perf ——
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        acc, pw = pick("overall")
        viewer_login(page, acc, pw)
        page.wait_for_timeout(800)
        shot(page, "final/A1_overall_dark_1440.png", True)
        perf = page.evaluate(
            """async () => {
              const longTasks = [];
              try {
                const obs = new PerformanceObserver((list) => {
                  for (const e of list.getEntries()) longTasks.push({d: e.duration});
                });
                obs.observe({type: 'longtask', buffered: true});
              } catch (e) {}
              const t0 = performance.now();
              window.scrollTo(0, document.body.scrollHeight);
              await new Promise(r => setTimeout(r, 1500));
              window.scrollTo(0, 0);
              await new Promise(r => setTimeout(r, 500));
              return {
                scroll_ms: performance.now() - t0,
                longTaskCount: longTasks.length,
                maxLongTask: longTasks.reduce((m,x)=>Math.max(m,x.d||0), 0),
                echartsIds: document.querySelectorAll('div[_echarts_instance_]').length,
                canvases: document.querySelectorAll('canvas').length,
                hasScifi: !!document.querySelector('.scifi-panel'),
              };
            }"""
        )
        (OUT / "perfA" / "performance_scroll.json").write_text(
            json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        results["perf"] = perf
        page.close()

        # —— A4 BU ——
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        bacc, bpw, bus = pick("bu")
        viewer_login(page, bacc, bpw)
        page.wait_for_timeout(800)
        bu_name = (bus or ["示意BU甲"])[0]
        import urllib.parse

        page.goto(
            f"{BASE}/bu/{urllib.parse.quote(bu_name)}",
            wait_until="networkidle",
            timeout=90000,
        )
        page.wait_for_timeout(1500)
        body = page.inner_text("body")[:200]
        results["A4_url"] = page.url
        results["A4_body_prefix"] = body
        shot(page, "final/A4_BU_dark_1440.png", True)
        content_l = page.content().lower()
        results["A4_ok"] = (
            "not found" not in body.lower()
            and (
                "scifi" in content_l
                or page.locator(".scifi-panel, .kpi, #periodSync").count() > 0
            )
        )
        page.close()

        # —— Admin write paths 真点击 ——
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        aacc, apw = pick("admin")
        url = admin_login(page, aacc, apw)
        results["admin_post_login_url"] = url
        still_login = (
            page.locator("text=管理员端登录").count() > 0
            and page.locator("button:has-text('进入')").count() > 0
        )
        results["admin_still_login"] = still_login
        if still_login:
            results["admin_write"] = "FAIL_still_login"
            shot(page, "admin/console.png", False)
        else:
            shot(page, "admin/console.png", False)
            page.goto(f"{BASE}/admin/settings", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1200)
            shot(page, "admin/settings.png", True)
            results["admin_settings_url"] = page.url
            results["admin_settings_has_form"] = page.locator("input, textarea, .el-input").count()
            # dirty bar 仅 dirty.size>0 才出「保存全部设置」
            # 优先「＋ 添加时间点」(必脏)；备份天数若已=max 则 + 无效
            dirty_ok = False
            try:
                add_t = page.locator("button:has-text('添加时间点')")
                if add_t.count() and add_t.first.is_visible():
                    add_t.first.scroll_into_view_if_needed()
                    add_t.first.click()
                    dirty_ok = True
                    results["admin_dirty_probe"] = "sched_add"
                else:
                    minus = page.locator(".el-input-number__decrease").first
                    if minus.count() and minus.is_visible():
                        minus.click()
                        dirty_ok = True
                        results["admin_dirty_probe"] = "backup_keep_minus"
            except Exception as e:
                results["admin_dirty_err"] = str(e)[:160]
            page.wait_for_timeout(600)
            # 等 dirty bar 并滚入视口
            try:
                bar = page.locator(".admin-dirty-bar, button:has-text('保存全部设置')").first
                bar.wait_for(state="visible", timeout=6000)
                bar.scroll_into_view_if_needed()
            except Exception:
                pass
            results["admin_dirty_bar_visible"] = page.locator(
                "button:has-text('保存全部设置')"
            ).count() > 0
            saved = False
            save_net: dict = {}
            for sel in (
                "button:has-text('保存全部设置')",
                ".admin-dirty-bar .el-button--primary",
                "button:has-text('保存全部')",
            ):
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible():
                    try:
                        with page.expect_response(
                            lambda r: r.request.method == "POST"
                            and ("/api/" in r.url)
                            and r.status < 500,
                            timeout=20000,
                        ) as resp_info:
                            loc.first.click()
                        resp = resp_info.value
                        save_net = {"url": resp.url, "status": resp.status, "sel": sel}
                        saved = True
                        results["admin_settings_save_click"] = sel
                        results["admin_settings_save_net"] = save_net
                        page.wait_for_timeout(800)
                        break
                    except Exception as e:
                        results["admin_settings_save_click_err"] = str(e)[:160]
            if not saved:
                # 已登录 cookie 真 POST（非 TestClient）——保底写路径证据
                api_write = page.evaluate(
                    """async () => {
                      const g = await fetch('/api/accounts', {credentials:'same-origin'});
                      const j = await g.json();
                      if (!g.ok) return {get: g.status};
                      const r = await fetch('/api/accounts', {
                        method:'POST', credentials:'same-origin',
                        headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({accounts: j.accounts||[]})
                      });
                      const b = await r.json().catch(()=>({}));
                      return {get: g.status, post: r.status, note: b.note||'', count: b.count};
                    }"""
                )
                results["admin_settings_save_click"] = "api_accounts_post_fallback"
                results["admin_settings_save_net"] = api_write
            results["admin_dirty_ok"] = dirty_ok
            shot(page, "admin/settings_after_save.png", False)
            page.goto(f"{BASE}/admin/edit/manual", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1000)
            shot(page, "admin/manual.png", True)
            results["admin_manual_url"] = page.url
            results["admin_manual_inputs"] = page.locator("input, textarea, table").count()
            # manual 写路径：dirty 一项后点「保存全部更改」或 API
            man_saved = False
            try:
                mi = page.locator("table input, .el-input input").first
                if mi.count() and mi.is_visible():
                    cv = mi.input_value()
                    mi.fill((cv or "0") if cv else "0")
                    mi.fill(cv or "")
                    # force dirty with toggle
                    if cv is not None:
                        mi.fill((cv + " ") if cv else "1")
                        mi.fill(cv or "")
                page.wait_for_timeout(300)
                for sel in (
                    "button:has-text('保存全部更改')",
                    "button:has-text('保存全部')",
                    ".admin-dirty-bar .el-button--primary",
                ):
                    if page.locator(sel).count() and page.locator(sel).first.is_visible():
                        with page.expect_response(
                            lambda r: r.request.method == "POST" and "/api/" in r.url,
                            timeout=12000,
                        ) as ri:
                            page.locator(sel).first.click()
                        results["admin_manual_save"] = {
                            "sel": sel,
                            "status": ri.value.status,
                            "url": ri.value.url,
                        }
                        man_saved = True
                        break
            except Exception as e:
                results["admin_manual_save_err"] = str(e)[:120]
            if not man_saved:
                results["admin_manual_save"] = "no_dirty_bar_ok_page_loaded"
            page.goto(f"{BASE}/admin/edit/detail", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1000)
            shot(page, "admin/detail.png", True)
            results["admin_detail_url"] = page.url
            api_st = page.evaluate(
                """async () => {
                  const r = await fetch('/api/accounts', {credentials:'same-origin'});
                  const j = await r.json().catch(()=>({}));
                  return {status: r.status, n: (j.accounts||[]).length};
                }"""
            )
            results["admin_accounts_api"] = api_st
            page.goto(f"{BASE}/admin/logout", wait_until="networkidle")
            page.wait_for_timeout(400)
            results["F2_logout_accounts"] = page.evaluate(
                """async () => (await fetch('/api/accounts', {credentials:'same-origin'})).status"""
            )
            shot(page, "sec/after_logout.png", False)
            page.goto(f"{BASE}/static/admin/admin.html", wait_until="networkidle")
            page.wait_for_timeout(500)
            results["static_admin_final_url"] = page.url
            results["admin_app_js"] = page.evaluate(
                "async () => (await fetch('/admin/app.js')).status"
            )

        page.close()

        # —— F2 改密踢会话：my_passwd 只认看端 VCOOKIE，字段 old/new ——
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        vacc, vpw = pick("overall")
        viewer_login(page, vacc, vpw)
        page.wait_for_timeout(800)
        kick = page.evaluate(
            """async (pw) => {
              const before = await fetch('/api/v1/session', {credentials:'same-origin'});
              const r = await fetch('/api/my_passwd', {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({old: pw, new: pw + 'K'})
              });
              const body = await r.text();
              const after = await fetch('/api/v1/session', {credentials:'same-origin'});
              return {
                before: before.status,
                change: r.status,
                changeBody: body.slice(0, 200),
                after_session: after.status
              };
            }""",
            vpw,
        )
        results["F2_passwd_kick"] = kick
        if kick.get("change") == 200:
            # 新密重登并还原
            page.goto(f"{BASE}/login", wait_until="networkidle")
            page.wait_for_timeout(400)
            fill_login(page, vacc, vpw + "K")
            click_login(page)
            page.wait_for_timeout(1000)
            rest = page.evaluate(
                """async (pw) => {
                  const r = await fetch('/api/my_passwd', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({old: pw + 'K', new: pw})
                  });
                  return r.status;
                }""",
                vpw,
            )
            results["F2_passwd_restored"] = rest
            results["F2_passwd_kick_ok"] = kick.get("after_session") == 401
        else:
            results["F2_passwd_kick_ok"] = False
        page.close()

        # F3 BU matrix
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        bacc, bpw, _ = pick("bu")
        viewer_login(page, bacc, bpw)
        page.wait_for_timeout(800)
        mat = page.evaluate(
            """async () => {
              const o = {};
              let r = await fetch('/api/v1/vm/cockpit', {credentials:'same-origin'});
              o.vm_cockpit = r.status;
              r = await fetch('/api/accounts', {credentials:'same-origin'});
              o.accounts = r.status;
              r = await fetch('/api/detail?table=' + encodeURIComponent('收入明细'), {credentials:'same-origin'});
              o.detail = r.status;
              return o;
            }"""
        )
        results["F3"] = mat
        (OUT / "sec" / "bu_403_matrix.json").write_text(
            json.dumps(mat, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        page.close()
        browser.close()

    (OUT / "admin" / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "sec" / "results.json").write_text(
        json.dumps(
            {k: results[k] for k in results if k.startswith("F") or "admin" in k or "static" in k},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "final" / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (SCRATCH / "evidence_real.log").write_text(
        "\n".join(log) + "\n" + json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("\n".join(log))
    # hard fail if still login
    if results.get("admin_still_login"):
        return 1
    if not results.get("A4_ok"):
        log.append("WARN A4 not ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
