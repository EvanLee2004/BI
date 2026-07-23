"""导出 PNG/HTML 与历史快照 — 从 server.create_app 纯搬家。

2.2.7：历史 = vm JSON + Vue 只读；导出主路径 = HTML。
2.2.9：导出 = 方案 A 自包含静态可交互快照（kanban_snapshot + Vue 播放器）；
       禁止 Playwright/残壳 fallback 假成功；PNG 与 /?archive= 保留。
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

    def _export_html_body(
        request: Request, *, bu_name: str | None, blk: str, theme: str = ""
    ) -> Response:
        """2.2.9：方案 A 快照导出；鉴权由调用方完成。2.3.0：theme 白名单。"""
        if not _state.get("summary") and not (_state.get("user_html") or "").strip():
            if not _state.get("has_data") and not _state.get("summary"):
                raise HTTPException(status_code=503, detail="页面尚未构建，稍后再试")
        _check_blk(blk)
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一份导出，请稍候几秒再点")
        try:
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
            # 静态断言：成功体不得是残壳
            if "data-export-fallback" in html and "data-export-fallback=\"1\"" in html:
                raise HTTPException(status_code=503, detail="导出拒绝残壳 fallback")
            if "kanban_snapshot" not in html and "__KANBAN_SNAPSHOT__" not in html:
                raise HTTPException(status_code=503, detail="导出体缺少快照标记")
        except HTTPException:
            raise
        finally:
            _EXPORT_LOCK.release()

        period_label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")
        stem = f"甲骨易经营看板_{label_bu}_{period_label}" if label_bu else f"甲骨易经营看板_{period_label}"
        fn = quote(f"{stem}_{time.strftime('%Y%m%d_%H%M')}.html")
        return Response(
            content=html.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}", "X-Filename": fn},
        )

    @app.get("/export.png")
    def api_export_png(request: Request, blk: str = ""):
        """导出=当前所选周期的整页 PNG（服务端 Playwright 截图）。v7.8 起要求整体页/管理员会话。
        任务书65·L2：HTML 按需装配（不依赖刷新预装 user_html）。兼容保留；前端主路径改 .html。"""
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        if not _state.get("summary") and not (_state.get("user_html") or "").strip():
            raise HTTPException(status_code=503, detail="页面尚未构建，稍后再试")
        _check_blk(blk)
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一张导出图，请稍候几秒再点")
        try:
            from refresh_pipeline import assemble_export_html

            try:
                html = assemble_export_html(cfg, bu_name=None)
            except ValueError as e:
                raise HTTPException(status_code=503, detail=str(e) or "页面尚未构建") from e
            png = _screenshot_png(html, blk)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 chromium 未装/超时等
            raise HTTPException(
                status_code=503, detail=f"截图失败（{type(e).__name__}）；部署机需先 playwright install chromium"
            ) from e
        finally:
            _EXPORT_LOCK.release()
        label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")

        fn = quote(f"甲骨易经营看板_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
        return Response(
            content=png,
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}", "X-Filename": fn},
        )

    @app.get("/export.html")
    @app.get("/api/export.html")
    def api_export_html(request: Request, blk: str = "", theme: str = ""):
        """2.2.9：整体页导出静态可交互快照 HTML。

        双路径：`/export.html`（计划主路径）+ `/api/export.html`（现网 nginx 已反代 /api）。
        2.3.0：?theme=neon|dark|light。
        """
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        return _export_html_body(request, bu_name=None, blk=blk, theme=theme)

    @app.get("/bu/{name}/export.png")
    def api_bu_export_png(name: str, request: Request, blk: str = ""):
        """BU 页导出：按需装配该 BU HTML 后截图（65·L2）。兼容保留。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=401, detail="请先登录看板")
        _check_blk(blk)
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一张导出图，请稍候几秒再点")
        try:
            from refresh_pipeline import assemble_export_html

            try:
                # 若测试注入了 page.html 则优先
                html = page.get("html") if isinstance(page, dict) else None
                if not html:
                    html = assemble_export_html(cfg, bu_name=name)
            except ValueError as e:
                raise HTTPException(status_code=503, detail=str(e) or "该 BU 尚无数据") from e
            png = _screenshot_png(html, blk)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"截图失败（{type(e).__name__}）；部署机需先 playwright install chromium"
            ) from e
        finally:
            _EXPORT_LOCK.release()
        label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")

        fn = quote(f"甲骨易经营看板_{name}_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
        return Response(
            content=png,
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}", "X-Filename": fn},
        )

    @app.get("/bu/{name}/export.html")
    def api_bu_export_html(name: str, request: Request, blk: str = "", theme: str = ""):
        """2.2.9：BU 页导出快照 HTML。未知 BU 404；无权 401。包内仅本 BU。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=401, detail="请先登录看板")
        return _export_html_body(request, bu_name=name, blk=blk, theme=theme)

    @app.get("/api/history")
    def api_history(request: Request):
        """历史 VM 存档列表（按天，倒序）。供管理员端「历史快照」页。2.2.7 起读 vm_*.json。"""
        _require(request)
        from ingest import archive

        return archive.list_vm_archives(cfg, root)

    @app.get("/api/history/{day}/vm")
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

    @app.get("/api/history/{day}")
    def api_history_page(request: Request, day: str):
        """旧 HTML 快照接口：2.2.7 起返回 410，请用 /api/history/{day}/vm + Vue 打开。"""
        _require(request)
        if not re.fullmatch(r"\d{8}", day):
            raise HTTPException(status_code=400, detail="日期格式须为 YYYYMMDD")
        raise HTTPException(
            status_code=410,
            detail="历史页面 HTML 快照已停用；请使用管理端「打开」走 Vue 存档（/?archive=YYYYMMDD）",
        )
