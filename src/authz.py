#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RBAC：账号级能力矩阵（3.7.9 收敛）+ 旧 CAN_* 兼容。

3.7.9 产品规则（硬规则，服务端权威）：
- 看什么 → 仅权限角色（管理员 / 整体 / 按 BU）
- 用户可勾能力 → 仅看端四导出（export_page_html/png/pl_xlsx/ledger_xlsx）
- 管理类 + 管端明细导出 + 审计归档 → 仅管理员恒 true；非管理员强制 false（忽略 JSON 脏 true）
- can_main := is_admin OR is_main（忽略 能力.view_main / 旧 可看整体页 对 BU 的放宽）
- is_admin := 角色管理员（禁止「非管理员 + 脏 admin_access」半管理）
- 总账号 lushasha 不可降到无管理（管理员全开已覆盖）

旧 CAN_EXPORT / CAN_ADMIN / CAN_VIEW_SALARY 仍由 caps_of 派生，兼容 test_authz。
"""

from __future__ import annotations

from typing import Any

import accounts

# ---- 细粒度能力（3.7.8 键名保留；3.7.9 语义收敛）----
CAP_VIEW_MAIN = "view_main"
CAP_ADMIN_ACCESS = "admin_access"
CAP_DATA_REFRESH = "data_refresh"
CAP_DATA_WRITE = "data_write"
CAP_MANAGE_ACCOUNTS = "manage_accounts"
CAP_EXPORT_PAGE_HTML = "export_page_html"
CAP_EXPORT_PAGE_PNG = "export_page_png"
CAP_EXPORT_PL_XLSX = "export_pl_xlsx"
CAP_EXPORT_LEDGER_XLSX = "export_ledger_xlsx"
CAP_EXPORT_ADMIN_DETAIL = "export_admin_detail"
CAP_EXPORT_ARCHIVE = "export_archive"

FINE_CAP_KEYS: tuple[str, ...] = (
    CAP_VIEW_MAIN,
    CAP_ADMIN_ACCESS,
    CAP_DATA_REFRESH,
    CAP_DATA_WRITE,
    CAP_MANAGE_ACCOUNTS,
    CAP_EXPORT_PAGE_HTML,
    CAP_EXPORT_PAGE_PNG,
    CAP_EXPORT_PL_XLSX,
    CAP_EXPORT_LEDGER_XLSX,
    CAP_EXPORT_ADMIN_DETAIL,
    CAP_EXPORT_ARCHIVE,
)

# 用户可独立开关的看端四导出（设置页唯一可勾项）
USER_EXPORT_KEYS: tuple[str, ...] = (
    CAP_EXPORT_PAGE_HTML,
    CAP_EXPORT_PAGE_PNG,
    CAP_EXPORT_PL_XLSX,
    CAP_EXPORT_LEDGER_XLSX,
)

# 绑定管理员角色：非管理员 materialize 强制 false
_ADMIN_BOUND_KEYS: tuple[str, ...] = (
    CAP_VIEW_MAIN,
    CAP_ADMIN_ACCESS,
    CAP_DATA_REFRESH,
    CAP_DATA_WRITE,
    CAP_MANAGE_ACCOUNTS,
    CAP_EXPORT_ADMIN_DETAIL,
    CAP_EXPORT_ARCHIVE,
)

# 旧 CAN_EXPORT 派生：任一导出（含管理类导出）
_EXPORT_KEYS: tuple[str, ...] = (
    CAP_EXPORT_PAGE_HTML,
    CAP_EXPORT_PAGE_PNG,
    CAP_EXPORT_PL_XLSX,
    CAP_EXPORT_LEDGER_XLSX,
    CAP_EXPORT_ADMIN_DETAIL,
    CAP_EXPORT_ARCHIVE,
)

# ---- 旧能力点（兼容）----
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


def default_caps_for_role(acc: dict | None) -> dict[str, bool]:
    """角色默认能力（存量无「能力」字段时物化）。

    - 管理员：全开
    - 整体/BU 存量：四看端导出 true（保留 3.7.8 存量可达）；管理类全 false
    """
    out = {k: False for k in FINE_CAP_KEYS}
    rk = role_key(acc)
    if not rk:
        return out
    if rk == accounts.PERM_ADMIN:
        return {k: True for k in FINE_CAP_KEYS}
    # 整体 / BU 存量：仅四看端导出开
    for k in USER_EXPORT_KEYS:
        out[k] = True
    return out


def caps_template(role: str) -> dict[str, bool]:
    """新账号 /「应用角色默认」模板（3.7.9）。

    - 管理员：全开
    - 整体：四导出 true；管理类 false
    - BU：四导出 false；管理类 false
    """
    r = (role or "").strip()
    out = {k: False for k in FINE_CAP_KEYS}
    if r == accounts.PERM_ADMIN or r == "管理员":
        return {k: True for k in FINE_CAP_KEYS}
    if r == accounts.PERM_MAIN or r == "整体":
        for k in USER_EXPORT_KEYS:
            out[k] = True
        return out
    # BU / 其它：安全默认（四导出关）
    return out


def materialize_caps(acc: dict | None) -> dict[str, bool]:
    """解析账号能力（3.7.9 硬规则）。

    - 管理员角色：全部 fine key 恒 true（总号不可降权）
    - 非管理员：仅四导出可读 JSON 覆盖；管理类/view_main/管端导出/归档强制 false
    """
    if not acc:
        return {k: False for k in FINE_CAP_KEYS}
    # 角色管理员：固定最高权限（忽略 JSON 降权）
    if accounts.is_admin(acc):
        return {k: True for k in FINE_CAP_KEYS}
    base = default_caps_for_role(acc)
    raw = acc.get("能力")
    if isinstance(raw, dict):
        for k in USER_EXPORT_KEYS:
            if k in raw:
                base[k] = bool(raw[k])
    for k in _ADMIN_BOUND_KEYS:
        base[k] = False
    return base


def caps_public(acc: dict | None) -> dict[str, bool]:
    """session / API 下发用：全部 fine key → bool。"""
    return materialize_caps(acc)


def has_fine_cap(acc: dict | None, cap: str, *, cfg: dict | None = None) -> bool:
    """细粒度能力判断。cfg 保留兼容。"""
    _ = cfg
    if not cap:
        return False
    # 旧 CAN_* 映射
    if cap == CAN_ADMIN:
        return bool(materialize_caps(acc).get(CAP_ADMIN_ACCESS))
    if cap == CAN_EXPORT:
        m = materialize_caps(acc)
        return any(m.get(k) for k in _EXPORT_KEYS)
    if cap == CAN_VIEW_SALARY:
        return False  # 54.12 R-01
    return bool(materialize_caps(acc).get(cap))


def caps_of(acc: dict | None, *, cfg: dict | None = None) -> frozenset[str]:
    """账号旧能力点集合（CAN_*）。cfg 保留兼容。"""
    _ = cfg
    m = materialize_caps(acc)
    out: set[str] = set()
    if m.get(CAP_ADMIN_ACCESS):
        out.add(CAN_ADMIN)
    if any(m.get(k) for k in _EXPORT_KEYS):
        out.add(CAN_EXPORT)
    # CAN_VIEW_SALARY 永不授予
    return frozenset(out)


def has_cap(acc: dict | None, cap: str, *, cfg: dict | None = None) -> bool:
    """兼容入口：旧 CAN_* 与 fine key 均可。"""
    return has_fine_cap(acc, cap, cfg=cfg)


def is_admin(acc: dict | None) -> bool:
    """能进管理端：3.7.9 以角色管理员为准（与 materialize admin_access 一致）。"""
    return accounts.is_admin(acc)


def can_export(acc: dict | None, *, cfg: dict | None = None) -> bool:
    return has_fine_cap(acc, CAN_EXPORT, cfg=cfg)


def can_view_salary(acc: dict | None, *, cfg: dict | None = None) -> bool:
    return has_fine_cap(acc, CAN_VIEW_SALARY, cfg=cfg)


def can_main(acc: dict | None) -> bool:
    """能看整体页：3.7.9 仅管理员或整体权限（忽略 能力.view_main / 旧 可看整体页）。"""
    return accounts.is_admin(acc) or accounts.is_main(acc)


def can_see_bu(acc: dict | None, name: str) -> bool:
    """能看指定 BU：管理员/整体/绑定名单内。"""
    if is_admin(acc) or accounts.is_main(acc):
        return True
    return accounts.can_see_bu(acc, name)


def require_cap(acc: dict | None, cap: str, *, detail: str | None = None) -> None:
    """无能力 → HTTP 403。供路由闸使用。"""
    from fastapi import HTTPException

    if has_fine_cap(acc, cap):
        return
    raise HTTPException(
        status_code=403,
        detail=detail or f"无权：需要能力 {cap}",
    )


def count_admin_managers(rows: list[dict]) -> int:
    """具备 admin_access + manage_accounts 的账号数。"""
    n = 0
    for a in rows:
        m = materialize_caps(a)
        if m.get(CAP_ADMIN_ACCESS) and m.get(CAP_MANAGE_ACCOUNTS):
            n += 1
    return n


def validate_accounts_caps(rows: list[dict]) -> None:
    """保存前：至少一账号 admin+manage；总账号不可无管理。抛 ValueError。"""
    if not rows:
        raise ValueError("账号表不能为空")
    if count_admin_managers(rows) < 1:
        raise ValueError("至少保留一个具备管理端入口与账号管理能力的账号")
    for a in rows:
        if accounts.is_master_account(a.get("账号")):
            m = materialize_caps(a)
            if not (m.get(CAP_ADMIN_ACCESS) and m.get(CAP_MANAGE_ACCOUNTS)):
                raise ValueError(
                    f"总账号「{accounts.MASTER_ACCOUNT}」不可取消管理端入口或账号管理能力"
                )


def normalize_caps_field(raw) -> dict[str, bool] | None:
    """清洗客户端「能力」字段；非法 → None（表示不写，走默认）。

    3.7.9：仍接受全 fine key 输入，但 materialize 会硬规则覆盖管理类。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    out: dict[str, bool] = {}
    for k in FINE_CAP_KEYS:
        if k in raw:
            out[k] = bool(raw[k])
    return out if out else None


