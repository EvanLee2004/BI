"""管理端文档页 /admin — 从 server.create_app 纯搬家。"""

from __future__ import annotations


from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import accounts
from app_state import COOKIE, STATIC_DIR, _state


def register(app, d):
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

    get_schedule_times = d.get_schedule_times
    normalize_schedule_times = d.normalize_schedule_times
    save_settings = d.save_settings
    read_zhiyun_creds = d.read_zhiyun_creds
    save_zhiyun_creds = d.save_zhiyun_creds
    read_zhiyun_conn = d.read_zhiyun_conn
    save_zhiyun_conn = d.save_zhiyun_conn
    _screenshot_png = d.screenshot_png
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN
    DEFAULT_PW = d.DEFAULT_PW

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request):
        """管理员控制台：仅 static/admin（+ /admin/app.js）。
        _state['admin_html'] 仅作「是否已首次取数成功」标记（truthy=完整台，空=引导页）。
        会话态文档 → 一律 no-store（防登录成功后仍吃缓存登录页）。"""
        if _user(request):
            # 数据未生成（空机器首次部署）→ 引导页：填智云账号→立即更新→自动进完整管理端（F-02）
            if not _state.get("admin_html"):
                return _html_doc(_bootstrap_page())
            return _html_doc(_admin_static_html())
        return _admin_login_file()

    @app.get("/admin/app.js")
    def admin_app_js(request: Request):
        """管理端应用 JS：磁盘 static/admin/admin.js 与抽取常量一致，
        仅将 __MANUAL_ITEMS__ 换成当前 config 手填项 JSON（纯注入、不算账）。"""

        js_path = STATIC_DIR / "admin" / "admin.js"
        if not js_path.is_file():
            raise HTTPException(status_code=404, detail="admin.js missing")
        raw = js_path.read_text(encoding="utf-8")
        body = raw.replace("__MANUAL_ITEMS__", _manual_items_json(cfg))
        return Response(body, media_type="application/javascript; charset=utf-8", headers={"Cache-Control": "no-store"})

    @app.post("/admin/login")
    def admin_login(
        account: str = Form(""), password: str = Form(""), identity: str = Form("")
    ):  # identity 兼容旧表单字段名，忽略
        account = (account or identity or "").strip()
        acc = accounts.authenticate(cfg, root, account, password)
        if not acc or not accounts.is_admin(acc):
            return RedirectResponse(
                "/admin?msg=" + __import__("urllib.parse").parse.quote("账号或密码不正确"), status_code=303
            )
        accounts.mark_login(cfg, root, account)
        return _set_acookie(RedirectResponse("/admin", status_code=303), account)

    @app.get("/admin/logout")
    def admin_logout():
        resp = RedirectResponse("/admin", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp
