#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内网双端服务（FastAPI + uvicorn）：用户端只读 + 管理员控制台（明细编辑/手填/年度预算/调整台账）。

- 用户端 `/`：账号+密码登录，按 数据/看板账号.json 权限分流（管理员→/admin、整体→整体页、BU→本 BU 页）。
- 管理员端 `/admin`：账号 lushasha（或任何权限=管理员的号）+ 密码；经手人=登录账号。
- `/api/detail`：明细数据，**仅管理员会话内可用**（服务端挡，未登录 401；非前端藏）。
- `/api/health`：最近一次运行日志（体检状态条数据源）。

安全实现用标准库：会话 HMAC 签名 token；账号明文存 数据/看板账号.json（不进 git）。
会话签名密钥存 数据/管理员密钥.json（只保留 cookie_key；旧 salt/pw_hash 字段读时忽略）。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

import loaders
import accounts
import tpl
import auth_session
import refresh_pipeline
from app_state import (  # noqa: F401  # 测试/外部可读 server._state
    COOKIE,
    VCOOKIE,
    SESSION_TTL,
    STATIC_DIR,
    _state,
    _LOCK,
    _EXPORT_LOCK,
)


# 54.13 纯搬家 re-export
from settings_io import (  # noqa: E402,F401
    _TIME_RE,
    EDITABLE_SETTINGS,
    MAX_SCHEDULE_TIMES,
    normalize_schedule_times,
    get_schedule_times,
    CRON_BEGIN,
    CRON_END,
    _cron_block_for_times,
    _strip_cron_sentinel,
    _linux_sync_schedule,
    sync_schedule,
    _zhiyun_cfg_file,
    read_zhiyun_creds,
    save_zhiyun_creds,
    read_zhiyun_conn,
    save_zhiyun_conn,
    save_settings,
)
from audit_diff import (  # noqa: E402,F401
    _audit,
    _join_summary,
    _diff_bu_config,
    _diff_accounts,
    _manual_items_json,
    _admin_page,
    _bootstrap_page,
    admin_ui_source,
    _run_reasons,
    apply_business_health_yellow,
    _ZY_BANNER_NAMES,
    _ZY_FILE_KEYS,
    _file_as_of_label,
    build_fetch_fallback_banners,
)

# 任务书36·A：fragments JSON 等文本响应 gzip（Starlette 内置；minimum_size≈1KB）
GZIP_MINIMUM_SIZE = 1000

# B-P5：已登录整体/BU 页固定 static shell + fragments（无 SERVE_SHELL 化石开关）。
# 测试断言 HTML 内容请用 _state["user_html"] / page["html"] / fragments 组装，勿依赖 / 直出 SSR。

# 会话态文档页禁止浏览器缓存：未登录时同一 URL 是登录页，登录后是 shell/控制台；
# 若缺 no-store，登录成功 location.replace 同 URL 会直接吃缓存登录页（P0·2026-07-16）。
# 真正静态 css/js/图走 /static 不受影响；/admin/app.js 已有同类先例。
_NO_STORE = {"Cache-Control": "no-store"}


def _html_doc(content: str, status_code: int = 200) -> HTMLResponse:
    """HTML 文档响应：带 no-store，防会话态页面被缓存。"""
    return HTMLResponse(content, status_code=status_code, headers=_NO_STORE)


def _file_html_doc(path: Path) -> FileResponse:
    """HTML 文件文档响应：带 no-store。"""
    return FileResponse(path, media_type="text/html; charset=utf-8", headers=_NO_STORE)


# 管理员会话看内嵌看板时隐藏「🔑密码」自改入口（管理员改密走 /admin 设置页，避免误改）
# 模板缓存于模块载入（tpl.load 一次）；内容与迁前逐字节一致
_HIDE_PW_STYLE = tpl.load("partials/hide_pw_style.html")
_WRAP_OPEN = tpl.load("partials/wrap_open.html")
_EMPTY_DATA_HTML = tpl.load("partials/empty_data.html")
_BU_NAV_TPL = tpl.load("partials/bu_nav.html")
_BU_NAV_LINK_TPL = tpl.load("partials/bu_nav_link.html")
# 兼容旧测试/文档引用（v8.0 起管理员口令在 看板账号.json，不再走密钥哈希）
DEFAULT_PW = os.environ.get("KANBAN_ADMIN_PW", accounts.DEFAULT_ADMIN_PW)
DEFAULT_VIEW_PW = accounts.DEFAULT_VIEW_PW
DEFAULT_ADMIN_ACCOUNT = "lushasha"

