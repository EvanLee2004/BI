"""鉴权与页面入口（/ · /login · /bu 页 · session/login/logout · accounts） — 从 server.create_app 纯搬家。"""

from __future__ import annotations


from fastapi import Body, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import accounts
import api_v1
import authz
import db
from app_state import COOKIE, VCOOKIE, _state


def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler
    cfg = d.cfg
    root = d.root
    _user = d.user
    _vacct = d.vacct
    _vacc_row = d.vacc_row
    _can_view_main = d.can_view_main
    _can_view_bu = d.can_view_bu
    _bu_switcher_html = d.bu_switcher_html
    _set_vcookie = d.set_vcookie
    _set_acookie = d.set_acookie
    _main_shell = d.main_shell
    _bu_shell = d.bu_shell
    _view_login_file = d.view_login_file
    _bootstrap_page = d.bootstrap_page
    _manual_items_json = d.manual_items_json
    _html_doc = d.html_doc
    _file_html_doc = d.file_html_doc
    _audit = d.audit
    _diff_accounts = d.diff_accounts
    _diff_bu_config = d.diff_bu_config
    _run_reasons = d.run_reasons


    _screenshot_png = d.screenshot_png
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN
    _BU_NAV_TPL = d.BU_NAV_TPL
    _BU_NAV_LINK_TPL = d.BU_NAV_LINK_TPL

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    def _conn():
        return db.connect(cfg, root)

    @app.get("/", response_class=HTMLResponse)
    def user_page(request: Request):
        """看板统一入口：未登录 → 登录；已登录 → Vue dist SPA（54.4·C 删 shell）。"""
        if _user(request):
            return _main_shell()
        acc = _vacc_row(request)
        if acc:
            if accounts.is_main(acc):
                return _main_shell()
            names = accounts.bu_names_of(acc)
            if names:
                existing = [n for n in names if n in _state.get("bu_pages", {})]
                if not existing:
                    return RedirectResponse(
                        "/login?msg="
                        + __import__("urllib.parse").parse.quote("你绑定的 BU 已被管理员移除，请重新登录或联系管理员"),
                        status_code=303,
                    )
                # BU 账号：壳 + 本 BU fragments（隔离由 fragments API 保证）
                return RedirectResponse(f"/bu/{existing[0]}", status_code=303)
            if authz.is_admin(acc):
                return RedirectResponse("/admin", status_code=303)
        return _view_login_file()

    @app.get("/login", response_class=HTMLResponse)
    def viewer_login_page():
        """看板登录 static 页（B-P4）。"""
        return _view_login_file()

    @app.post("/login")
    def viewer_login(account: str = Form(""), password: str = Form("")):
        """兼容旧 form POST：成功重定向；失败回登录 static（错误见 query，前端也可走 /api/v1/login）。"""
        import login_guard

        account = account.strip()
        if login_guard.is_locked(account, cfg):
            return RedirectResponse(
                "/login?msg=" + __import__("urllib.parse").parse.quote(login_guard.lock_message(cfg)),
                status_code=303,
            )
        acc = accounts.authenticate(cfg, root, account, password)
        if not acc:
            login_guard.register_failure(account, cfg)
            _audit(cfg, root, account or "?", ("访问", f"登录失败：{account or '空账号'}"))
            return RedirectResponse(
                "/login?msg=" + __import__("urllib.parse").parse.quote("账号或密码不正确"), status_code=303
            )
        login_guard.clear_failures(account)
        accounts.mark_login(cfg, root, account)
        _audit(cfg, root, account, ("访问", f"登录成功：{account}"))
        if authz.is_admin(acc):
            return _set_acookie(RedirectResponse("/admin", status_code=303), account)
        if accounts.is_main(acc):
            return _set_vcookie(RedirectResponse("/", status_code=303), account)
        names = accounts.bu_names_of(acc)
        redir = f"/bu/{names[0]}" if names else "/"
        return _set_vcookie(RedirectResponse(redir, status_code=303), account)

    @app.get("/bu/{name}", response_class=HTMLResponse)
    def bu_page(name: str, request: Request):
        """BU 页：Vue dist SPA（54.4·C）。未登录 → 登录。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        if not _can_view_bu(request, name):
            return _view_login_file()
        return _bu_shell()

    # ---------- v1.4 JSON API（只序列化 summary，不算账）----------
    @app.get("/api/v1/session")
    def api_v1_session(request: Request):
        admin = _user(request)
        if admin:
            acc = accounts.find_account(cfg, root, admin)
            return api_v1.session_public(acc, is_admin_session=True)
        acc = _vacc_row(request)
        if not acc:
            raise HTTPException(status_code=401, detail="未登录")
        return api_v1.session_public(acc)

    @app.post("/api/v1/login")
    def api_v1_login(payload: dict = Body(default={})):
        import login_guard

        account = str(payload.get("account") or "").strip()
        password = str(payload.get("password") or "")
        if login_guard.is_locked(account, cfg):
            raise HTTPException(status_code=429, detail=login_guard.lock_message(cfg))
        acc = accounts.authenticate(cfg, root, account, password)
        if not acc:
            login_guard.register_failure(account, cfg)
            _audit(cfg, root, account or "?", ("访问", f"登录失败：{account or '空账号'}"))
            raise HTTPException(status_code=401, detail="账号或密码不正确")
        login_guard.clear_failures(account)
        accounts.mark_login(cfg, root, account)
        _audit(cfg, root, account, ("访问", f"登录成功：{account}"))
        if authz.is_admin(acc):
            sess = api_v1.session_public(acc, is_admin_session=True)
            resp = JSONResponse({"ok": True, "redirect": "/admin", "session": sess})
            return _set_acookie(resp, account)
        sess = api_v1.session_public(acc)
        redir = "/"
        if not accounts.is_main(acc):
            names = accounts.bu_names_of(acc)
            if names:
                redir = f"/bu/{names[0]}"
        resp = JSONResponse({"ok": True, "redirect": redir, "session": sess})
        return _set_vcookie(resp, account)

    @app.post("/api/v1/logout")
    def api_v1_logout(request: Request):
        """任务书52·F-3：删 cookie +  bump 账号会话版本，旧 cookie 重放 401。"""
        name = _user(request) or _vacct(request)
        if name:
            accounts.bump_session_version(cfg, root, name)
            _audit(cfg, root, name, ("访问", "退出登录（会话版本+1）"))
        resp = JSONResponse({"ok": True})
        # 2.4.3：path/samesite 与 set_cookie 一致，避免删不干净导致二次进根路径身份串扰
        resp.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax")
        resp.delete_cookie(VCOOKIE, path="/", httponly=True, samesite="lax")
        return resp

    @app.post("/api/my_passwd")
    def api_my_passwd(request: Request, payload: dict = Body(default={})):
        """看的人自改密码（整体页/BU 页右上 🔑）：验旧设新，密码版本+1（旧会话失效）。"""
        name = _vacct(request)
        if not name:
            raise HTTPException(status_code=401, detail="请先登录看板")
        old, new = str(payload.get("old") or ""), str(payload.get("new") or "")
        err = accounts.change_password(cfg, root, name, old, new)
        if err:
            raise HTTPException(status_code=400, detail=err)
        _audit(cfg, root, name, ("密码", f"账号 {name} 自改密码"))  # C3：不记密码内容
        return {"note": "密码已修改", "relogin": True}

    @app.get("/api/accounts")
    def api_accounts_get(request: Request):
        """账号表（管理员会话）：下发明文密码（管理端 👁 可见可改；任务书64·P 产品口径）。"""
        _require(request)
        rows = [accounts.public_row(a, with_password=True) for a in accounts.load_accounts(cfg, root)]
        return {"accounts": rows, "count": len(rows), "master_account": accounts.MASTER_ACCOUNT}

    @app.post("/api/accounts")
    def api_accounts_post(request: Request, payload: dict = Body(default={})):
        """保存账号表（管理员）。至少保留一个管理员；总账号不可删。C3：变更留痕（密码只记「改密码」）。"""
        user = _require(request)
        raw = payload.get("accounts")
        if not isinstance(raw, list):
            raise HTTPException(status_code=400, detail="accounts 须为列表")
        if len(raw) > 50:
            raise HTTPException(status_code=400, detail="账号数量过多（上限 50）")
        old_accs = accounts.load_accounts(cfg, root, create=False)
        try:
            saved = accounts.save_accounts(cfg, root, raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        _audit(cfg, root, user, _diff_accounts(old_accs, saved))
        rows = [accounts.public_row(a, with_password=True) for a in saved]
        return {"accounts": rows, "count": len(rows), "note": "已保存", "master_account": accounts.MASTER_ACCOUNT}

    @app.post("/api/accounts/{acct}/reset_passwd")
    def api_accounts_reset_passwd(request: Request, acct: str, payload: dict = Body(default={})):
        """管理员重置密码（快捷入口；列表亦可直接编辑明文）。body.new 可选。"""
        user = _require(request)
        new = payload.get("new") if isinstance(payload, dict) else None
        plain, err = accounts.reset_password(cfg, root, acct, new if new is not None else None)
        if err:
            raise HTTPException(status_code=400, detail=err)
        _audit(cfg, root, user, ("密码", f"管理员重置账号 {acct} 密码"))  # 不记明文
        return {
            "status": "ok",
            "账号": acct,
            "password": plain,
            "note": "已重置；管理端账号表亦可直接查看/编辑明文",
        }
