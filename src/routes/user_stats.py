"""3.3.0 管理端用户统计 API（只读聚合 manual_配置变更 访问/登录类）。"""

from __future__ import annotations

from fastapi import HTTPException, Query, Request

import accounts
import db


def register(app, d):
    cfg = d.cfg
    root = d.root
    _user = d.user

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    @app.get("/api/v1/admin/user_stats")
    def api_user_stats(
        request: Request,
        days: int = Query(default=30, description="7|30|90|0(全部)"),
    ):
        """用户访问统计摘要：KPI + 按账号/BU/形态 + 日趋势。仅管理员。"""
        _require(request)
        if days not in (0, 7, 30, 90):
            days = 30
        accs = accounts.load_accounts(cfg, root, create=False)
        conn = db.connect(cfg, root)
        try:
            return db.aggregate_user_stats(conn, accs, days=days)
        finally:
            conn.close()

    @app.get("/api/v1/admin/user_stats/events")
    def api_user_stats_events(
        request: Request,
        days: int = Query(default=30),
        action: str | None = Query(default=None),
        account: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ):
        """用户访问明细流水（倒序分页）。仅管理员。"""
        _require(request)
        if days not in (0, 7, 30, 90):
            days = 30
        accs = accounts.load_accounts(cfg, root, create=False)
        conn = db.connect(cfg, root)
        try:
            return db.list_access_events(
                conn,
                accs,
                days=days,
                action=action,
                account=account,
                limit=limit,
                offset=offset,
            )
        finally:
            conn.close()