# ---------------- 会话（auth_session）兼容别名 ----------------
_secret_path = auth_session.secret_path
_load_or_init_secret = auth_session.load_or_init_secret
_save_secret = auth_session.save_secret
_make_token = auth_session.make_token
_check_token_raw = auth_session.check_token_raw
_check_token = auth_session.check_token
_check_vsubject = auth_session.check_vsubject

# ---------------- 刷新管道（refresh_pipeline）兼容别名 ----------------
# 注意：_do_full / start_refresh_async 必须挂在 server 模块上，
# 以便 tests 打桩 server._do_full（见 test_admin_edit 刷新异步）。
_publish = refresh_pipeline.publish
_do_full = refresh_pipeline.do_full
_do_recompute = refresh_pipeline.do_recompute
recompute = refresh_pipeline.recompute


def refresh(cfg, root=None, trigger="manual") -> dict:
    """完整更新；持锁调用本模块 _do_full（可被测试替换）。"""
    with _LOCK:
        return _do_full(cfg, root, trigger)


def start_refresh_async(cfg, root=None, trigger="manual") -> bool:
    """后台完整更新。调用本模块 _do_full，便于测试打桩。"""
    if not _LOCK.acquire(blocking=False):
        return False
    _state["refreshing"] = {"started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger}

    def _job():
        t0 = time.time()
        try:
            ing = _do_full(cfg, root, trigger)
            elapsed_ms = int((time.time() - t0) * 1000)
            # 2.3.0 S6.B：真实 metrics（禁永久 null）
            sources = []
            try:
                meta = (_state.get("summary") or {}).get("meta") or {}
                sources = (meta.get("health") or {}).get("sources") or []
            except Exception:
                sources = []
            n = len(sources) if isinstance(sources, list) else 0
            n_fail = 0
            if n:
                for s in sources:
                    if isinstance(s, dict) and s.get("ok") is False:
                        n_fail += 1
                    elif isinstance(s, dict) and str(s.get("status") or "").lower() in (
                        "fail",
                        "error",
                        "failed",
                    ):
                        n_fail += 1
            fail_rate = (n_fail / n) if n else 0.0
            _state["metrics"] = {
                "update_ms": elapsed_ms,
                "fetch_fail_rate": round(fail_rate, 4),
            }
            _state["last_refresh"] = {
                "status": "ok",
                "result": ing.get("result"),
                "seconds": round(time.time() - t0, 1),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            _state["metrics"] = {
                "update_ms": elapsed_ms,
                "fetch_fail_rate": 1.0,
            }
            _state["last_refresh"] = {
                "status": "error",
                "detail": f"{type(e).__name__}: {e}",
                "seconds": round(time.time() - t0, 1),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        finally:
            _state["refreshing"] = None
            _LOCK.release()

    threading.Thread(target=_job, daemon=True).start()
    return True


# ---------------- 设置（config.json 可改项：自动更新时间/备份保留天数/在线抓开关） ----------------
# 任务书54·D：Windows 计划任务 / 启动脚本全线退役；定时同步仅 Linux crontab。







# Linux crontab 哨兵（与 deploy/linux/register_schedule.sh 一致；绝不动段外行）






















# recompute 已由 refresh_pipeline 提供（秒级重算：缓存记录→重放→重算→重渲染）


# ---------------- 配置变更留痕（C3）：写接口 diff → 人读摘要 → db.log_config_change ----------------












# refresh_pipeline.publish 拼 admin_html 时调用（避免 pipeline↔server 环依赖）
refresh_pipeline.set_admin_page_builder(_admin_page)










# 智云源键 → 人读短名（任务书37·B9 黄横幅）






def _view_login_file():
    """看板登录：纯 static（B-P4 增补；错误由前端按 API 渲染）。会话态文档 → no-store。"""
    p = STATIC_DIR / "view_login.html"
    return _file_html_doc(p)


def _admin_login_file():
    """管理端登录：纯 static。会话态文档 → no-store。"""
    p = STATIC_DIR / "admin_login.html"
    return _file_html_doc(p)


# ---------------- FastAPI 应用 ----------------
def resolve_serve_static(cfg: dict | None = None) -> bool:
    """是否由 FastAPI 挂载 /static。nginx 模式 false（静态由 nginx 伺服）；直连 true。
    环境变量 KANBAN_SERVE_STATIC=0/1/false/true 可覆盖 config。"""
    import os

    env = os.environ.get("KANBAN_SERVE_STATIC")
    if env is not None and str(env).strip() != "":
        return str(env).strip().lower() in ("1", "true", "yes", "on")
    cfg = cfg or {}
    if "serve_static" in cfg:
        return bool(cfg.get("serve_static"))
    # 未配置时：绑 127.0.0.1 默认不挂静态（倾向反代）；否则挂（直连兼容）
    host = str(cfg.get("server_host") or "0.0.0.0")
    return host not in ("127.0.0.1", "localhost", "::1")


def resolve_server_host(cfg: dict | None = None) -> str:
    """监听地址。KANBAN_SERVER_HOST 优先；默认 config server_host → 0.0.0.0。"""
    import os

    env = os.environ.get("KANBAN_SERVER_HOST")
    if env is not None and str(env).strip() != "":
        return str(env).strip()
    return str((cfg or {}).get("server_host") or "0.0.0.0")


def create_app(cfg, root=None) -> FastAPI:  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler
    """组装 FastAPI：会话/中间件依赖 + 路由注册（路由体见 routes/）。"""
    app = FastAPI(title="甲骨易经营看板", docs_url=None, redoc_url=None, openapi_url=None)
    # 任务书36·A：内置 gzip，压 JSON/文本（≥1KB）；不自写压缩、不加依赖。
    # 任务书43：nginx 模式也保留 GZipMiddleware（双模兼容；反代时可再由 nginx gzip）。
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE)

    # 任务书46·6：请求 ID 中间件
    import uuid as _uuid

    from starlette.middleware.base import BaseHTTPMiddleware

    class _RequestIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            rid = request.headers.get("X-Request-ID") or _uuid.uuid4().hex[:16]
            request.state.request_id = rid
            resp = await call_next(request)
            resp.headers["X-Request-ID"] = rid
            return resp

    app.add_middleware(_RequestIdMiddleware)
    sec = _load_or_init_secret(cfg, root)
    # 确保账号文件存在（部署零配置）
    accounts.load_accounts(cfg, root, create=True)
    # 静态：直连模式挂载；nginx 模式由 nginx 伺服 /static/（serve_static=false）
    if resolve_serve_static(cfg) and STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    # 任务书46·3：Vue dist 静态资源 /app/
    _fe_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if _fe_dist.is_dir():
        app.mount("/app", StaticFiles(directory=str(_fe_dist), html=True), name="frontend")

    # 54.12 R-13 favicon
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
        # 浏览器地址栏直开常带 */* 或空；排除明确 JSON/API
        if "application/json" in accept and "text/html" not in accept:
            return False
        path = request.url.path or ""
        if path.startswith("/api") or path.startswith("/openapi") or path.endswith(".json"):
            return False
        return "text/html" in accept or accept in ("", "*/*") or "text/*" in accept

    def _error_page(status: int, title: str, msg: str) -> HTMLResponse:
        """54.12 R-14：友好错误页（模板在 static/templates/errors，禁 HTML-in-py）。"""
        home = "/" if status != 401 else "/login"
        tpl = STATIC_DIR / "templates" / "errors" / "http_error.html"
        raw = tpl.read_text(encoding="utf-8") if tpl.is_file() else (
            "__TITLE__ (__STATUS__) __MSG__ <a href=\"__HOME__\">home</a>"
        )
        # 简单占位替换，避免 HTML 字面量进 .py
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
        # 保留 API JSON 契约
        if not _wants_html(request):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        code = exc.status_code
        if code == 404:
            return _error_page(404, "页面不存在", "找不到这个地址。可能链接已变更，或路径输错了。")
        if code >= 500:
            return _error_page(500, "服务暂时出了点问题", "系统开小差了，请稍后重试；若持续出现请联系管理员。")
        # 其它 4xx 仍给友好页
        detail = exc.detail if isinstance(exc.detail, str) else "请求无法完成"
        return _error_page(code, "无法打开", detail)

    @app.exception_handler(Exception)
    async def _unhandled_exc_handler(request: Request, exc: Exception):
        import traceback
        traceback.print_exc()
        if not _wants_html(request):
            return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
        return _error_page(500, "服务暂时出了点问题", "系统开小差了，请稍后重试；若持续出现请联系管理员。")

    def _session_subject(cookie_val: str) -> str | None:
        """校验 cookie：签名/过期 + 密码版本与账号表一致（改密踢会话）。"""
        raw = auth_session.check_token_raw(sec, cookie_val or "")
        if not raw:
            return None
        name, tok_ver = raw
        acc = accounts.find_account(cfg, root, name)
        if not acc:
            return None
        if tok_ver != accounts.password_version_of(acc):
            return None
        return name

    def _user(request: Request) -> str | None:
        """管理员会话：cookie 主体=账号名，且账号表里权限仍是「管理员」。经手人=该账号。"""
        import authz

        name = _session_subject(request.cookies.get(COOKIE, ""))
        if not name:
            return None
        acc = accounts.find_account(cfg, root, name)
        return name if authz.is_admin(acc) else None

    def _vacct(request: Request) -> str | None:
        """查看端会话：返回登录账号名（权限运行时再解析）。"""
        return _session_subject(request.cookies.get(VCOOKIE, ""))

    def _vacc_row(request: Request) -> dict | None:
        name = _vacct(request)
        return accounts.find_account(cfg, root, name) if name else None

    def _can_view_main(request: Request) -> bool:
        """整体页/全公司口径：整体权限账号 或 管理员会话。BU 账号不行。"""
        import authz

        if _user(request):
            return True
        acc = _vacc_row(request)
        return authz.can_main(acc)  # 管理员已由 _user 覆盖；此处整体=True、BU=False

    def _can_view_bu(request: Request, bu_name: str) -> bool:
        import authz

        if _user(request):
            return True
        acc = _vacc_row(request)
        if not acc:
            return False
        return authz.can_see_bu(acc, bu_name)

    def _bu_switcher_html(my_names, current: str) -> str:
        """多 BU 账号看 BU 页时顶部的「我的 BU」切换条：**只列该账号绑定且仍存在的 BU**
        （绝不列他 BU，铁律12）。单个绑定不出条。"""
        from urllib.parse import quote

        def esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        existing = [n for n in my_names if n in _state.get("bu_pages", {})]
        if len(existing) <= 1:
            return ""
        links = "".join(
            _BU_NAV_LINK_TPL.format(
                href=quote(n),
                current_attrs=(' aria-current="page" style="border-color:var(--blue)"' if n == current else ""),
                name=esc(n),
            )
            for n in existing
        )
        return _BU_NAV_TPL.format(aria_label="我的 BU 分页", label="我的 BU", links=links)

    def _set_vcookie(resp, account: str):
        """看端会话：写 VCOOKIE，并互清管理员 COOKIE（防双 cookie 串扰）。"""
        acc = accounts.find_account(cfg, root, account)
        tok = auth_session.make_token(sec, account, pw_ver=accounts.password_version_of(acc))
        resp.set_cookie(VCOOKIE, tok, max_age=SESSION_TTL, httponly=True, samesite="lax")
        # path/samesite 必须与 set 一致，否则删不掉
        resp.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax")
        return resp

    def _set_acookie(resp, account: str):
        """管理员会话：写 COOKIE，并互清看端 VCOOKIE（防双 cookie 串扰）。"""
        acc = accounts.find_account(cfg, root, account)
        tok = auth_session.make_token(sec, account, pw_ver=accounts.password_version_of(acc))
        resp.set_cookie(COOKIE, tok, max_age=SESSION_TTL, httponly=True, samesite="lax")
        resp.delete_cookie(VCOOKIE, path="/", httponly=True, samesite="lax")
        return resp

    def _frontend_mode() -> str:
        """KANBAN_FRONTEND=vue|legacy（env > config.frontend > 默认 vue）。
        任务书54.4·C：看端壳已删，/_bu 永远 Vue dist；
        legacy 仅影响管理端 static 回退与 VM HTML 打包对照。
        """
        env = (os.environ.get("KANBAN_FRONTEND") or "").strip().lower()
        if env in ("vue", "legacy"):
            return env
        cfg_fe = str(cfg.get("frontend") or "").strip().lower()
        if cfg_fe in ("vue", "legacy"):
            return cfg_fe
        root_dir = Path(__file__).resolve().parents[1]
        if (root_dir / "frontend" / "dist" / "index.html").is_file():
            return "vue"
        return "vue"

    def _vue_index():
        """Vue SPA 入口（frontend/dist/index.html）。"""
        # 相对 create_app 所在包：ROOT/frontend/dist
        root_dir = Path(__file__).resolve().parents[1]
        p = root_dir / "frontend" / "dist" / "index.html"
        if not p.is_file():
            # 禁止在 py 内嵌 HTML 标签（test_no_html_in_py）；用纯文本 503
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse(
                "Vue frontend not built. Run scripts/build_frontend.sh",
                status_code=503,
            )
        return _file_html_doc(p)

    def _main_shell():
        """整体页：仅 Vue dist（54.4·C 删看端 legacy 壳；与 frontend_mode 无关）。"""
        return _vue_index()

    def _bu_shell():
        """BU 页：仅 Vue dist。"""
        return _vue_index()

    # 批次3：路由纯搬家到 routes.register_all（行为零变化）
    from types import SimpleNamespace
    from routes import register_all
    import export_png as _export_png

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
            start_refresh_async=start_refresh_async,
            recompute=recompute,
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

    # 任务书46·2：openapi 仅管理员会话可见
    @app.get("/openapi.json", include_in_schema=False)
    def openapi_admin_only(request: Request):
        if not _user(request):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="仅管理员可查看 OpenAPI")
        return app.openapi()

    @app.get("/docs", include_in_schema=False)
    def docs_admin_only(request: Request):
        if not _user(request):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="仅管理员可查看 API 文档")
        from fastapi.openapi.docs import get_swagger_ui_html

        return get_swagger_ui_html(openapi_url="/openapi.json", title="看板 API")

    return app


