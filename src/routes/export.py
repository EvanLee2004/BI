"""导出 PNG 与历史快照 — 从 server.create_app 纯搬家。"""

from __future__ import annotations

import re
import time
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response

import db
import loaders
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

    @app.get("/export.png")
    def api_export_png(request: Request, blk: str = ""):
        """导出=当前所选周期的整页 PNG（服务端 Playwright 截图）。v7.8 起要求整体页/管理员会话。
        任务书65·L2：HTML 按需装配（不依赖刷新预装 user_html）。"""
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        if not _state.get("summary") and not (_state.get("user_html") or "").strip():
            raise HTTPException(status_code=503, detail="页面尚未构建，稍后再试")
        keys = set(((_state.get("summary") or {}).get("periods") or {}).keys())
        if blk and keys and blk not in keys:
            raise HTTPException(status_code=400, detail="未知周期")
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

    @app.get("/bu/{name}/export.png")
    def api_bu_export_png(name: str, request: Request, blk: str = ""):
        """BU 页导出：按需装配该 BU HTML 后截图（65·L2）。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=401, detail="请先登录看板")
        keys = set(((_state.get("summary") or {}).get("periods") or {}).keys())
        if blk and keys and blk not in keys:
            raise HTTPException(status_code=400, detail="未知周期")
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

    @app.get("/api/history")
    def api_history(request: Request):
        """历史页面快照列表（按天，倒序）。供管理员端「历史快照」页。"""
        _require(request)
        bdir = loaders.data_dir(cfg, root) / "备份"
        out = []
        for p in sorted(bdir.glob("页面_*.html"), reverse=True):
            d = p.stem.split("_")[1]
            out.append(
                {
                    "day": d,
                    "label": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                    "saved_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
                    "kb": round(p.stat().st_size / 1024),
                }
            )
        return out

    @app.get("/api/history/{day}")
    def api_history_page(request: Request, day: str):
        """回看某天的看板页面（当天最后一次更新的原样快照）。"""
        _require(request)
        if not re.fullmatch(r"\d{8}", day):
            raise HTTPException(status_code=400, detail="日期格式须为 YYYYMMDD")
        p = loaders.data_dir(cfg, root) / "备份" / f"页面_{day}.html"
        if not p.exists():
            raise HTTPException(status_code=404, detail="该日无页面快照")
        return _html_doc(p.read_text(encoding="utf-8"))
