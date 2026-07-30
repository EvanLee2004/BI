# -*- coding: utf-8 -*-
"""四层健康契约（3.6.0 G2 / G5 看端差异）。

- system_health：服务/DB/依赖/内存/磁盘/运行时
- source_quality：抓取/文件稳定/未来日期/缺列
- business_completeness：手填/预算/归属等业务待补
- viewer_state：老板看端能否安全展示（中性文案，无英文 yellow 大横幅）
"""

from __future__ import annotations

from typing import Any


def build_layered_health(
    *,
    system: dict[str, Any] | None = None,
    source_quality: dict[str, Any] | None = None,
    business_completeness: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装四层状态；不混成单一 yellow。"""
    sys_l = dict(system or {"level": "ok", "items": []})
    src_l = dict(source_quality or {"level": "ok", "items": []})
    biz_l = dict(business_completeness or {"level": "ok", "items": []})
    view_l = dict(viewer or {})

    # 业务缺月 ≠ 系统故障
    if biz_l.get("level") == "yellow" and sys_l.get("level") == "ok":
        sys_l = {**sys_l, "level": "ok", "note": "business_gaps_do_not_yellow_system"}

    blocking = bool(view_l.get("blocking"))
    # 只有 critical 且数字不安全才 blocking
    if view_l.get("level") == "critical" and view_l.get("numbers_safe") is False:
        blocking = True
    elif view_l.get("level") != "critical":
        blocking = False

    viewer_state = {
        "level": view_l.get("level") or "ok",
        "blocking": blocking,
        "freshness_label": view_l.get("freshness_label") or "数据更新至",
        "freshness_at": view_l.get("freshness_at") or "",
        "integrity_hint": view_l.get("integrity_hint") or "",  # 可展开业务完整性，中性
        "no_technical_yellow_banner": True,
    }
    return {
        "system_health": sys_l,
        "source_quality": src_l,
        "business_completeness": biz_l,
        "viewer_state": viewer_state,
    }


def viewer_blocks_numbers(*, level: str, numbers_safe: bool) -> bool:
    return level == "critical" and numbers_safe is False


def boss_banner_allowed(viewer_state: dict[str, Any]) -> bool:
    """老板看端：禁止技术 yellow 全宽条；仅 critical+blocking 可阻断。"""
    if viewer_state.get("blocking") and viewer_state.get("level") == "critical":
        return True  # 阻断页，不是 yellow 横条
    return False
