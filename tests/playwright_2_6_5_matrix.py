#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.5 体验巡检：3 账号 × 3 主题 × 2 视口 = 18 组（Playwright）。

真 hook 控制台 error；拒页面红条「页面出现异常」；断言弹层有行。
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT_ROOT = (
    ROOT.parents[1]
    / "方案与文档"
    / "软件工程文档"
    / "3_测试"
    / "20260726_2.6.5体验巡检"
)
SCRATCH = Path(
    "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-c31b43ef0cf9/implementer"
)

ACCOUNTS = ("管理员", "整体", "BU")
THEMES = ("neon", "dark", "light")
VIEWPORTS = (("desktop", 1440, 900), ("mobile", 390, 844))

# 注入：真实收集 console.error / pageerror
HOOK_JS = """
(() => {
  window.__kanban_console_errors = [];
  window.__kanban_page_errors = [];
  const oe = console.error.bind(console);
  console.error = (...args) => {
    try {
      window.__kanban_console_errors.push(args.map(a => String(a)).join(' ').slice(0, 400));
    } catch (e) {}
    oe(...args);
  };
  window.addEventListener('error', (ev) => {
    window.__kanban_page_errors.push(String(ev.message || ev.error || 'error').slice(0, 400));
  });
  window.addEventListener('unhandledrejection', (ev) => {
    window.__kanban_page_errors.push(String(ev.reason || 'rejection').slice(0, 400));
  });
})();
"""


def _load_accounts():
    rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("accounts") or []
    by = {"管理员": None, "整体": None, "BU": None}
    for a in rows:
        role = a.get("权限") or ""
        if role == "管理员" and not by["管理员"]:
            by["管理员"] = (a.get("账号"), a.get("密码"))
        elif role == "整体" and not by["整体"]:
            by["整体"] = (a.get("账号"), a.get("密码"))
        elif role not in ("管理员", "整体") and not by["BU"]:
            by["BU"] = (a.get("账号"), a.get("密码"))
    return by


