#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastAPI 应用组装（3.2.0：从 server.create_app 抽出）。

职责：中间件安装、静态/SPA 挂载、会话闭包、DI SimpleNamespace、register_all、openapi 闸。
入口仍经 server.create_app 暴露。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import accounts
import auth_session
import export_png as _export_png
import refresh_pipeline
import session_ctx as _session_ctx
import tpl
from app_state import STATIC_DIR, _state
from audit_diff import (
    _audit,
    _bootstrap_page,
    _diff_accounts,
    _diff_bu_config,
    _manual_items_json,
    _run_reasons,
)
from middleware_stack import install_middleware
from settings_io import (
    EDITABLE_SETTINGS,
    get_schedule_times,
    normalize_schedule_times,
    read_zhiyun_conn,
    read_zhiyun_creds,
    save_settings,
    save_zhiyun_conn,
    save_zhiyun_creds,
)

_NO_STORE = {"Cache-Control": "no-store"}
_HIDE_PW_STYLE = tpl.load("partials/hide_pw_style.html")
_WRAP_OPEN = tpl.load("partials/wrap_open.html")
_BU_NAV_TPL = tpl.load("partials/bu_nav.html")
_BU_NAV_LINK_TPL = tpl.load("partials/bu_nav_link.html")
DEFAULT_PW = os.environ.get("KANBAN_ADMIN_PW", accounts.DEFAULT_ADMIN_PW)


