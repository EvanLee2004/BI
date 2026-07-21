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


def _bu_nav_meta(cfg, root, pages: dict | None) -> dict:
    """54.11 R-01：BU 导航元信息——配置条数 + 有配置但无分页时的可见提示（防静默）。"""
    import bu as _bu

    pages = pages or {}
    bucfg = _bu.load_bu_config(cfg, root)
    n_cfg = len(bucfg["bus"]) if bucfg else 0
    hint = ""
    if n_cfg > 0 and not pages:
        hint = (
            f"已配置 {n_cfg} 个业务 BU，但当前尚未生成 BU 分页（入口暂不可用）。"
            "请管理员在管理端点「更新数据」后刷新本页。"
        )
    return {"bu_config_count": n_cfg, "bu_nav_hint": hint}


def _empty_bu_views() -> dict:
    return {"year_key": "", "period_keys": [], "rankings_view": {}, "scope": "BU"}


def _ensure_bu_fragments(name: str, page: dict, cfg) -> tuple[dict, dict]:
    """冷启动或补全 BU 碎片/views；就地写回 page。返回 (fr, views)。"""
    summary = page.get("summary")
    fr = page.get("fragments")
    views = page.get("views")
    if not fr:
        if not summary:
            raise HTTPException(status_code=503, detail="该 BU 尚无碎片快照")
        logo = ""
        try:
            logo = assets.load_logo_base64(cfg) or ""
        except OSError as e:
            print(f"[cockpit] BU logo 加载失败：{e}")
            logo = ""
        fr_full = render.build_bu_dashboard_fragments(name, summary, cfg, logo)
        fr = api_v1.client_strip_fragments(fr_full)
        views = api_v1.build_bu_cockpit_views(name, summary, cfg)
        page["fragments"] = fr
        page["views"] = views
        return fr, views
    fr = api_v1.client_strip_fragments(fr)
    if not views:
        if summary and (summary.get("meta") or {}).get("year_key"):
            try:
                views = api_v1.build_bu_cockpit_views(name, summary, cfg)
                page["views"] = views
            except Exception as e:
                print(f"[cockpit] build_bu_cockpit_views 失败：{type(e).__name__}: {e}")
                views = _empty_bu_views()
        else:
            views = _empty_bu_views()
    return fr, views or _empty_bu_views()


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

    @app.get("/api/v1/cockpit")
    def api_v1_cockpit(request: Request):
        """整体驾驶舱 JSON（数字与 golden 全等；前端/飞书等复用）。"""
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_main(request):
            raise HTTPException(status_code=403, detail="无整体驾驶舱权限")
        summary = _state.get("summary")
        # 2.2.4·G：无 summary 返回友好空态（保留登录鉴权；非死门 503）
        if not summary:
            return {
                "scope": "整体",
                "empty": True,
                "empty_message": "暂无数据：请配置数据源后在管理端点「更新数据」，或等待定时刷新。可先浏览界面空态。",
                "meta": {"built_at": _state.get("built_at") or ""},
                "periods": {},
            }
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
        # 2.2.4·G：无 summary → 友好空态 VM（看端可进，不挡登录后页面）
        if not summary:
            out = {
                "scope": "整体",
                "empty": True,
                "empty_message": "暂无数据：请配置数据源后在管理端点「更新数据」，或等待定时刷新。",
                "year_key": "",
                "period_keys": [],
                "kpi": {"cards_by_period": {}},
                "bu_names": [],
                "bu_nav_label": "业务 BU 分页",
                "bu_nav_hint": "数据尚未生成，请管理员更新数据。",
                "bu_config_count": 0,
            }
            out.update(_bu_nav_meta(cfg, root, {}))
            return JSONResponse(out)
        vm = viewmodels.build_cockpit_vm(summary, cfg)
        out = vm.model_dump()
        # 整体页「业务 BU 分页」入口（与 fragments chrome_prefix 同源名单）
        pages = _state.get("bu_pages") or {}
        out["bu_names"] = list(pages.keys())
        # 54.11 R-01：有 BU 配置但未生成分页时勿静默（管理员/整体可见提示）
        out.update(_bu_nav_meta(cfg, root, pages))
        return JSONResponse(out)

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
        # 2.2.4·G：BU 无 summary → 友好空态（非死门 503）
        if not summary:
            out = {
                "scope": "bu",
                "current_bu": name,
                "empty": True,
                "empty_message": "该 BU 暂无数据快照：请管理员在管理端点「更新数据」。",
                "year_key": "",
                "period_keys": [],
                "kpi": {"cards_by_period": {}},
                "bu_names": list((_state.get("bu_pages") or {}).keys()),
                "bu_nav_label": "业务 BU 分页",
            }
            out.update(_bu_nav_meta(cfg, root, _state.get("bu_pages") or {}))
            return JSONResponse(out)
        vm = viewmodels.build_bu_vm(name, summary, cfg)
        out = vm.model_dump()
        # 多 BU 账号：可切换的本账号可见 BU（在已发布 bu_pages 内）
        pages = _state.get("bu_pages") or {}
        vacc = _vacc_row(request)
        if _user(request):
            out["bu_names"] = list(pages.keys())
            out["bu_nav_label"] = "业务 BU 分页"
        elif vacc and accounts.is_main(vacc):
            out["bu_names"] = list(pages.keys())
            out["bu_nav_label"] = "业务 BU 分页"
        else:
            my = accounts.bu_names_of(vacc) if vacc else []
            existing = [n for n in my if n in pages]
            out["bu_names"] = existing
            out["bu_nav_label"] = "我的 BU"
        out["current_bu"] = name
        out.update(_bu_nav_meta(cfg, root, pages))
        return JSONResponse(out)

    @app.get("/api/v1/vm/ledger")
    def api_v1_vm_ledger(
        request: Request,
        page: int = 1,
        page_size: int = 50,
        month_from: str | None = None,
        month_to: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        filters: str | None = None,
        bu: str | None = None,
        q: str | None = None,
        show_all: int = 0,
    ):
        """任务书50·B：看端费用明细 VM。
        **任何会话（含管理员）一律白名单列**——管理员也走 view/view_bu，不走管理端全列。
        管理端数据调整仍用 /api/detail（audience=admin）。
        任务书51·B4：鉴权统一 resolve_expense_view_access(force_whitelist=True)。
        任务书56·R-45：默认仅期间费用白名单大类（与图表口径一致）；show_all=1 显示台账全量。
        任务书58·R-50：date_from/date_to 按收单日期日级闭区间（优先看端）；month_from/to 归属月仍兼容。"""
        import authz
        import db
        from domain.expense.chart_whitelist import merge_ledger_caliber_filters

        user = _user(request)
        vacc = _vacc_row(request)
        force_bu, hide_salary, audience = authz.resolve_expense_view_access(
            user,
            vacc,
            bu,
            cfg=cfg,
            force_whitelist=True,
        )

        who = user or _vacct(request) or "?"
        _audit(cfg, root, who, ("访问", "看端明细VM" + (f" bu={force_bu}" if force_bu else "")))
        caliber_all = bool(int(show_all or 0))
        filters_eff = merge_ledger_caliber_filters(filters, cfg, show_all=caliber_all)

        conn = db.connect(cfg, root)
        try:
            try:
                data = db.query_detail(
                    conn,
                    "费用明细",
                    None,
                    q,
                    page,
                    page_size,
                    False,
                    False,
                    year=None,
                    bu=force_bu,
                    filters=filters_eff,
                    hide_salary=hide_salary,
                    audience=audience,
                    month_from=month_from,
                    month_to=month_to,
                    date_from=date_from,
                    date_to=date_to,
                )
            except KeyError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            conn.close()

        cols = list(data.get("columns") or [])
        # 双保险：响应绝不含隐藏列
        forbidden = set(db.VIEW_EXPENSE_HIDDEN)
        cols = [c for c in cols if c not in forbidden]
        rows = []
        for r in data.get("rows") or []:
            if not isinstance(r, dict):
                continue
            rows.append({c: r.get(c, "") for c in cols})
        # 列 kind：看端漏斗 text=多选值；number/date=关键词/区间（防金额分串误导）
        try:
            meta = db.detail_columns_meta("费用明细", audience=audience)
            kind_by = {m["name"]: m["kind"] for m in meta if isinstance(m, dict)}
            column_meta = [{"name": c, "kind": kind_by.get(c, "text")} for c in cols]
        except Exception:
            column_meta = [{"name": c, "kind": "text"} for c in cols]
        # 任务书52·F-6：响应不带 forbidden 元数据（列已裁剪，名单不下发）
        return JSONResponse(
            {
                "columns": cols,
                "column_meta": column_meta,
                "rows": rows,
                "total": data.get("total") or 0,
                "page": data.get("page") or page,
                "page_size": data.get("page_size") or page_size,
                "audience": audience,
                "caliber_mode": "all" if caliber_all else "period_expense",
                "caliber_note": (
                    "台账全量（含成本/非利润表）"
                    if caliber_all
                    else "仅期间费用大类（与上方图表口径一致；已剔成本/非利润表）"
                ),
            }
        )

    @app.get("/api/v1/vm/ledger/values")
    def api_v1_vm_ledger_values(
        request: Request,
        column: str,
        month_from: str | None = None,
        month_to: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        filters: str | None = None,
        bu: str | None = None,
        q: str | None = None,
        show_all: int = 0,
        limit: int = 200,
    ):
        """看端费用明细：列去重可选值（Excel 式多选漏斗）。

        鉴权/白名单/口径与 GET /api/v1/vm/ledger 一致；query_detail_distinct 会排除本列自身 in，避免下拉自锁。
        """
        import authz
        import db
        from domain.expense.chart_whitelist import merge_ledger_caliber_filters

        user = _user(request)
        vacc = _vacc_row(request)
        force_bu, hide_salary, audience = authz.resolve_expense_view_access(
            user,
            vacc,
            bu,
            cfg=cfg,
            force_whitelist=True,
        )
        caliber_all = bool(int(show_all or 0))
        filters_eff = merge_ledger_caliber_filters(filters, cfg, show_all=caliber_all)
        conn = db.connect(cfg, root)
        try:
            try:
                data = db.query_detail_distinct(
                    conn,
                    "费用明细",
                    column,
                    month=None,
                    q=q,
                    year=None,
                    bu=force_bu,
                    filters=filters_eff,
                    hide_salary=hide_salary,
                    limit=limit,
                    audience=audience,
                    month_from=month_from,
                    month_to=month_to,
                    date_from=date_from,
                    date_to=date_to,
                )
            except KeyError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            conn.close()
        return JSONResponse(data)

    @app.get("/api/v1/vm/ledger/export")
    def api_v1_vm_ledger_export(
        request: Request,
        month_from: str | None = None,
        month_to: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        filters: str | None = None,
        bu: str | None = None,
        q: str | None = None,
        show_all: int = 0,
    ):
        """任务书51·B5：看端费用明细导出 xlsx。

        鉴权/audience/列白名单与 GET /api/v1/vm/ledger 完全同一策略（force_whitelist=True）。
        任务书56·R-45：导出跟随当前口径视图（show_all 与列表一致）。
        任务书58·R-50：导出注明收单日期区间 + 口径；参数与列表同源。
        """
        import io

        import authz
        import db
        import openpyxl
        from domain.expense.chart_whitelist import merge_ledger_caliber_filters
        from fastapi.responses import StreamingResponse

        user = _user(request)
        vacc = _vacc_row(request)
        force_bu, hide_salary, audience = authz.resolve_expense_view_access(
            user,
            vacc,
            bu,
            cfg=cfg,
            force_whitelist=True,
        )
        who = user or _vacct(request) or "?"
        _audit(cfg, root, who, ("访问", "看端明细导出" + (f" bu={force_bu}" if force_bu else "")))
        caliber_all = bool(int(show_all or 0))
        filters_eff = merge_ledger_caliber_filters(filters, cfg, show_all=caliber_all)

        conn = db.connect(cfg, root)
        try:
            try:
                data = db.query_detail(
                    conn,
                    "费用明细",
                    None,
                    q,
                    1,
                    5000,
                    False,
                    False,
                    year=None,
                    bu=force_bu,
                    filters=filters_eff,
                    hide_salary=hide_salary,
                    audience=audience,
                    month_from=month_from,
                    month_to=month_to,
                    date_from=date_from,
                    date_to=date_to,
                    max_page_size=5000,
                )
            except KeyError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            conn.close()

        forbidden = set(db.VIEW_EXPENSE_HIDDEN)
        cols = [c for c in (data.get("columns") or []) if c not in forbidden]
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "费用明细"
        # 第 1 行必须是表头（导出契约/白名单测依赖）；口径说明放第 2 张表
        ws.append(list(cols))
        for r in data.get("rows") or []:
            if not isinstance(r, dict):
                continue
            ws.append([r.get(c, "") if r.get(c, "") is not None else "" for c in cols])
        note = (
            "口径：台账全量（含成本/非利润表）"
            if caliber_all
            else "口径：仅期间费用大类（与看板图表一致；已剔成本/非利润表）"
        )
        d0 = (date_from or "").strip()[:10]
        d1 = (date_to or "").strip()[:10]
        range_note = f"{d0 or '（起空）'} ~ {d1 or '（止空）'}" if (d0 or d1) else "（未限定收单日期）"
        if not (d0 or d1) and (month_from or month_to):
            range_note = f"归属月 {(month_from or '').strip()} ~ {(month_to or '').strip()}"
        ws_note = wb.create_sheet("口径说明", 1)
        ws_note.append(["导出口径"])
        ws_note.append([note])
        ws_note.append(["show_all", "1" if caliber_all else "0"])
        ws_note.append(["收单日期区间", range_note])
        ws_note.append(["date_from", d0 or ""])
        ws_note.append(["date_to", d1 or ""])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        # Content-Disposition 头必须 latin-1；中文名用 filename* (RFC 5987)
        from urllib.parse import quote

        ascii_name = "expense_ledger_all.xlsx" if caliber_all else "expense_ledger_period.xlsx"
        utf8_name = "费用明细_台账全量.xlsx" if caliber_all else "费用明细_期间费用.xlsx"
        cd = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(utf8_name)}"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": cd},
        )

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
        fr, views = _ensure_bu_fragments(name, page, cfg)
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
