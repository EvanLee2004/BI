#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.6·T2-0：管理端体检浮层 — 展开后滚动/Esc/点外收起；1440 + 390 证据。"""
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
SCRATCH = Path(
    "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-33225311c65a/implementer"
)
EVID = (
    ROOT.parents[1]
    / "方案与文档"
    / "软件工程文档"
    / "3_测试"
    / "20260726_全站交互体验扫查"
)


def _admin_cred():
    rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("accounts") or []
    a = next(x for x in rows if x.get("权限") == "管理员")
    return a.get("账号"), a.get("密码")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP no playwright")
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
        print("refresh", e)

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

    user, pw = _admin_cred()
    EVID.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, w, h in (("desktop_1440", 1440, 900), ("mobile_390", 390, 844)):
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(base + "/login", wait_until="networkidle", timeout=90000)
            page.locator("input[type=text], input[autocomplete=username]").first.fill(user)
            page.locator("input[type=password]").first.fill(pw)
            for sel in ("button:has-text('进入')", "button:has-text('登录')", "button[type=submit]"):
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    break
            page.wait_for_timeout(1500)
            # admin redirect
            if "/admin" not in page.url:
                page.goto(base + "/admin", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1000)
            pill = page.locator("[data-testid=admin-health-pill]")
            pill.wait_for(timeout=15000)
            pill.click()
            page.wait_for_timeout(400)
            pop = page.locator("[data-testid=admin-health-pop]")
            open1 = pop.count() > 0 and pop.first.is_visible()
            page.screenshot(path=str(EVID / f"t2_0_{name}_open.png"), full_page=False)
            # scroll to collapse
            page.evaluate("window.scrollTo(0, 200)")
            page.wait_for_timeout(500)
            open_after_scroll = pop.count() > 0 and pop.first.is_visible()
            # re-open and Esc
            if not open_after_scroll:
                pill.click()
                page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            open_after_esc = page.locator("[data-testid=admin-health-pop]").count() > 0 and page.locator(
                "[data-testid=admin-health-pop]"
            ).first.is_visible()
            # re-open and outside click
            pill.click()
            page.wait_for_timeout(300)
            page.mouse.click(w - 20, h - 20)
            page.wait_for_timeout(300)
            open_after_out = page.locator("[data-testid=admin-health-pop]").count() > 0 and page.locator(
                "[data-testid=admin-health-pop]"
            ).first.is_visible()
            page.screenshot(path=str(EVID / f"t2_0_{name}_after.png"), full_page=False)
            row = {
                "viewport": name,
                "open": open1,
                "closed_after_scroll": not open_after_scroll,
                "closed_after_esc": not open_after_esc,
                "closed_after_outside": not open_after_out,
            }
            results.append(row)
            print(row)
            page.close()
        browser.close()

    try:
        srv.should_exit = True
    except Exception:
        pass

    summary = "# T2-0 黄条收起\n\n" + "\n".join(
        f"- {r['viewport']}: open={r['open']} scroll_close={r['closed_after_scroll']} esc={r['closed_after_esc']} outside={r['closed_after_outside']}"
        for r in results
    )
    (EVID / "t2_0_summary.md").write_text(summary + "\n", encoding="utf-8")
    (SCRATCH / "t2_0_summary.md").write_text(summary + "\n", encoding="utf-8")
    (SCRATCH / "t2_0_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = all(r["open"] and r["closed_after_scroll"] and r["closed_after_esc"] and r["closed_after_outside"] for r in results)
    print("PASS" if ok else "FAIL", results)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