def _html_doc(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(content, status_code=status_code, headers=_NO_STORE)


def _file_html_doc(path: Path) -> FileResponse:
    return FileResponse(path, media_type="text/html; charset=utf-8", headers=_NO_STORE)


def resolve_serve_static(cfg: dict | None = None) -> bool:
    env = os.environ.get("KANBAN_SERVE_STATIC")
    if env is not None and str(env).strip() != "":
        return str(env).strip().lower() in ("1", "true", "yes", "on")
    cfg = cfg or {}
    if "serve_static" in cfg:
        return bool(cfg.get("serve_static"))
    host = str(cfg.get("server_host") or "0.0.0.0")
    return host not in ("127.0.0.1", "localhost", "::1")


def resolve_server_host(cfg: dict | None = None) -> str:
    env = os.environ.get("KANBAN_SERVER_HOST")
    if env is not None and str(env).strip() != "":
        return str(env).strip()
    return str((cfg or {}).get("server_host") or "0.0.0.0")


def _view_login_file():
    """看板登录：纯 static。"""
    p = STATIC_DIR / "view_login.html"
    return _file_html_doc(p)


def _admin_login_file():
    """统一 303 → /login?next=/admin。"""
    import login_redirect
    from fastapi.responses import RedirectResponse

    return RedirectResponse(
        login_redirect.login_url(next_path="/admin"),
        status_code=303,
    )


def build_app(cfg, root=None) -> FastAPI:  # noqa: C901  # 纯装配分发壳（原 create_app）
    """组装 FastAPI 应用（行为与 3.1.0 create_app 一致）。"""
    app = FastAPI(title="甲骨易经营看板", docs_url=None, redoc_url=None, openapi_url=None)
    install_middleware(app, cfg=cfg, root=root)

    sec = auth_session.load_or_init_secret(cfg, root)
    accounts.load_accounts(cfg, root, create=True)

    if resolve_serve_static(cfg) and STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    _fe_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if _fe_dist.is_dir():
        app.mount("/app", StaticFiles(directory=str(_fe_dist), html=True), name="frontend")

    _favicon = STATIC_DIR / "favicon.ico"
    _favicon_svg = STATIC_DIR / "icons" / "favicon.svg"

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon_ico():
        if _favicon.is_file():
            return FileResponse(_favicon, media_type="image/x-icon")
        if _favicon_svg.is_file():
            return FileResponse(_favicon_svg, media_type="image/svg+xml")
        raise HTTPException(status_code=404, detail="favicon missing")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon_svg():
        if _favicon_svg.is_file():
            return FileResponse(_favicon_svg, media_type="image/svg+xml")
        raise HTTPException(status_code=404, detail="favicon missing")

    def _wants_html(request: Request) -> bool:
        accept = (request.headers.get("accept") or "").lower()
        if "text/html" in accept:
            return True
        if "application/json" in accept and "text/html" not in accept:
            return False
        path = request.url.path or ""
        if path.startswith("/api") or path.startswith("/openapi") or path.endswith(".json"):
            return False
        return "text/html" in accept or accept in ("", "*/*") or "text/*" in accept

    def _error_page(status: int, title: str, msg: str) -> HTMLResponse:
        home = "/" if status != 401 else "/login"
        tpl_path = STATIC_DIR / "templates" / "errors" / "http_error.html"
        raw = (
            tpl_path.read_text(encoding="utf-8")
            if tpl_path.is_file()
            else "__TITLE__ (__STATUS__) __MSG__ <a href=\"__HOME__\">home</a>"
        )
        html = (
            raw.replace("__TITLE__", title)
            .replace("__STATUS__", str(status))
            .replace("__MSG__", msg)
            .replace("__HOME__", home)
        )
        return HTMLResponse(html, status_code=status)

    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(request: Request, exc: StarletteHTTPException):
        if not _wants_html(request):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        code = exc.status_code
        if code == 404:
            return _error_page(404, "页面不存在", "找不到这个地址。可能链接已变更，或路径输错了。")
        if code >= 500:
            return _error_page(500, "服务暂时出了点问题", "系统开小差了，请稍后重试；若持续出现请联系管理员。")
        detail = exc.detail if isinstance(exc.detail, str) else "请求无法完成"
        return _error_page(code, "无法打开", detail)

    @app.exception_handler(Exception)
    async def _unhandled_exc_handler(request: Request, exc: Exception):
        import traceback

        traceback.print_exc()
        if not _wants_html(request):
            return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
        return _error_page(500, "服务暂时出了点问题", "系统开小差了，请稍后重试；若持续出现请联系管理员。")

    def _resolve(request: Request):
        cached = getattr(request.state, "kanban_ctx", None)
        if cached is not None or getattr(request.state, "kanban_ctx_resolved", False):
            return cached
        ctx = _session_ctx.resolve_session(request.cookies, sec=sec, cfg=cfg, root=root)
        request.state.kanban_ctx = ctx
        request.state.kanban_ctx_resolved = True
        return ctx

    def _user(request: Request) -> str | None:
        ctx = _resolve(request)
        if not ctx or not ctx.is_admin:
            return None
        return ctx.account

    def _vacct(request: Request) -> str | None:
        ctx = _resolve(request)
        if not ctx or ctx.is_admin:
            return None
        return ctx.account

    def _vacc_row(request: Request) -> dict | None:
        ctx = _resolve(request)
        if not ctx or ctx.is_admin:
            return None
        return ctx.row

    def _can_view_main(request: Request) -> bool:
        ctx = _resolve(request)
        if not ctx:
            return False
        return ctx.can_main

    def _can_view_bu(request: Request, bu_name: str) -> bool:
        ctx = _resolve(request)
        if not ctx:
            return False
        return ctx.can_see_bu(bu_name)

    def _bu_switcher_html(my_names, current: str) -> str:
        from urllib.parse import quote

        def esc(s):
            return (
                str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

        existing = [n for n in my_names if n in _state.get("bu_pages", {})]
        if len(existing) <= 1:
            return ""
        links = "".join(
            _BU_NAV_LINK_TPL.format(
                href=quote(n),
                current_attrs=(
                    ' aria-current="page" style="border-color:var(--blue)"' if n == current else ""
                ),
                name=esc(n),
            )
            for n in existing
        )
        return _BU_NAV_TPL.format(aria_label="我的 BU 分页", label="我的 BU", links=links)

    def _set_sid_cookie(resp, account: str):
        return _session_ctx.apply_sid_cookie(resp, sec=sec, cfg=cfg, root=root, account=account)

    def _set_vcookie(resp, account: str):
        return _set_sid_cookie(resp, account)

    def _set_acookie(resp, account: str):
        return _set_sid_cookie(resp, account)

    def _frontend_mode() -> str:
        """3.2.0：恒 vue（看端/管理端均 Vue dist）。"""
        return "vue"

    def _vue_index():
        root_dir = Path(__file__).resolve().parents[1]
        p = root_dir / "frontend" / "dist" / "index.html"
        if not p.is_file():
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse(
                "Vue frontend not built. Run scripts/build_frontend.sh",
                status_code=503,
            )
        return _file_html_doc(p)

    def _main_shell():
        return _vue_index()

    def _bu_shell():
        return _vue_index()

    from routes import register_all

    register_all(
        app,
        SimpleNamespace(
            cfg=cfg,
            root=root,
            user=_user,
            vacct=_vacct,
            vacc_row=_vacc_row,
            can_view_main=_can_view_main,
            can_view_bu=_can_view_bu,
            bu_switcher_html=_bu_switcher_html,
            set_vcookie=_set_vcookie,
            set_acookie=_set_acookie,
            main_shell=_main_shell,
            bu_shell=_bu_shell,
            view_login_file=_view_login_file,
            admin_login_file=_admin_login_file,
            bootstrap_page=_bootstrap_page,
            manual_items_json=_manual_items_json,
            html_doc=_html_doc,
            file_html_doc=_file_html_doc,
            audit=_audit,
            diff_accounts=_diff_accounts,
            diff_bu_config=_diff_bu_config,
            run_reasons=_run_reasons,
            start_refresh_async=refresh_pipeline.start_refresh_async,
            recompute=refresh_pipeline.recompute,
            get_schedule_times=get_schedule_times,
            normalize_schedule_times=normalize_schedule_times,
            save_settings=save_settings,
            read_zhiyun_creds=read_zhiyun_creds,
            save_zhiyun_creds=save_zhiyun_creds,
            read_zhiyun_conn=read_zhiyun_conn,
            save_zhiyun_conn=save_zhiyun_conn,
            screenshot_png=_export_png.screenshot_png,
            HIDE_PW_STYLE=_HIDE_PW_STYLE,
            WRAP_OPEN=_WRAP_OPEN,
            DEFAULT_PW=DEFAULT_PW,
            BU_NAV_TPL=_BU_NAV_TPL,
            BU_NAV_LINK_TPL=_BU_NAV_LINK_TPL,
            EDITABLE_SETTINGS=EDITABLE_SETTINGS,
            frontend_mode=_frontend_mode,
            vue_index=_vue_index,
        ),
    )

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_admin_only(request: Request):
        if not _user(request):
            raise HTTPException(status_code=401, detail="仅管理员可查看 OpenAPI")
        return app.openapi()

    @app.get("/docs", include_in_schema=False)
    def docs_admin_only(request: Request):
        if not _user(request):
            raise HTTPException(status_code=401, detail="仅管理员可查看 API 文档")
        from fastapi.openapi.docs import get_swagger_ui_html

        return get_swagger_ui_html(openapi_url="/openapi.json", title="看板 API")

    return app
