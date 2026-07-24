#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.5.0：登录成功后的默认落地页 + next 白名单（open-redirect 防护）。"""
from __future__ import annotations

from urllib.parse import quote, unquote, urlencode

import accounts
import authz


def default_redirect_for_account(acc: dict | None, *, bu_pages: dict | None = None) -> str:
    """管理员→/admin；整体→/；BU→/bu/{第一个仍存在的可见BU}。"""
    if not acc:
        return "/login"
    if authz.is_admin(acc):
        return "/admin"
    if accounts.is_main(acc):
        return "/"
    names = accounts.bu_names_of(acc)
    pages = bu_pages if isinstance(bu_pages, dict) else {}
    existing = [n for n in names if n in pages] if pages else list(names)
    if not existing and names:
        existing = list(names)
    if existing:
        return "/bu/" + quote(str(existing[0]), safe="")
    return "/"


def _is_safe_relative_path(raw: str) -> bool:
    if not raw or not isinstance(raw, str):
        return False
    s = raw.strip()
    if not s.startswith("/") or s.startswith("//"):
        return False
    if "://" in s or "\\" in s or "\n" in s or "\r" in s:
        return False
    return True


def _path_only(s: str) -> str:
    return s.split("?", 1)[0].split("#", 1)[0]


def _bu_name_from_path(path_only: str) -> str | None:
    if not path_only.startswith("/bu/"):
        return None
    rest = path_only[len("/bu/") :]
    if not rest:
        return None
    return unquote(rest.split("/")[0])


def _next_ok_for_admin(path_only: str) -> bool:
    if path_only in ("/", "/login"):
        return True
    if path_only == "/admin" or path_only.startswith("/admin/"):
        return True
    return path_only.startswith("/bu/")


def _next_ok_for_viewer(acc: dict | None, path_only: str) -> bool:
    if path_only == "/":
        return accounts.is_main(acc)
    name = _bu_name_from_path(path_only)
    if name is None:
        return False
    return authz.can_see_bu(acc, name)


def sanitize_next_path(next_raw: str | None, acc: dict | None) -> str | None:
    """校验 next：管理员可 /admin* 与看板；非管理员仅 /（整体）或 /bu/...。非法→None。"""
    if next_raw is None:
        return None
    s = unquote(str(next_raw).strip())
    if not _is_safe_relative_path(s):
        return None
    path_only = _path_only(s)
    if not path_only.startswith("/"):
        return None
    if authz.is_admin(acc):
        if not _next_ok_for_admin(path_only):
            return None
        if path_only == "/login":
            return "/"
        return s
    if path_only == "/admin" or path_only.startswith("/admin/"):
        return None
    if not _next_ok_for_viewer(acc, path_only):
        return None
    return s


def resolve_login_redirect(
    acc: dict | None,
    next_raw: str | None = None,
    *,
    bu_pages: dict | None = None,
) -> str:
    default = default_redirect_for_account(acc, bu_pages=bu_pages)
    nxt = sanitize_next_path(next_raw, acc)
    return nxt or default


def login_url(*, next_path: str | None = None, msg: str | None = None) -> str:
    q: dict[str, str] = {}
    if next_path:
        q["next"] = next_path
    if msg:
        q["msg"] = msg
    if not q:
        return "/login"
    return "/login?" + urlencode(q)
