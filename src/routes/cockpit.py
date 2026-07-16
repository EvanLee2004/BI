"""看端 fragments / cockpit JSON — 从 server.create_app 纯搬家。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

import accounts
import api_v1
import assets
import render
from app_state import _state


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
    _BU_NAV_TPL = d.BU_NAV_TPL
    _BU_NAV_LINK_TPL = d.BU_NAV_LINK_TPL

    @app.get("/api/v1/cockpit")
    def api_v1_cockpit(request: Request):
        """整体驾驶舱 JSON（数字与 golden 全等；前端/飞书等复用）。"""
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_main(request):
            raise HTTPException(status_code=403, detail="无整体驾驶舱权限")
        summary = _state.get("summary")
        if not summary:
            raise HTTPException(status_code=503, detail="数据尚未生成")
        out = api_v1.cockpit_payload(summary, scope="整体")
        if _state.get("built_at"):
            out.setdefault("meta", {})["built_at"] = _state["built_at"]
        return out

    @app.get("/api/v1/vm/cockpit")
    def api_v1_vm_cockpit(request: Request):
        """任务书46·2：整体页 ViewModel（显示串+SVG；数字与 fragments 同源）。"""
        import viewmodels

        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_main(request):
            raise HTTPException(status_code=403, detail="无整体驾驶舱权限")
        summary = _state.get("summary")
        if not summary:
            raise HTTPException(status_code=503, detail="数据尚未生成")
        vm = viewmodels.build_cockpit_vm(summary, cfg)
        return JSONResponse(vm.model_dump())

    @app.get("/api/v1/vm/bu/{name}")
    def api_v1_vm_bu(name: str, request: Request):
        """任务书46·2：BU 页 ViewModel。"""
        import viewmodels

        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=403, detail="无权查看该 BU")
        page = (_state.get("bu_pages") or {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="BU 不存在或未配置")
        summary = page.get("summary")
        if not summary:
            raise HTTPException(status_code=503, detail="该 BU 尚无 JSON 快照（请更新数据）")
        vm = viewmodels.build_bu_vm(name, summary, cfg)
        return JSONResponse(vm.model_dump())

    @app.get("/api/v1/cockpit/bu/{name}")
    def api_v1_cockpit_bu(name: str, request: Request):
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=403, detail="无权查看该 BU")
        page = (_state.get("bu_pages") or {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="BU 不存在或未配置")
        summary = page.get("summary")
        if not summary:
            # 基准版 bu_pages 仅有 html：现场重算会动 core——此处 503 提示需带 summary 的发布
            raise HTTPException(status_code=503, detail="该 BU 尚无 JSON 快照（请更新数据）")
        return api_v1.cockpit_payload(summary, scope="BU", bu_name=name)

    # B-P5：真删 /api/v1/cockpit/view 与 SERVE_SHELL 直出。user_html 仅缓存供导出 PNG。

    def _main_chrome_prefix(hide_pw: bool = False) -> str:
        """整体页 chrome（BU 入口条 / 隐藏改密），注入点=wrap 前。"""

        def _esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        parts = []
        if hide_pw:
            parts.append(_HIDE_PW_STYLE)
        names = list(_state.get("bu_pages", {}))
        if names:
            links = "".join(_BU_NAV_LINK_TPL.format(href=quote(n), current_attrs="", name=_esc(n)) for n in names)
            parts.append(_BU_NAV_TPL.format(aria_label="BU 分页", label="业务 BU 分页", links=links))
        return "".join(parts)

    def _bu_chrome_prefix(name: str, request: Request) -> str:
        """BU 页 chrome：管理员隐藏改密 + 多 BU 切换条。"""
        parts = []
        if _user(request):
            parts.append(_HIDE_PW_STYLE)
        vacc = _vacc_row(request)
        my = accounts.bu_names_of(vacc) if vacc else []
        if my:
            parts.append(_bu_switcher_html(my, name))
        return "".join(parts)

    @app.get("/api/v1/cockpit/fragments")
    def api_v1_cockpit_fragments(request: Request):
        """B：整体页渲染就绪碎片（shell 组装）。"""
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="请先登录看板")
        if not _can_view_main(request) and not _user(request):
            raise HTTPException(status_code=403, detail="无权限")
        summary = _state.get("summary")
        fr = _state.get("fragments")
        views = _state.get("views")
        if not fr:
            # 冷启动：无 fragments 时一次性建 client-ready
            if not summary:
                raise HTTPException(status_code=503, detail="数据尚未生成")
            logo = ""
            try:
                logo = assets.load_logo_base64(cfg) or ""
            except OSError as e:
                print(f"[cockpit] logo 加载失败：{e}")
                logo = ""
            pack = api_v1.cockpit_fragments(summary, cfg, logo, client=True)
            fr = pack["fragments"]
            views = pack["views"]
            _state["fragments"] = fr
            _state["views"] = views
        else:
            # publish-once / 测试桩：有 fragments 则 strip 幂等；views 优先缓存
            fr = api_v1.client_strip_fragments(fr)
            if not views:
                if summary and (summary.get("meta") or {}).get("year_key"):
                    try:
                        views = api_v1.build_cockpit_views(summary, cfg)
                        _state["views"] = views
                    except Exception as e:
                        # 任务书33·B：不可静默空 views（周期切换会空）。记日志后退化空壳，不 500。
                        print(f"[cockpit] build_cockpit_views 失败：{type(e).__name__}: {e}")
                        views = {"year_key": "", "period_keys": [], "rankings_view": {}}
                else:
                    views = {"year_key": "", "period_keys": [], "rankings_view": {}}
        hide_pw = bool(_user(request))
        return JSONResponse(
            {
                "api_version": "v1",
                "mode": "fragments",
                "fragments": fr,
                "views": views,
                "chrome_prefix": _main_chrome_prefix(hide_pw=hide_pw),
                "data_assembled": "1",
            }
        )

    @app.get("/api/v1/cockpit/bu/{name}/fragments")
    def api_v1_cockpit_bu_fragments(name: str, request: Request):
        """B-P4：BU 页碎片 + views（shell-bu + rankings.js + page.js）。"""
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="请先登录看板")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=403, detail="无权查看该 BU")
        page = (_state.get("bu_pages") or {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="BU 不存在或未配置")
        summary = page.get("summary")
        fr = page.get("fragments")
        views = page.get("views")
        if not fr:
            # 冷启动：BU 专属 views（禁止整体页构建器）
            if not summary:
                raise HTTPException(status_code=503, detail="该 BU 尚无碎片快照")
            logo = ""
            try:
                logo = assets.load_logo_base64(cfg) or ""
            except OSError as e:
                # logo 文件缺失/不可读：页面仍可出，仅无 Logo
                print(f"[cockpit] BU logo 加载失败：{e}")
                logo = ""
            fr_full = render.build_bu_dashboard_fragments(name, summary, cfg, logo)
            fr = api_v1.client_strip_fragments(fr_full)
            views = api_v1.build_bu_cockpit_views(name, summary, cfg)
            page["fragments"] = fr
            page["views"] = views
        else:
            fr = api_v1.client_strip_fragments(fr)
            if not views:
                if summary and (summary.get("meta") or {}).get("year_key"):
                    try:
                        views = api_v1.build_bu_cockpit_views(name, summary, cfg)
                        page["views"] = views
                    except Exception as e:
                        print(f"[cockpit] build_bu_cockpit_views 失败：{type(e).__name__}: {e}")
                        views = {"year_key": "", "period_keys": [], "rankings_view": {}, "scope": "BU"}
                else:
                    views = {"year_key": "", "period_keys": [], "rankings_view": {}, "scope": "BU"}
        if not views:
            views = {"year_key": "", "period_keys": [], "rankings_view": {}, "scope": "BU"}
        return JSONResponse(
            {
                "api_version": "v1",
                "mode": "fragments",
                "scope": "BU",
                "bu_name": name,
                "fragments": fr,
                "views": views,
                "chrome_prefix": _bu_chrome_prefix(name, request),
                "data_assembled": "1",
            }
        )
