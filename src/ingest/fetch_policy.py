# -*- coding: utf-8 -*-
"""抓数失败分类、短退避与 48h 数据新鲜度（3.7.4 纯逻辑，可单测）。

产品决策：
- 取消「连败 3 次 → 24h 停抓」长冷却；临时错误用有限短退避，下一定时槽可恢复。
- 明确账号/密码/权限错误 → 提示人工检查凭据，仍不长时间停抓。
- 有 ≤48h 最近成功副本 → 展示可看、管理端非阻断轻提示；过时/无副本/完整性失败 → 红。
"""

from __future__ import annotations

import re
from typing import Any

ERROR_KIND_TEMPORARY = "temporary"
ERROR_KIND_CREDENTIAL = "credential"

# 默认短退避 5 分钟（秒）；可被 cfg zhiyun_login_short_backoff_seconds 覆盖
DEFAULT_SHORT_BACKOFF_SECONDS = 300.0
# 成功副本视为「仍新鲜」的最大年龄（小时）
DEFAULT_FRESH_MAX_HOURS = 48.0

_CRED_MARKERS = (
    "password",
    "passwd",
    "密码",
    "账号或密码",
    "用户名或密码",
    "wrong password",
    "invalid password",
    "invalid credential",
    "凭据",
    "权限不足",
    "无权限",
    "没有权限",
    "forbidden",
    "unauthorized",
    "认证失败",
    "鉴权失败",
    "账号被禁用",
    "用户不存在",
)
_TEMP_MARKERS = (
    "timeout",
    "timed out",
    "time-out",
    "connection",
    "connect",
    "network",
    "连接",
    "超时",
    "unreachable",
    "refused",
    "reset",
    "temporary",
    "temporarily",
    "502",
    "503",
    "504",
    "500",
    "bad gateway",
    "service unavailable",
    "gateway",
    "ssl",
    "dns",
    "broken pipe",
    "token",
    "session expired",
    "登录状态",
    "重新登录",
    "请重新登录",
)


def classify_fetch_error(err: Any) -> str:
    """将登录/抓数错误分为 temporary | credential。

    默认 temporary（利于自动恢复）；仅明确凭据/权限文案才判 credential。
    临时网络错误不得累计为凭据失败。
    """
    if err is None:
        return ERROR_KIND_TEMPORARY
    if isinstance(err, BaseException):
        text = f"{type(err).__name__}: {err}"
    else:
        text = str(err)
    low = text.lower()
    # 凭据优先（避免「登录失败」被 timeout 类噪声淹没时误伤）
    for m in _CRED_MARKERS:
        if m.lower() in low or m in text:
            return ERROR_KIND_CREDENTIAL
    # HTTP 5xx
    if re.search(r"\b5\d\d\b", text):
        return ERROR_KIND_TEMPORARY
    for m in _TEMP_MARKERS:
        if m.lower() in low or m in text:
            return ERROR_KIND_TEMPORARY
    # Connection/Timeout 类异常名
    name = type(err).__name__.lower() if isinstance(err, BaseException) else ""
    if any(x in name for x in ("timeout", "connection", "network", "ssl", "http")):
        return ERROR_KIND_TEMPORARY
    return ERROR_KIND_TEMPORARY


def short_backoff_seconds(cfg: dict | None = None) -> float:
    cfg = cfg or {}
    raw = cfg.get("zhiyun_login_short_backoff_seconds")
    if raw is None:
        # 兼容旧键：若仍配 cooldown_hours，强制压到短退避上限 15min，禁止 24h
        hours = cfg.get("zhiyun_login_cooldown_hours")
        if hours is not None:
            try:
                sec = float(hours) * 3600.0
                return max(30.0, min(sec, 900.0))
            except (TypeError, ValueError):
                pass
        return DEFAULT_SHORT_BACKOFF_SECONDS
    try:
        return max(30.0, min(float(raw), 900.0))
    except (TypeError, ValueError):
        return DEFAULT_SHORT_BACKOFF_SECONDS


def max_failures(cfg: dict | None = None) -> int:
    cfg = cfg or {}
    try:
        n = int(cfg.get("zhiyun_login_max_failures", 3) or 3)
    except (TypeError, ValueError):
        n = 3
    return max(1, n)