def _bu_view_access(vacc: dict | None, bu_s: str | None) -> tuple[str | None, bool, str]:
    """看端/BU 会话解析 force_bu + audience（一律 hide_salary）。"""
    from fastapi import HTTPException

    if accounts.is_main(vacc):
        return bu_s, True, "view"
    names = accounts.bu_names_of(vacc) if vacc else []
    if not names:
        raise HTTPException(status_code=403, detail="无权查看费用明细")
    want = bu_s or (names[0] if len(names) == 1 else "")
    if not want or not accounts.can_see_bu(vacc, want):
        raise HTTPException(status_code=403, detail="无权查看该 BU 费用明细")
    return want, True, "view_bu"


def resolve_expense_view_access(
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

    - force_whitelist=False：/api/v1/admin/detail 路径——管理员 audience=admin 全列；
      看端仅费用明细，整体 view / BU view_bu。
    - force_whitelist=True：/api/v1/vm/ledger 路径——**任何会话（含管理员）一律白名单**，
      管理员也走 view/view_bu，不走 admin 全列。

    抛 HTTPException 语义由调用方映射；本函数抛 ValueError 带 code/detail。
    """
    from fastapi import HTTPException

    _ = cfg or {}
    bu_s = (bu or "").strip() or None

    if force_whitelist:
        # 看端 ledger：强制白名单列；54.12 R-01 全端隐工资
        if not user and not vacc:
            raise HTTPException(status_code=401, detail="未登录")
        if user:
            return bu_s, True, ("view_bu" if bu_s else "view")
        return _bu_view_access(vacc, bu_s)

    # /api/v1/admin/detail：管理员全列但仍隐工资；看端仅费用明细
    if user:
        return bu_s, True, "admin"
    if vacc and table == "费用明细":
        return _bu_view_access(vacc, bu_s)
    # AUTH-003：已登录但无该明细权限 → 403；未登录 → 401
    if vacc:
        raise HTTPException(status_code=403, detail="无权查看该明细（看端仅费用明细）")
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
    """自检：3.7.9 is_admin/can_main 与 accounts 角色一致。"""
    return {
        "is_admin": is_admin(acc) == accounts.is_admin(acc),
        "can_main": can_main(acc)
        == (accounts.is_admin(acc) or accounts.is_main(acc)),
    }
