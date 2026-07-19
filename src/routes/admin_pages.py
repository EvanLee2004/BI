"""管理端文档页 /admin — 从 server.create_app 纯搬家。"""

from __future__ import annotations


from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import accounts
from app_state import COOKIE, STATIC_DIR, _state


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
    _admin_login_file = d.admin_login_file
    _admin_static_html = d.admin_static_html
    _bootstrap_page = d.bootstrap_page
    _manual_items_json = d.manual_items_json
    _html_doc = d.html_doc
    _file_html_doc = d.file_html_doc
    _audit = d.audit
    _diff_accounts = d.diff_accounts
    _diff_bu_config = d.diff_bu_config
    _run_reasons = d.run_reasons

    def start_refresh_async(cfg, root=None, trigger="manual"):
        import server as _srv

        return _srv.start_refresh_async(cfg, root, trigger)

    def recompute(cfg, root=None):
        import server as _srv

        return _srv.recompute(cfg, root)

    _screenshot_png = d.screenshot_png
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN
    _frontend_mode = getattr(d, "frontend_mode", None)
    _vue_index = getattr(d, "vue_index", None)

    def _admin_is_vue() -> bool:
        """KANBAN_FRONTEND=vue 且 dist 可用时走 Vue SPA 管理端。"""
        try:
            return callable(_frontend_mode) and _frontend_mode() == "vue" and callable(_vue_index)
        except Exception:
            return False

    # —— 固定端点必须先于 /admin/{path} 通配注册 ——

    @app.get("/admin/app.js")
    def admin_app_js(request: Request):
        """管理端应用 JS。
        54.4·D4：vue 模式主 UI 已迁 Vue SPA → 本入口 410（禁止再当业务主路径）。
        legacy 模式仍注入 __MANUAL_ITEMS__ 供 static 对照。
        """
        if _admin_is_vue():
            return Response(
                "/* admin.js offline: use Vue /admin */\n",
                status_code=410,
                media_type="application/javascript; charset=utf-8",
                headers={"Cache-Control": "no-store"},
            )
        js_path = STATIC_DIR / "admin" / "admin.js"
        if not js_path.is_file():
            raise HTTPException(status_code=404, detail="admin.js missing")
        raw = js_path.read_text(encoding="utf-8")
        body = raw.replace("__MANUAL_ITEMS__", _manual_items_json(cfg))
        return Response(body, media_type="application/javascript; charset=utf-8", headers={"Cache-Control": "no-store"})

    @app.get("/admin/logout")
    def admin_logout(request: Request):
        """任务书52·F-3：管理端退出同样 bump 会话版本。"""
        name = _user(request)
        if name:
            accounts.bump_session_version(cfg, root, name)
            try:
                _audit(cfg, root, name, ("访问", "管理端退出（会话版本+1）"))
            except Exception:
                pass
        resp = RedirectResponse("/admin", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.post("/admin/login")
    def admin_login(
        account: str = Form(""), password: str = Form(""), identity: str = Form("")
    ):  # identity 兼容旧表单字段名，忽略
        import login_guard

        account = (account or identity or "").strip()
        if login_guard.is_locked(account, cfg):
            return RedirectResponse(
                "/admin?msg=" + __import__("urllib.parse").parse.quote(login_guard.lock_message(cfg)),
                status_code=303,
            )
        import authz

        acc = accounts.authenticate(cfg, root, account, password)
        if not acc or not authz.is_admin(acc):
            login_guard.register_failure(account, cfg)
            return RedirectResponse(
                "/admin?msg=" + __import__("urllib.parse").parse.quote("账号或密码不正确"), status_code=303
            )
        login_guard.clear_failures(account)
        accounts.mark_login(cfg, root, account)
        return _set_acookie(RedirectResponse("/admin", status_code=303), account)

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request):
        """管理员控制台。
        vue 模式：SPA（frontend/dist/index.html，前端 path=/admin 挂 AdminApp）。
        legacy：static/admin（+ /admin/app.js）。
        _state['admin_html'] 仅作「是否已首次取数成功」标记（truthy=完整台，空=引导页）。
        会话态文档 → 一律 no-store（防登录成功后仍吃缓存登录页）。"""
        if _user(request):
            # 数据未生成（空机器首次部署）→ 引导页：填智云账号→立即更新→自动进完整管理端（F-02）
            if not _state.get("admin_html"):
                return _html_doc(_bootstrap_page())
            if _admin_is_vue():
                return _vue_index()
            return _html_doc(_admin_static_html())
        # 未登录：vue → SPA 登录页；legacy → static 登录
        if _admin_is_vue():
            return _vue_index()
        return _admin_login_file()

    @app.get("/admin/login", response_class=HTMLResponse)
    def admin_login_get(request: Request):
        """Vue 路由 /admin/login：未登录进 SPA；已登录进控制台。"""
        if _user(request):
            return RedirectResponse("/admin", status_code=303)
        if _admin_is_vue():
            return _vue_index()
        return _admin_login_file()

    @app.get("/admin/{spa_path:path}", response_class=HTMLResponse)
    def admin_spa_fallback(request: Request, spa_path: str = ""):
        """Vue SPA 深链回落：/admin/edit/* · /admin/settings · /admin/review/* 等。
        app.js / logout / login 已在上方精确注册，不会落到这里。"""
        _ = spa_path  # 路径参数仅用于匹配深链，回落统一返回 index
        # 非 vue：不提供 SPA 深链
        if not _admin_is_vue():
            raise HTTPException(status_code=404, detail="Not Found")
        # 引导页优先（未取数）
        if _user(request) and not _state.get("admin_html"):
            return _html_doc(_bootstrap_page())
        return _vue_index()
