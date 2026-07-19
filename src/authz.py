#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·阶段1：RBAC 雏形——能力点枚举 + 角色映射。

行为（54.12 R-01 起）：
- 管理员：CAN_ADMIN + CAN_EXPORT（工资大类全端隐藏，不再授予 CAN_VIEW_SALARY）
- 整体：CAN_EXPORT（工资并入「其他」，无开关）
- BU：CAN_EXPORT（工资并入「其他」，与整体一致）

散落的 is_admin / can_main 判断收敛到本模块（accounts 仍保留 is_* 兼容别名）。
"""

from __future__ import annotations

from typing import Any

import accounts

CAN_EXPORT = "CAN_EXPORT"
CAN_VIEW_SALARY = "CAN_VIEW_SALARY"
CAN_ADMIN = "CAN_ADMIN"

ALL_CAPS = frozenset({CAN_EXPORT, CAN_VIEW_SALARY, CAN_ADMIN})

# 静态角色矩阵（不含配置联动的 VIEW_SALARY）
_ROLE_BASE: dict[str, frozenset[str]] = {
    accounts.PERM_ADMIN: frozenset({CAN_EXPORT, CAN_ADMIN}),
    accounts.PERM_MAIN: frozenset({CAN_EXPORT}),
    accounts.PERM_BU: frozenset({CAN_EXPORT}),
}


def role_key(acc: dict | None) -> str | None:
    """归一角色：管理员 / 整体 / BU（旧「权限=单个BU名」也归为 BU）。"""
    if not acc:
        return None
    if accounts.is_admin(acc):
        return accounts.PERM_ADMIN
    if accounts.is_main(acc):
        return accounts.PERM_MAIN
    if accounts.bu_names_of(acc):
        return accounts.PERM_BU
    # 权限字段是未知 BU 名也视作 BU 角色（可见列表可能空）
    perm = accounts.role_of(acc)
    if perm and perm not in (accounts.PERM_ADMIN, accounts.PERM_MAIN):
        return accounts.PERM_BU
    return None


def caps_of(acc: dict | None, *, cfg: dict | None = None) -> frozenset[str]:
    """账号能力点集合。cfg 保留参数兼容旧调用；54.12 起不再因配置授予 CAN_VIEW_SALARY。"""
    rk = role_key(acc)
    if not rk:
        return frozenset()
    return frozenset(_ROLE_BASE.get(rk) or ())


def has_cap(acc: dict | None, cap: str, *, cfg: dict | None = None) -> bool:
    return cap in caps_of(acc, cfg=cfg)


def is_admin(acc: dict | None) -> bool:
    """等价 accounts.is_admin（收敛入口）。"""
    return has_cap(acc, CAN_ADMIN)


def can_export(acc: dict | None, *, cfg: dict | None = None) -> bool:
    return has_cap(acc, CAN_EXPORT, cfg=cfg)


def can_view_salary(acc: dict | None, *, cfg: dict | None = None) -> bool:
    return has_cap(acc, CAN_VIEW_SALARY, cfg=cfg)


def can_main(acc: dict | None) -> bool:
    """能看整体页：管理员或整体权限。"""
    return accounts.is_admin(acc) or accounts.is_main(acc)


def can_see_bu(acc: dict | None, name: str) -> bool:
    """能看指定 BU：管理员/整体/绑定名单内。"""
    if accounts.is_admin(acc) or accounts.is_main(acc):
        return True
    return accounts.can_see_bu(acc, name)


def resolve_expense_view_access(  # noqa: C901
    user: str | None,
    vacc: dict | None,
    bu: str | None,
    *,
    cfg: dict | None,
    force_whitelist: bool,
    table: str = "费用明细",
) -> tuple[str | None, bool, str]:
    """明细鉴权统一策略（任务书51·B4）。

    返回 (force_bu, hide_salary, audience)。

    - force_whitelist=False：/api/detail 路径——管理员 audience=admin 全列；
      看端仅费用明细，整体 view / BU view_bu。
    - force_whitelist=True：/api/v1/vm/ledger 路径——**任何会话（含管理员）一律白名单**，
      管理员也走 view/view_bu，不走 admin 全列。

    抛 HTTPException 语义由调用方映射；本函数抛 ValueError 带 code/detail。
    """
    from fastapi import HTTPException

    cfg = cfg or {}
    bu_s = (bu or "").strip() or None

    if force_whitelist:
        # 看端 ledger：强制白名单列；54.12 R-01 全端隐工资
        if not user and not vacc:
            raise HTTPException(status_code=401, detail="未登录")
        if user:
            force_bu = bu_s
            audience = "view_bu" if force_bu else "view"
            return force_bu, True, audience
        if accounts.is_main(vacc):
            return bu_s, True, "view"
        names = accounts.bu_names_of(vacc) if vacc else []
        if not names:
            raise HTTPException(status_code=403, detail="无权查看费用明细")
        want = bu_s or (names[0] if len(names) == 1 else "")
        if not want or not accounts.can_see_bu(vacc, want):
            raise HTTPException(status_code=403, detail="无权查看该 BU 费用明细")
        return want, True, "view_bu"

    # /api/detail：管理员全列但仍隐工资；看端仅费用明细
    if user:
        return bu_s, True, "admin"
    if vacc and table == "费用明细":
        names = accounts.bu_names_of(vacc)
        if accounts.is_main(vacc):
            return bu_s, True, "view"
        if not names:
            raise HTTPException(status_code=403, detail="无权查看费用明细")
        want = bu_s or (names[0] if len(names) == 1 else "")
        if not want or not accounts.can_see_bu(vacc, want):
            raise HTTPException(status_code=403, detail="无权查看该 BU 费用明细")
        return want, True, "view_bu"
    raise HTTPException(status_code=401, detail="需要登录")


def role_matrix_for_tests() -> dict[str, dict[str, bool]]:
    """三角色 × 三能力点矩阵（54.12 起无人有 CAN_VIEW_SALARY），供 test_authz 断言。"""
    rows = {
        accounts.PERM_ADMIN: {"账号": "a", "权限": accounts.PERM_ADMIN},
        accounts.PERM_MAIN: {"账号": "m", "权限": accounts.PERM_MAIN},
        accounts.PERM_BU: {"账号": "b", "权限": accounts.PERM_BU, "可见BU": ["甲BU"]},
    }
    out: dict[str, dict[str, bool]] = {}
    for name, acc in rows.items():
        caps = caps_of(acc, cfg={})
        out[name] = {c: (c in caps) for c in (CAN_EXPORT, CAN_VIEW_SALARY, CAN_ADMIN)}
    return out


def assert_legacy_parity(acc: dict | None) -> dict[str, Any]:
    """自检：authz 与 accounts 旧判断一致（调试用）。"""
    return {
        "is_admin": is_admin(acc) == accounts.is_admin(acc),
        "can_main": can_main(acc) == (accounts.is_admin(acc) or accounts.is_main(acc)),
    }