def next_backoff_state(
    prev: dict | None,
    err: Any,
    *,
    cfg: dict | None = None,
    now_ts: float | None = None,
) -> dict:
    """根据上次状态与本次错误，计算新的短退避状态（纯函数，不写盘）。

    返回字段：
      fails / temp_fails / cred_fails / last_error / error_kind /
      needs_credential_check / until_ts / active / backoff_kind
    """
    import time

    now = float(now_ts if now_ts is not None else time.time())
    st = dict(prev or {})
    kind = classify_fetch_error(err)
    max_f = max_failures(cfg)
    short_s = short_backoff_seconds(cfg)
    temp_fails = int(st.get("temp_fails") or 0)
    cred_fails = int(st.get("cred_fails") or 0)
    needs_cred = bool(st.get("needs_credential_check"))

    if kind == ERROR_KIND_CREDENTIAL:
        cred_fails += 1
        needs_cred = True
    else:
        temp_fails += 1
        # 临时错误绝不升级 needs_credential_check

    total = temp_fails + cred_fails
    out: dict[str, Any] = {
        "fails": total,
        "temp_fails": temp_fails,
        "cred_fails": cred_fails,
        "last_error": str(err)[:200],
        "error_kind": kind,
        "needs_credential_check": needs_cred,
        "until_ts": float(st.get("until_ts") or 0),
        "active": False,
        "backoff_kind": "short",
    }
    # 任一类达阈 → 仅短退避（绝无 24h）
    if (kind == ERROR_KIND_TEMPORARY and temp_fails >= max_f) or (
        kind == ERROR_KIND_CREDENTIAL and cred_fails >= max_f
    ):
        out["until_ts"] = now + short_s
        out["active"] = True
    elif float(st.get("until_ts") or 0) > now:
        out["active"] = True
        out["until_ts"] = float(st.get("until_ts") or 0)
    return out


def is_backoff_active(state: dict | None, *, now_ts: float | None = None) -> bool:
    import time

    if not state:
        return False
    now = float(now_ts if now_ts is not None else time.time())
    until = float(state.get("until_ts") or 0)
    return bool(until and now < until)


def classify_source_data_state(
    *,
    fetch_ok: bool,
    last_success_ts: float | None = None,
    now_ts: float | None = None,
    max_fresh_hours: float = DEFAULT_FRESH_MAX_HOURS,
    has_local_copy: bool = False,
    integrity_ok: bool = True,
    zero_rows_blocking: bool = False,
    missing_columns: bool = False,
    below_min_rows: bool = False,
) -> dict[str, Any]:
    """健康三态：ok / fetch_failed_using_fresh / unsafe|stale。

    - fetch_ok：本次抓取成功
    - fetch_failed_using_fresh：本次失败但有 ≤max_fresh_hours 成功副本 → 非阻断
    - stale_or_missing：无副本或过期 → 红/阻断
    - unsafe：完整性/0 行/缺列/低于 min_rows → 红/阻断
    """
    import time

    now = float(now_ts if now_ts is not None else time.time())
    if (
        not integrity_ok
        or missing_columns
        or below_min_rows
        or zero_rows_blocking
    ):
        return {
            "state": "unsafe",
            "blocking": True,
            "viewer_ok": False,
            "admin_level": "red",
            "message": "数据不安全（缺列/过少行/完整性失败/阻断性 0 行）",
            "age_hours": None,
        }
    if fetch_ok:
        return {
            "state": "ok",
            "blocking": False,
            "viewer_ok": True,
            "admin_level": "ok",
            "message": "本次抓取成功",
            "age_hours": 0.0,
        }
    age_h: float | None = None
    if last_success_ts is not None:
        try:
            age_h = max(0.0, (now - float(last_success_ts)) / 3600.0)
        except (TypeError, ValueError):
            age_h = None
    if (
        has_local_copy
        and last_success_ts is not None
        and age_h is not None
        and age_h <= float(max_fresh_hours)
    ):
        return {
            "state": "fetch_failed_using_fresh",
            "blocking": False,
            "viewer_ok": True,
            "admin_level": "info",
            "message": "本次抓取失败，正在使用仍新鲜的最后成功数据",
            "age_hours": age_h,
        }
    if not has_local_copy or last_success_ts is None:
        return {
            "state": "stale_or_missing",
            "blocking": True,
            "viewer_ok": False,
            "admin_level": "red",
            "message": "无可用成功副本，数据不可安全展示",
            "age_hours": age_h,
        }
    return {
        "state": "stale_or_missing",
        "blocking": True,
        "viewer_ok": False,
        "admin_level": "red",
        "message": f"最后成功数据已超过 {max_fresh_hours:g} 小时，不可静默沿用",
        "age_hours": age_h,
    }
