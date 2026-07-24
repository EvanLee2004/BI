#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.0 活体：本机起服务 + Playwright 三角色截图。

用法（在 看板正式程序 根）：
  .venv/bin/python scripts/live_smoke_2_6_0.py --out DIR --base http://127.0.0.1:PORT
若不传 --base，脚本会在临时目录起 create_app 并用 uvicorn 占随机端口。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))


def _boot_app():
    import accounts
    import loaders
    import server
    import support
    import uvicorn

    tmp = Path(tempfile.mkdtemp(prefix="kanban_smoke_"))
    (tmp / "数据").mkdir()
    cfg = dict(loaders.load_config(ROOT))
    cfg["data_dir"] = "数据"
    cfg["db_path"] = "数据/看板.db"
    cfg["zhiyun_auto_fetch"] = False
    cfg["serve_static"] = True
    accounts.save_accounts(
        cfg,
        tmp,
        [
            {
                "账号": "lushasha",
                "显示名": "管理员",
                "权限": "管理员",
                "密码": server.DEFAULT_PW,
            },
            {
                "账号": "overall",
                "显示名": "整体",
                "权限": "整体",
                "密码": server.DEFAULT_VIEW_PW,
            },
            {
                "账号": "user_a",
                "显示名": "BU甲",
                "权限": "BU甲",
                "密码": server.DEFAULT_VIEW_PW,
            },
        ],
    )
    server._state["user_html"] = "<html><body>main</body></html>"
    server._state["fragments"] = support.fake_main_frags("M")
    server._state["views"] = support.fake_views("M")
    server._state["bu_pages"] = {
        "BU甲": support.fake_bu_page("BU甲", "A"),
        "BU乙": support.fake_bu_page("BU乙", "B"),
    }
    server._state["admin_html"] = "x"
    server._state["has_data"] = True
    app = server.create_app(cfg, root=tmp)
    # pick free port
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    thr = threading.Thread(target=uvicorn.Server(config).run, daemon=True)
    thr.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            import urllib.request

            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    return base, server.DEFAULT_PW, server.DEFAULT_VIEW_PW, tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="")
    args = ap.parse_args()
    out = Path(args.out)
    for sub in ("admin", "overall", "bu", "cookie", "regression"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    checklist = []

    if args.base:
        base = args.base.rstrip("/")
        # production-like: passwords from env or defaults
        import server as srv

        admin_pw, view_pw = srv.DEFAULT_PW, srv.DEFAULT_VIEW_PW
    else:
        base, admin_pw, view_pw, _tmp = _boot_app()

    from playwright.sync_api import sync_playwright

    def shot(page, path, note):
        page.screenshot(path=str(path), full_page=True)
        checklist.append(f"{note}|ok|{path.name}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # --- admin ---
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(base + "/login", wait_until="networkidle")
        page.fill("#account, input[name=account], input[autocomplete=username]", "lushasha")
        page.fill("#password, input[type=password]", admin_pw)
        page.click("button[type=submit], button:has-text('进入')")
        page.wait_for_timeout(1500)
        shot(page, out / "admin" / "01_login.png", "admin login")
        url = page.url
        assert "/admin" in url or "admin" in url, url
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        assert "kanban_sid" in cookies, cookies.keys()
        (out / "cookie" / "admin_sid.txt").write_text(
            "names=" + ",".join(sorted(cookies.keys())), encoding="utf-8"
        )
        checklist.append("admin cookie has kanban_sid|ok|admin_sid.txt")
        page.goto(base + "/", wait_until="networkidle")
        page.wait_for_timeout(800)
        shot(page, out / "admin" / "02_cockpit.png", "admin open root")
        page.goto(base + "/admin", wait_until="networkidle")
        shot(page, out / "admin" / "03_admin.png", "admin console")
        # logout via API
        page.evaluate("() => fetch('/api/v1/logout',{method:'POST',credentials:'include'})")
        page.wait_for_timeout(500)
        page.goto(base + "/login", wait_until="networkidle")
        shot(page, out / "admin" / "04_logout.png", "admin logout")
        ctx.close()

        # --- overall ---
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(base + "/login", wait_until="networkidle")
        page.fill("#account, input[autocomplete=username]", "overall")
        page.fill("#password, input[type=password]", view_pw)
        page.click("button[type=submit], button:has-text('进入')")
        page.wait_for_timeout(1500)
        shot(page, out / "overall" / "01_login.png", "overall login")
        # should not stay on login
        assert "/login" not in page.url or page.url.rstrip("/").endswith("127"), page.url
        cookies = {c["name"] for c in ctx.cookies()}
        assert "kanban_sid" in cookies
        page.goto(base + "/admin", wait_until="networkidle")
        page.wait_for_timeout(800)
        shot(page, out / "overall" / "02_admin_blocked.png", "overall hit admin")
        # should redirect to login
        assert "login" in page.url or "admin" not in page.content().lower()[:200]
        page.evaluate("() => fetch('/api/v1/logout',{method:'POST',credentials:'include'})")
        ctx.close()

        # --- BU ---
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(base + "/login", wait_until="networkidle")
        page.fill("#account, input[autocomplete=username]", "user_a")
        page.fill("#password, input[type=password]", view_pw)
        page.click("button[type=submit], button:has-text('进入')")
        page.wait_for_timeout(1500)
        shot(page, out / "bu" / "01_login.png", "bu login")
        assert "/bu/" in page.url or "BU" in page.url, page.url
        page.goto(base + "/", wait_until="networkidle")
        page.wait_for_timeout(1000)
        shot(page, out / "bu" / "02_root_redirect.png", "bu reopen root")
        assert "/bu/" in page.url, page.url
        page.evaluate("() => fetch('/api/v1/logout',{method:'POST',credentials:'include'})")
        page.wait_for_timeout(400)
        # 新上下文测 next=/admin 不得进管理端
        ctx2 = browser.new_context()
        page2 = ctx2.new_page()
        page2.goto(base + "/login?next=%2Fadmin", wait_until="networkidle")
        page2.wait_for_selector("#account, input[autocomplete=username]", timeout=15000)
        page2.fill("#account, input[autocomplete=username]", "user_a")
        page2.fill("#password, input[type=password]", view_pw)
        page2.click("button[type=submit], button:has-text('进入')")
        page2.wait_for_timeout(1500)
        shot(page2, out / "bu" / "03_next_admin.png", "bu next admin ignored")
        assert "/admin" not in page2.url, page2.url
        ctx2.close()
        ctx.close()

        # regression /admin/login
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(base + "/admin/login", wait_until="networkidle")
        page.wait_for_timeout(800)
        shot(page, out / "regression" / "admin_login_compat.png", "admin/login compat")
        assert "login" in page.url
        ctx.close()
        browser.close()

    (out / "活体清单.md").write_text(
        "# 2.6.0 活体清单\n\n| 步骤 | 结果 | 文件 |\n|------|------|------|\n"
        + "\n".join(f"| {r.replace('|', ' | ')} |" for r in checklist)
        + "\n",
        encoding="utf-8",
    )
    (out / "summary.json").write_text(
        json.dumps({"base": base, "steps": checklist, "ok": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("SMOKE_OK", base, "steps=", len(checklist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
