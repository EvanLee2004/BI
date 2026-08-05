#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.7.1：单会话 resolve 仅 kanban_sid（无旧 cookie 读、无 21 天窗）。

2.7.1 铁律：
- 生产 **单 worker**（`_state` 进程内缓存；多 worker 未支持）。
- 身份解析**只认** `kanban_sid`；`kanban_session`/`kanban_view` 不再维持登录。
- 登录/升级写 sid 并 **delete** 旧 cookie 名；退出清 sid + 两旧名。
- 用户须重登一次（旧 cookie 无法续会话）。

参考：OWASP Session Management；MDN Set-Cookie（path 与 delete 一致）。
权限永不写入 cookie 名：角色一律账号表 + authz。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import accounts
import auth_session
import authz
from app_state import (
    COOKIE,
    SESSION_TTL,
    SID_COOKIE,
    VCOOKIE,
)

# 测试可注入「今天」（保留 API，兼容旧测桩）
_today_override: date | None = None


def set_today_override(d: date | None) -> None:
    """单测用：固定「今天」。"""
    global _today_override
    _today_override = d


def today() -> date:
    return _today_override if _today_override is not None else date.today()


@dataclass(frozen=True)
class AccountContext:
    account: str
    row: dict
    is_admin: bool
    source: str  # sid only (2.7.1)
    needs_upgrade: bool  # 恒 False；保留字段兼容调用方

    @property
    def can_main(self) -> bool:
        return authz.can_main(self.row) or self.is_admin

    def can_see_bu(self, bu_name: str) -> bool:
        if self.is_admin:
            return True
        return authz.can_see_bu(self.row, bu_name)


def _subject_from_token(sec: dict, token: str, cfg, root) -> tuple[str, dict] | None:
    raw = auth_session.check_token_raw(sec, token or "")
    if not raw:
        return None
    name, tok_ver = raw
    acc = accounts.find_account(cfg, root, name)
    if not acc:
        return None
    if tok_ver != accounts.password_version_of(acc):
        return None
    return name, acc


def resolve_session(
    cookies: dict[str, str] | Any,
    *,
    sec: dict,
    cfg,
    root=None,
    on: date | None = None,  # noqa: ARG001 — 保留签名兼容
) -> AccountContext | None:
    """唯一身份解析。cookies 为 request.cookies 或 dict。

    2.7.1：只认 kanban_sid；忽略 legacy cookie。
    """

    def get(name: str) -> str:
        try:
            return str(cookies.get(name) or "")
        except Exception:
            return ""

    sid = get(SID_COOKIE)
    if not sid:
        return None
    hit = _subject_from_token(sec, sid, cfg, root)
    if not hit:
        return None
    name, acc = hit
    return AccountContext(
        account=name,
        row=acc,
        is_admin=authz.is_admin(acc),
        source="sid",
        needs_upgrade=False,
    )


def apply_sid_cookie(resp, *, sec: dict, cfg, root, account: str, secure: bool = False):
    """登录：只写 kanban_sid，删两旧名。

    ``secure`` 仅在 HTTPS / 可信转发 https 时为 True（3.7.14 AUDIT-003）；
    纯 HTTP 内网必须 False。
    """
    acc = accounts.find_account(cfg, root, account)
    tok = auth_session.make_token(sec, account, pw_ver=accounts.password_version_of(acc))
    resp.set_cookie(
        SID_COOKIE,
        tok,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        path="/",
        secure=bool(secure),
    )
    clear_legacy_cookies(resp)
    return resp


def clear_all_session_cookies(resp):
    """退出：清 sid + 两旧名。"""
    for name in (SID_COOKIE, COOKIE, VCOOKIE):
        resp.delete_cookie(name, path="/", httponly=True, samesite="lax")
    return resp


def clear_legacy_cookies(resp):
    for name in (COOKIE, VCOOKIE):
        resp.delete_cookie(name, path="/", httponly=True, samesite="lax")
    return resp


def require_login(ctx: AccountContext | None) -> AccountContext:
    from fastapi import HTTPException

    if not ctx:
        raise HTTPException(status_code=401, detail="未登录")
    return ctx


def require_admin(ctx: AccountContext | None) -> AccountContext:
    from fastapi import HTTPException

    ctx = require_login(ctx)
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return ctx


def require_main(ctx: AccountContext | None) -> AccountContext:
    from fastapi import HTTPException

    ctx = require_login(ctx)
    if not ctx.can_main:
        raise HTTPException(status_code=403, detail="无整体看板权限")
    return ctx


def require_bu(ctx: AccountContext | None, bu_name: str) -> AccountContext:
    from fastapi import HTTPException

    ctx = require_login(ctx)
    if not ctx.can_see_bu(bu_name):
        raise HTTPException(status_code=403, detail="无权查看该业务线")
    return ctx
