#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.0：单会话 resolve + 21 天遗留 cookie 兼容。

参考：OWASP Session Management Cheat Sheet（HttpOnly/SameSite、改密使会话失效已由 pw_ver 覆盖）；
MDN Set-Cookie（path 与 delete 一致）。

权限永不写入 cookie 名：角色一律账号表 + authz。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import accounts
import auth_session
import authz
import loaders
from app_state import (
    COOKIE,
    SESSION_LEGACY_COMPAT_DAYS,
    SESSION_LEGACY_COMPAT_SINCE_FILE,
    SESSION_TTL,
    SID_COOKIE,
    VCOOKIE,
)

# 测试可注入「今天」
_today_override: date | None = None


def set_today_override(d: date | None) -> None:
    """单测用：固定「今天」以测兼容窗外。"""
    global _today_override
    _today_override = d


def today() -> date:
    return _today_override if _today_override is not None else date.today()


def compat_since_path(cfg, root=None) -> Path:
    return loaders.data_dir(cfg, root) / SESSION_LEGACY_COMPAT_SINCE_FILE


def ensure_compat_since(cfg, root=None, *, since: date | None = None) -> date:
    """读或写入兼容锚点日（默认今天）。上机首次 2.6.0 应落到生产日。"""
    p = compat_since_path(cfg, root)
    if p.is_file():
        try:
            raw = p.read_text(encoding="utf-8").strip().split()[0]
            return date.fromisoformat(raw[:10])
        except (ValueError, OSError, IndexError):
            pass
    d = since or today()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(d.isoformat() + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return d


def compat_until(cfg, root=None) -> date:
    since = ensure_compat_since(cfg, root)
    return since + timedelta(days=SESSION_LEGACY_COMPAT_DAYS)


def legacy_compat_active(cfg, root=None, *, on: date | None = None) -> bool:
    """on < since+21 天（含 since 当天起算 21 个自然日的窗口）。

    窗口定义：自 since 日起共 SESSION_LEGACY_COMPAT_DAYS 天可读旧 cookie；
    即 on ∈ [since, since+DAYS) 时 active（第 0 天～第 20 天 = 21 天）。
    若需含第 21 天整天，用 on <= since+DAYS-1 等价 on < since+DAYS。
    """
    on = on or today()
    since = ensure_compat_since(cfg, root)
    return on < since + timedelta(days=SESSION_LEGACY_COMPAT_DAYS)


@dataclass(frozen=True)
class AccountContext:
    account: str
    row: dict
    is_admin: bool
    source: str  # sid | legacy_session | legacy_view
    needs_upgrade: bool

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
    on: date | None = None,
) -> AccountContext | None:
    """唯一身份解析。cookies 为 request.cookies 或 dict。

    顺序：sid →（窗内）legacy session → legacy view。
    新旧并存：只认 sid。两旧并存：优先 session。
    """
    def get(name: str) -> str:
        try:
            return str(cookies.get(name) or "")
        except Exception:
            return ""

    sid = get(SID_COOKIE)
    if sid:
        hit = _subject_from_token(sec, sid, cfg, root)
        if hit:
            name, acc = hit
            return AccountContext(
                account=name,
                row=acc,
                is_admin=authz.is_admin(acc),
                source="sid",
                needs_upgrade=False,
            )

    if not legacy_compat_active(cfg, root, on=on):
        return None

    leg_s = get(COOKIE)
    leg_v = get(VCOOKIE)
    if leg_s:
        hit = _subject_from_token(sec, leg_s, cfg, root)
        if hit:
            name, acc = hit
            return AccountContext(
                account=name,
                row=acc,
                is_admin=authz.is_admin(acc),
                source="legacy_session",
                needs_upgrade=True,
            )
    if leg_v:
        hit = _subject_from_token(sec, leg_v, cfg, root)
        if hit:
            name, acc = hit
            return AccountContext(
                account=name,
                row=acc,
                is_admin=authz.is_admin(acc),
                source="legacy_view",
                needs_upgrade=True,
            )
    return None


def apply_sid_cookie(resp, *, sec: dict, cfg, root, account: str):
    """登录/升级：只写 kanban_sid，删两旧名。"""
    acc = accounts.find_account(cfg, root, account)
    tok = auth_session.make_token(sec, account, pw_ver=accounts.password_version_of(acc))
    resp.set_cookie(
        SID_COOKIE,
        tok,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        path="/",
    )
    clear_legacy_cookies(resp)
    # 再清一次 sid 以外的旧名（clear 已含）
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
