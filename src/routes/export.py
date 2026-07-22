"""导出 PNG/HTML 与历史快照 — 从 server.create_app 纯搬家。

2.2.7：历史 = vm JSON + Vue 只读；导出主路径 = HTML（Vue 皮）；PNG 兼容保留。
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

    def _stub_vm(summary, *, bu_name: str = "") -> dict:
        meta = (summary or {}).get("meta") or {}
        out = {
            "year_key": meta.get("year_key") or "",
            "period_keys": list((summary or {}).get("periods") or {}),
            "kpi": {"cards_by_period": {}},
        }
        if bu_name:
            out["bu_name"] = bu_name
        return out

    def _resolve_export_vm(bu_name: str | None) -> tuple[dict, str, str, str]:
        """返回 (vm, scope, label_bu, page_path)。"""
        import viewmodels

        if bu_name:
            page = _state.get("bu_pages", {}).get(bu_name)
            if not page:
                raise HTTPException(status_code=404, detail="Not Found")
            summary = page.get("summary") if isinstance(page, dict) else None
            try:
                vm = viewmodels.build_bu_vm(bu_name, summary, cfg).model_dump() if summary else {}
            except Exception:
                vm = _stub_vm(summary, bu_name=bu_name)
            return vm, "BU", bu_name, f"/bu/{quote(bu_name)}"
        summary = _state.get("summary")
        try:
            vm = viewmodels.build_cockpit_vm(summary, cfg).model_dump() if summary else {}
        except Exception:
            vm = _stub_vm(summary)
        return vm, "整体", "", "/"

    def _export_html_body(request: Request, *, bu_name: str | None, blk: str) -> Response:
        """共用 HTML 导出：鉴权由调用方完成。"""
        if not _state.get("summary") and not (_state.get("user_html") or "").strip():
            if not _state.get("has_data") and not _state.get("summary"):
                raise HTTPException(status_code=503, detail="页面尚未构建，稍后再试")
        _check_blk(blk)
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一份导出，请稍候几秒再点")
        try:
            from export_html import build_export_html

            vm, scope, label_bu, page_path = _resolve_export_vm(bu_name)
            base = str(request.base_url).rstrip("/")
            q = f"?blk={quote(blk)}" if blk else ""
            try:
                html, _mode = build_export_html(
                    page_url=f"{base}{page_path}{q}",
                    cookie_header=request.headers.get("cookie") or "",
                    blk=blk,
                    vm=vm,
                    scope=scope,
                    bu_name=label_bu,
                    version=_version(),
                    root=root,
                    prefer_playwright=True,
                )
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=503,
                    detail=f"导出失败（{type(e).__name__}）；部署机需 playwright install chromium 或稍后重试",
                ) from e
        except HTTPException:
            raise
        finally:
            _EXPORT_LOCK.release()

        period_label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")
        stem = f"甲骨易智能经营罗盘_{label_bu}_{period_label}" if label_bu else f"甲骨易智能经营罗盘_{period_label}"
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

        fn = quote(f"甲骨易智能经营罗盘_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
        return Response(
            content=png,
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}", "X-Filename": fn},
        )

    @app.get("/export.html")
    @app.get("/api/export.html")
    def api_export_html(request: Request, blk: str = ""):
        """2.2.7：整体页导出 HTML（Vue 皮 + 权限与 export.png 一致）。

        双路径：`/export.html`（计划主路径）+ `/api/export.html`（现网 nginx 已反代 /api，
        在 sites-available 尚未 reload 含 export.html 时前端可走此口，避免落 SPA）。
        """
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        return _export_html_body(request, bu_name=None, blk=blk)

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

        fn = quote(f"甲骨易智能经营罗盘_{name}_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
        return Response(
            content=png,
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}", "X-Filename": fn},
        )

    @app.get("/bu/{name}/export.html")
    def api_bu_export_html(name: str, request: Request, blk: str = ""):
        """2.2.7：BU 页导出 HTML。未知 BU 404；无权 401。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=401, detail="请先登录看板")
        return _export_html_body(request, bu_name=name, blk=blk)

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
