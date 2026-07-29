"""导出 PNG/HTML 与历史快照 — 从 server.create_app 纯搬家。

2.2.7：历史 = vm JSON + Vue 只读；导出主路径 = HTML。
2.2.9：导出 = 方案 A 自包含静态可交互快照（kanban_snapshot + Vue 播放器）；
       禁止 Playwright/残壳 fallback 假成功；PNG 与 /?archive= 保留。
2.7.8 G3：PNG 与 HTML 共用同一 kanban_snapshot pack→HTML 串；禁整页 HTML 装运 PNG / 旧 assemble 导出。
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

import db
from app_state import _state, _EXPORT_LOCK


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

    # 截图走 server._screenshot_png（请求时解析，便于测试打桩 server._screenshot_png）
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN

    def _screenshot_png(html, blk="", width=1440):
        from routes._srv import srv

        return srv()._screenshot_png(html, blk, width=width)

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    def _conn():
        return db.connect(cfg, root)

    def _period_keys():
        return set(((_state.get("summary") or {}).get("periods") or {}).keys())

    def _check_blk(blk: str) -> None:
        keys = _period_keys()
        if blk and keys and blk not in keys:
            raise HTTPException(status_code=400, detail="未知周期")

    def _version() -> str:
        try:
            from version import read_version

            return read_version()
        except Exception:
            return ""

    def _ready_for_export() -> None:
        if not _state.get("summary") and not (_state.get("user_html") or "").strip():
            if not _state.get("has_data") and not _state.get("summary"):
                raise HTTPException(status_code=503, detail="页面尚未构建，稍后再试")

    def _build_snapshot_html(*, bu_name: str | None, blk: str, theme: str = "") -> str:
        """2.7.8：HTML 与 PNG 唯一 HTML 源 — pack → build_export_html（kanban_snapshot）。"""
        from export_html import assemble_export_pack, build_export_html

        scope = "BU" if bu_name else "整体"
        label_bu = bu_name or ""
        try:
            pack = assemble_export_pack(
                scope=scope,
                bu_name=label_bu,
                blk=blk,
                version=_version(),
                state=_state,
                cfg=cfg,
                theme=theme,
            )
            html, _mode = build_export_html(
                blk=blk,
                scope=scope,
                bu_name=label_bu,
                version=_version(),
                root=root,
                pack=pack,
                prefer_playwright=False,
            )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=503,
                detail=f"导出快照失败（{type(e).__name__}: {e}）；请确认 frontend/dist-snapshot 已构建",
            ) from e
        if "data-export-fallback" in html and 'data-export-fallback="1"' in html:
            raise HTTPException(status_code=503, detail="导出拒绝残壳 fallback")
        if "kanban_snapshot" not in html and "__KANBAN_SNAPSHOT__" not in html:
            raise HTTPException(status_code=503, detail="导出体缺少快照标记")
        return html

    def _export_html_body(
        request: Request, *, bu_name: str | None, blk: str, theme: str = ""
    ) -> Response:
        """2.2.9 / 2.7.8：方案 A 快照 HTML；与 PNG 同源 _build_snapshot_html。"""
        _ready_for_export()
        _check_blk(blk)
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一份导出，请稍候几秒再点")
        try:
            html = _build_snapshot_html(bu_name=bu_name, blk=blk, theme=theme)
        except HTTPException:
            raise
        finally:
            _EXPORT_LOCK.release()

        label_bu = bu_name or ""
        period_label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")
        stem = f"甲骨易经营看板_{label_bu}_{period_label}" if label_bu else f"甲骨易经营看板_{period_label}"
        fn = quote(f"{stem}_{time.strftime('%Y%m%d_%H%M')}.html")
        return Response(
            content=html.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}", "X-Filename": fn},
        )

    def _export_png_body(*, bu_name: str | None, blk: str) -> Response:
        """2.7.8：PNG = Playwright 截同款 kanban_snapshot HTML（与 export.html 同源）。"""
        _ready_for_export()
        _check_blk(blk)
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一张导出图，请稍候几秒再点")
        try:
            html = _build_snapshot_html(bu_name=bu_name, blk=blk, theme="")
            try:
                png = _screenshot_png(html, blk)
            except Exception as e:  # noqa: BLE001 chromium 未装/超时等
                raise HTTPException(
                    status_code=503,
                    detail=f"截图失败（{type(e).__name__}）；部署机需先 playwright install chromium",
                ) from e
        except HTTPException:
            raise
        finally:
            _EXPORT_LOCK.release()

        label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")
        if bu_name:
            fn = quote(f"甲骨易经营看板_{bu_name}_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
        else:
            fn = quote(f"甲骨易经营看板_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
        return Response(
            content=png,
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}", "X-Filename": fn},
        )

    @app.get("/api/v1/export.png")
    def api_export_png(request: Request, blk: str = ""):
        """2.7.8：整体页 PNG = 截 kanban_snapshot HTML（与 /api/v1/export.html 同源）。"""
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        return _export_png_body(bu_name=None, blk=blk)

    @app.get("/api/v1/export.html")
    def api_export_html(request: Request, blk: str = "", theme: str = ""):
        """2.2.9 / 2.7.2：整体页导出静态可交互快照 HTML（仅 `/api/v1/export.html`）。
        2.3.0：?theme=neon|dark|light。
        """
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        return _export_html_body(request, bu_name=None, blk=blk, theme=theme)

    @app.get("/api/v1/export/bu/{name}/png")
    def api_bu_export_png(name: str, request: Request, blk: str = ""):
        """2.7.8：BU PNG = 截同源 kanban_snapshot HTML。2.6.3·D3 先鉴权。"""
        if not _can_view_bu(request, name):
            # 无权/未登录：与「不存在」对无权者同形 401（不先 404 泄露）
            raise HTTPException(status_code=401, detail="请先登录看板")
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        return _export_png_body(bu_name=name, blk=blk)

    @app.get("/api/v1/export/bu/{name}/html")
    def api_bu_export_html(name: str, request: Request, blk: str = "", theme: str = ""):
        """2.2.9 / 2.7.2：BU 页导出快照 HTML（仅 v1）。2.6.3·D3：先鉴权；无权一律 401（不先 404）；有权再 404。"""
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=401, detail="请先登录看板")
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        return _export_html_body(request, bu_name=name, blk=blk, theme=theme)

    @app.get("/api/v1/history")
    def api_history(request: Request):
        """历史 VM 存档列表（按天，倒序）。供管理员端「历史快照」页。2.2.7 起读 vm_*.json。"""
        _require(request)
        from ingest import archive

        return archive.list_vm_archives(cfg, root)

    @app.get("/api/v1/history/{day}/vm")
    def api_history_vm(request: Request, day: str):
        """某日归档 VM（管理员可读）；供 Vue `/?archive=YYYYMMDD` 只读加载。"""
        _require(request)
        if not re.fullmatch(r"\d{8}", day):
            raise HTTPException(status_code=400, detail="日期格式须为 YYYYMMDD")
        from ingest import archive

        data = archive.load_vm_archive(cfg, day, root)
        if not data:
            raise HTTPException(status_code=404, detail="该日无 VM 存档")
        return JSONResponse(data)

    @app.get("/api/v1/history/{day}")
    def api_history_page(request: Request, day: str):
        """旧 HTML 快照接口：2.2.7 起返回 410，请用 /api/v1/history/{day}/vm + Vue 打开。"""
        _require(request)
        if not re.fullmatch(r"\d{8}", day):
            raise HTTPException(status_code=400, detail="日期格式须为 YYYYMMDD")
        raise HTTPException(
            status_code=410,
            detail="历史页面 HTML 快照已停用；请使用管理端「打开」走 Vue 存档（/?archive=YYYYMMDD）",
        )

    # ---------- 2.3.6：管理利润表 Excel（当前筛选 + 构成明细）----------

    def _pl_xlsx_response(
        request: Request,
        *,
        summary: dict,
        is_bu: bool,
        scope_label: str,
        blk: str,
    ) -> Response:
        """鉴权由调用方完成；校验 blk、组 xlsx、写 Content-Disposition。"""
        if not summary:
            raise HTTPException(status_code=503, detail="页面尚未构建，稍后再试")
        periods = (summary.get("periods") or {}) if isinstance(summary, dict) else {}
        meta = (summary.get("meta") or {}) if isinstance(summary, dict) else {}
        year_key = meta.get("year_key") or ""
        period_key = (blk or "").strip() or str(year_key)
        if not period_key:
            raise HTTPException(status_code=400, detail="未知周期")
        # 未知周期 → 400（与顶栏 export.html 的 _check_blk 语义一致）
        if periods and period_key not in periods:
            raise HTTPException(status_code=400, detail="未知周期")
        from export_pl_xlsx import build_pl_xlsx_bytes, pl_xlsx_filename

        try:
            raw = build_pl_xlsx_bytes(
                summary,
                period_key=period_key,
                is_bu=is_bu,
                scope_label=scope_label,
                version=_version(),
            )
        except KeyError as e:
            raise HTTPException(status_code=400, detail="未知周期") from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=503,
                detail=f"生成管理利润表 Excel 失败（{type(e).__name__}: {e}）",
            ) from e

        who = _user(request) or _vacct(request) or "?"
        _audit(cfg, root, who, ("访问", f"导出管理利润表Excel scope={scope_label} blk={period_key}"))
        fname = pl_xlsx_filename(scope_label=scope_label, period_key=period_key)
        cd = f"attachment; filename=\"export.xlsx\"; filename*=UTF-8''{quote(fname)}"
        return Response(
            content=raw,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": cd, "X-Filename": quote(fname)},
        )

    @app.get("/api/v1/export/pl.xlsx")
    def api_export_pl_xlsx(request: Request, blk: str = ""):
        """2.3.6 / 2.7.2：整体页管理利润表 Excel（跟随 ?blk=；仅 v1）。"""
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="请先登录看板")
        if not _can_view_main(request):
            raise HTTPException(status_code=403, detail="无权导出整体管理利润表")
        summary = _state.get("summary") or {}
        return _pl_xlsx_response(
            request,
            summary=summary if isinstance(summary, dict) else {},
            is_bu=False,
            scope_label="整体",
            blk=blk,
        )

    @app.get("/api/v1/export/bu/{name}/pl.xlsx")
    def api_bu_export_pl_xlsx(name: str, request: Request, blk: str = ""):
        """2.3.6 / 2.7.2：BU 页管理利润表 Excel；summary 与 BU 页 VM 同源（仅 v1）。"""
        # 2.6.7 D-6：先鉴权再判存在（防资源枚举）
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="请先登录看板")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=403, detail="无权查看该 BU")
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        summary = page.get("summary") if isinstance(page, dict) else None
        if not summary:
            raise HTTPException(status_code=503, detail="该 BU 尚无 JSON 快照（请更新数据）")
        return _pl_xlsx_response(
            request,
            summary=summary if isinstance(summary, dict) else {},
            is_bu=True,
            scope_label=name,
            blk=blk,
        )
