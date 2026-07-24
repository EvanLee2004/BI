"""管理端文档页 /admin — Vue 单轨（任务书65·L1：legacy static 管理端已下线）。"""

from __future__ import annotations

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import accounts
import authz
import login_redirect
from app_state import _state
import session_ctx


def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler
    cfg = d.cfg
    root = d.root
    _user = d.user
    _bootstrap_page = d.bootstrap_page
    _html_doc = d.html_doc
    _audit = d.audit
    _set_acookie = d.set_acookie
    _set_vcookie = getattr(d, "set_vcookie", None)
    _vue_index = getattr(d, "vue_index", None)

    def _has_data() -> bool:
        """是否已首次取数成功（可进完整管理端）。"""
        if _state.get("has_data"):
            return True
        # 兼容 2.0.x 预装 admin_html 标记
        return bool(_state.get("admin_html"))

    def _spa():
        if not callable(_vue_index):
            raise HTTPException(status_code=503, detail="Vue 管理端未构建（缺 frontend/dist）")
        return _vue_index()

    @app.get("/admin/app.js")
    def admin_app_js(request: Request):
        """legacy admin.js 已下线（65·L1）；恒 410。"""
        _ = request
        return Response(
            "/* admin.js removed: use Vue /admin (stage65) */\n",
            status_code=410,
            media_type="application/javascript; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/admin/logout")
    def admin_logout(request: Request):
        """任务书52·F-3：管理端退出同样 bump 会话版本。2.5.0：退出到统一登录。"""
        name = _user(request)
        if name:
            accounts.bump_session_version(cfg, root, name)
            try:
                _audit(cfg, root, name, ("访问", "管理端退出（会话版本+1）"))
            except Exception:
                pass
        resp = RedirectResponse("/login", status_code=303)
        # 2.6.0：清 sid + 两旧名
        session_ctx.clear_all_session_cookies(resp)
        return resp

    @app.post("/admin/login")
    def admin_login(
        account: str = Form(""),
        password: str = Form(""),
        identity: str = Form(""),
        next: str = Form(""),
    ):
        """兼容旧 form：统一鉴权 + 分流（管理员写 acookie；非管理员写 vcookie）。"""
        import login_guard

        account = (account or identity or "").strip()
        if login_guard.is_locked(account, cfg):
            return RedirectResponse(
                login_redirect.login_url(next_path="/admin", msg=login_guard.lock_message(cfg)),
                status_code=303,
            )
        acc = accounts.authenticate(cfg, root, account, password)
        if not acc:
            login_guard.register_failure(account, cfg)
            return RedirectResponse(
                login_redirect.login_url(next_path="/admin", msg="账号或密码不正确"),
                status_code=303,
            )
        login_guard.clear_failures(account)
        accounts.mark_login(cfg, root, account)
        # 非管理员 next 默认忽略 /admin
        next_raw = next or ("/admin" if authz.is_admin(acc) else "")
        redir = login_redirect.resolve_login_redirect(
            acc, next_raw or None, bu_pages=_state.get("bu_pages") or {}
        )
        resp = RedirectResponse(redir, status_code=303)
        if authz.is_admin(acc):
            return _set_acookie(resp, account)
        if callable(_set_vcookie):
            return _set_vcookie(resp, account)
        return resp

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request):
        """管理员控制台：已登录管理员 → SPA；未登录 → 统一登录。"""
        if _user(request):
            if not _has_data():
                return _html_doc(_bootstrap_page())
            return _spa()
        return RedirectResponse(login_redirect.login_url(next_path="/admin"), status_code=303)

    @app.get("/admin/login", response_class=HTMLResponse)
    def admin_login_get(request: Request):
        """2.5.0：兼容书签 → 统一登录（可 next=/admin）。"""
        if _user(request):
            return RedirectResponse("/admin", status_code=303)
        return RedirectResponse(login_redirect.login_url(next_path="/admin"), status_code=303)

    @app.get("/admin/{spa_path:path}", response_class=HTMLResponse)
    def admin_spa_fallback(request: Request, spa_path: str = ""):
        """Vue SPA 深链回落。"""
        _ = spa_path
        if not _user(request):
            nxt = "/admin/" + spa_path if spa_path else "/admin"
            return RedirectResponse(login_redirect.login_url(next_path=nxt), status_code=303)
        if not _has_data():
            return _html_doc(_bootstrap_page())
        return _spa()