import export_png as _export_png

_screenshot_png = _export_png.screenshot_png


def serve(cfg=None, root=None):
    cfg = cfg or loaders.load_config()
    try:
        from app_logging import setup_logging

        setup_logging(cfg, root)
    except Exception:
        pass
    print("[server] 首次构建页面（跑管道+渲染）……")
    try:
        refresh(cfg, root)
        print(f"[server] 就绪 built_at={_state['built_at']}")
    except Exception as e:  # 数据有问题也让服务起来、页面提示
        print(f"[server] ⚠ 构建失败：{type(e).__name__}: {e}（服务仍启动，修数据后 /api/refresh 或重启）")
    app = create_app(cfg, root)
    import uvicorn

    host = resolve_server_host(cfg)
    # 环境变量 KANBAN_PORT 可覆盖端口（本机多会话调试时避开 config 固定端口，不影响部署默认值）
    port = int(os.environ.get("KANBAN_PORT") or cfg.get("server_port", 8018))
    static_on = resolve_serve_static(cfg)
    mode = "直连(挂static)" if static_on else "反代后端(无static挂载)"
    print(f"[server] 内网服务 host={host} port={port} 模式={mode}")
    print(f"[server] 用户端 http://{host if host not in ('0.0.0.0', '::') else '<本机IP>'}:{port}/   管理员 /admin")

    # 看门狗回滚配套：正常起服务 N 秒后清掉「更新回滚点」标记 = 确认这版没崩、无需回滚。
    # （若这版更新后启动即崩，进程活不到清标记，看门狗见标记仍在→自动回滚上一版本。）
    def _confirm_update_good():
        time.sleep(20)
        try:
            import updater

            updater.clear_rollback_marker(loaders.ROOT)
        except Exception as e:
            # 看门狗标记清理失败不挡服务；下次更新仍可重试。记一行便于排障。
            print(f"[server] clear_rollback_marker 跳过：{type(e).__name__}: {e}")

    threading.Thread(target=_confirm_update_good, daemon=True).start()

    # 任务书60：进程内定时刷新（只在 serve 启动；禁止挂 create_app）
    try:
        from schedule_loop import start_schedule_loop

        start_schedule_loop(cfg, root, start_refresh_async)
    except Exception as e:
        print(f"[server] schedule_loop 启动失败：{type(e).__name__}: {e}")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()
