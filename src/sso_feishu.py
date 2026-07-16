#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·阶段1：飞书 SSO 适配器骨架。

未配置（缺 app_id / app_secret / redirect_uri）→ 完全禁用，零行为变化。
真实联调凭据待明昊申请；本模块只提供接口形状与 URL 构造。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


# 飞书开放平台 OAuth 端点（文档占位；未配置时不会发起请求）
FEISHU_AUTHORIZE_URL = "https://open.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USERINFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def sso_config(cfg: dict | None) -> dict[str, str]:
    """从 config 读取飞书 SSO 占位凭据。"""
    c = cfg or {}
    block = c.get("feishu_sso") if isinstance(c.get("feishu_sso"), dict) else {}
    return {
        "app_id": str(block.get("app_id") or c.get("feishu_sso_app_id") or "").strip(),
        "app_secret": str(block.get("app_secret") or c.get("feishu_sso_app_secret") or "").strip(),
        "redirect_uri": str(block.get("redirect_uri") or c.get("feishu_sso_redirect_uri") or "").strip(),
    }


def is_enabled(cfg: dict | None) -> bool:
    """三项齐全才启用；否则禁用。"""
    s = sso_config(cfg)
    return bool(s["app_id"] and s["app_secret"] and s["redirect_uri"])


def authorize_url(cfg: dict | None, *, state: str = "") -> str | None:
    """构造飞书授权 URL；未启用 → None。"""
    if not is_enabled(cfg):
        return None
    s = sso_config(cfg)
    q = {
        "app_id": s["app_id"],
        "redirect_uri": s["redirect_uri"],
        "state": state or "kanban",
    }
    return f"{FEISHU_AUTHORIZE_URL}?{urlencode(q)}"


def exchange_token(cfg: dict | None, code: str) -> dict[str, Any] | None:
    """用授权码换 token。骨架：未启用或空 code → None；真实 HTTP 待联调。"""
    if not is_enabled(cfg) or not (code or "").strip():
        return None
    # 联调时：POST FEISHU_TOKEN_URL with app_id/app_secret/code
    raise NotImplementedError("飞书 SSO 换 token 待凭据联调（见 docs/madr/0007_feishu_sso.md）")


def fetch_user_info(cfg: dict | None, access_token: str) -> dict[str, Any] | None:
    """拉飞书用户信息。骨架：未启用 → None。"""
    if not is_enabled(cfg) or not (access_token or "").strip():
        return None
    raise NotImplementedError("飞书 SSO 用户信息待凭据联调")


def map_feishu_user_to_account(cfg: dict | None, root, feishu_user: dict) -> dict | None:
    """飞书用户 → 本系统账号映射接口。
    约定：优先 feishu_open_id / mobile / email 与账号表扩展字段匹配；未实现前恒 None。
    """
    if not is_enabled(cfg) or not feishu_user:
        return None
    # 映射表/字段待产品确认
    return None