def _collect_errors(page) -> list[str]:
    try:
        data = page.evaluate(
            """() => ({
              c: (window.__kanban_console_errors || []).slice(0, 20),
              p: (window.__kanban_page_errors || []).slice(0, 20),
              banner: !!(document.body && /页面出现异常|SyntaxError|addColorStop/i.test(document.body.innerText||'')),
              bannerText: (document.body && (document.body.innerText||'').match(/页面出现异常[^\\n]{0,80}/)||[])[0] || '',
            })"""
        )
    except Exception as e:
        return [f"eval_errors:{e}"]
    out = []
    for x in data.get("c") or []:
        out.append(f"console:{x}")
    for x in data.get("p") or []:
        out.append(f"page:{x}")
    if data.get("banner"):
        out.append(f"red_banner:{data.get('bannerText') or '页面出现异常'}")
    return out


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        SCRATCH.mkdir(parents=True, exist_ok=True)
        (SCRATCH / "playwright_env.txt").write_text("playwright not installed\n", encoding="utf-8")
        print("SKIP: playwright not installed")
        return 2

    import loaders
    import server
    import uvicorn

    cfg = dict(loaders.load_config(ROOT))
    cfg["zhiyun_auto_fetch"] = False
    cfg["serve_static"] = True
    try:
        server.refresh(cfg, ROOT)
    except Exception as e:
        print("refresh failed", e)
        return 3

    app = server.create_app(cfg, root=ROOT)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thr = threading.Thread(target=srv.run, daemon=True)
    thr.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/login", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        print("server not ready")
        return 4

    creds = _load_accounts()
    rows_out = []
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for acc_label in ACCOUNTS:
            cred = creds.get(acc_label)
            if not cred or not cred[0]:
                rows_out.append(
                    {"账号": acc_label, "主题": "-", "视口": "-", "状态": "SKIP 无账号", "缺陷": ""}
                )
                continue
            user, pw = cred
            for theme in THEMES:
                for vp_name, w, h in VIEWPORTS:
                    slot = f"{acc_label}_{theme}_{vp_name}"
                    out_dir = OUT_ROOT / slot
                    out_dir.mkdir(parents=True, exist_ok=True)
                    issues = []
                    try:
                        page = browser.new_page(viewport={"width": w, "height": h})
                        page.add_init_script(HOOK_JS)
                        page.goto(base + "/login", wait_until="networkidle", timeout=90000)
                        page.locator(
                            "input[type=text], #account, input[autocomplete=username]"
                        ).first.fill(user)
                        page.locator("input[type=password]").first.fill(pw)
                        for sel in (
                            "button:has-text('登录')",
                            "button:has-text('进入')",
                            "button[type=submit]",
                        ):
                            if page.locator(sel).count():
                                page.locator(sel).first.click()
                                break
                        page.wait_for_timeout(1500)
                        page.evaluate(
                            """(th) => {
                              document.documentElement.dataset.theme = th;
                              document.documentElement.classList.toggle('theme-light', th==='light');
                              localStorage.setItem('cockpit-theme', th);
                              localStorage.setItem('cockpit-theme-v2','1');
                              window.dispatchEvent(new CustomEvent('kanban-theme-change',{detail:{theme:th}}));
                            }""",
                            theme,
                        )
                        if acc_label != "BU":
                            page.goto(base + "/", wait_until="networkidle", timeout=90000)
                        page.wait_for_timeout(2000)
                        # 关掉入场遮罩（若仍在）
                        try:
                            splash = page.locator(".intro-splash")
                            if splash.count():
                                splash.first.click(timeout=1000, force=True)
                                page.wait_for_timeout(400)
                        except Exception:
                            pass
                        # 等 KPI / 图表区
                        try:
                            page.wait_for_selector(
                                ".kpi-host, #rankViews, .dual-rankings, .scifi-panel",
                                timeout=30000,
                            )
                        except Exception:
                            pass
                        page.wait_for_timeout(1000)
                        page.screenshot(path=str(out_dir / "01_home.png"), full_page=True)

                        errs = _collect_errors(page)
                        for e in errs:
                            if "favicon" in e.lower():
                                continue
                            issues.append(e)

                        # 点开展示明细：点按钮本体（force 绕过 sticky 顶栏拦截）
                        btns = page.locator("[data-testid=rank-others-btn], .rank-list__others, .pr-more, .rk-others-btn")
                        n = btns.count()
                        opened = 0
                        empty_modals = 0
                        for i in range(min(n, 8)):
                            try:
                                btn = btns.nth(i)
                                btn.scroll_into_view_if_needed()
                                page.wait_for_timeout(200)
                                btn.click(timeout=5000, force=True)
                                page.wait_for_timeout(900)
                                modal = page.locator(
                                    "[data-testid=data-modal], [data-testid=profit-rank-modal], .data-modal-mask, .rkm-mask"
                                )
                                if modal.count():
                                    text = modal.first.inner_text(timeout=3000)
                                    if "加载失败" in text:
                                        issues.append(f"modal{i} 加载失败")
                                    else:
                                        rows = modal.locator(
                                            "[data-testid=rank-bar], .rank-bar, .rk-row, .ev-row"
                                        ).count()
                                        if rows == 0 and "本期无数据" not in text:
                                            empty_modals += 1
                                            issues.append(f"modal{i} 无行")
                                        else:
                                            opened += 1
                                    page.screenshot(path=str(out_dir / f"02_modal_{i}.png"))
                                    page.keyboard.press("Escape")
                                    page.wait_for_timeout(200)
                                else:
                                    issues.append(f"modal{i} 未出现弹层")
                            except Exception as e:
                                issues.append(f"modal{i} {str(e)[:120]}")

                        # 周期切换（若有）
                        try:
                            for lab in ("年", "季", "月"):
                                loc = page.locator(f"button:has-text('{lab}'), .pp-tab:has-text('{lab}')")
                                if loc.count():
                                    loc.first.click(timeout=2000)
                                    page.wait_for_timeout(400)
                        except Exception:
                            pass

                        # 整体按钮权限
                        overall = page.locator("[data-testid=bu-nav-overall]")
                        has_overall = overall.count() > 0
                        if acc_label == "BU" and has_overall:
                            issues.append("BU 账号不应看到整体按钮")

                        # 再采一次错误（图表异步）
                        page.wait_for_timeout(800)
                        for e in _collect_errors(page):
                            if "favicon" in e.lower():
                                continue
                            if e not in issues:
                                issues.append(e)

                        page.screenshot(path=str(out_dir / "03_end.png"), full_page=True)
                        page.close()
                        status = "PASS" if not issues else "ISSUES"
                        rows_out.append(
                            {
                                "账号": acc_label,
                                "主题": theme,
                                "视口": vp_name,
                                "状态": status,
                                "缺陷": "; ".join(issues)[:500],
                                "明细点开": f"{opened}/{n}",
                                "空弹层": empty_modals,
                            }
                        )
                        print(slot, status, issues[:3])
                    except Exception as e:
                        rows_out.append(
                            {
                                "账号": acc_label,
                                "主题": theme,
                                "视口": vp_name,
                                "状态": "FAIL",
                                "缺陷": str(e)[:200],
                            }
                        )
                        print(slot, "FAIL", e)
        browser.close()

    try:
        srv.should_exit = True
    except Exception:
        pass

    lines = [
        "# 2.6.5 体验巡检总表",
        "",
        "> 真 hook `console.error` + `error`/`unhandledrejection`；拒红条「页面出现异常」。",
        "",
        "| 账号 | 主题 | 视口 | 状态 | 明细点开 | 空弹层 | 缺陷 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows_out:
        lines.append(
            f"| {r.get('账号')} | {r.get('主题')} | {r.get('视口')} | {r.get('状态')} | {r.get('明细点开','')} | {r.get('空弹层','')} | {r.get('缺陷','')} |"
        )
    summary = "\n".join(lines) + "\n"
    (OUT_ROOT / "summary.md").write_text(summary, encoding="utf-8")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "ux_matrix_summary.md").write_text(summary, encoding="utf-8")
    print("wrote", OUT_ROOT / "summary.md")
    fail = sum(1 for r in rows_out if r.get("状态") in ("FAIL", "ISSUES"))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
