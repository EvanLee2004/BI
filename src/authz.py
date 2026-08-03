#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RBAC：账号级能力矩阵（3.7.8）+ 旧 CAN_* 兼容。

细粒度 key（账号字段「能力」object，全可选勾）：
  view_main · admin_access · data_refresh · data_write · manage_accounts
  export_page_html · export_page_png · export_pl_xlsx · export_ledger_xlsx
  export_admin_detail · export_archive

存量缺「能力」：按旧行为物化默认（管理员全开；整体/BU 可看范围 + 全部 export_*=true）。
勾选以「能力」为准覆盖角色默认；总账号 lushasha 强制 admin_access+manage_accounts。

旧 CAN_EXPORT / CAN_ADMIN / CAN_VIEW_SALARY 仍由 caps_of 派生，兼容 test_authz。
"""

from __future__ import annotations

from typing import Any

import accounts

# ---- 细粒度能力（3.7.8 SSOT）----
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


def _legacy_view_main(acc: dict | None) -> bool:
    """升级前 can_main 语义（不读 能力，避免递归）。"""
    if not acc:
        return False
    if accounts.is_admin(acc):
        return True
    flag = acc.get("可看整体页")
    if flag is True:
        return True
    if flag is False:
        return False
    return accounts.is_main(acc)


def default_caps_for_role(acc: dict | None) -> dict[str, bool]:
    """角色默认能力（存量无「能力」字段时的旧行为物化）。

    - 管理员：全开
    - 整体/BU：可看范围 + 全部 export_*=true；无 admin/write/refresh/manage
    """
    out = {k: False for k in FINE_CAP_KEYS}
    rk = role_key(acc)
    if not rk:
        return out
    if rk == accounts.PERM_ADMIN:
        return {k: True for k in FINE_CAP_KEYS}
    # 整体 / BU：导出全开（与现网一致），管理/写/刷关
    for k in _EXPORT_KEYS:
        out[k] = True
    out[CAP_VIEW_MAIN] = _legacy_view_main(acc)
    out[CAP_ADMIN_ACCESS] = False
    out[CAP_DATA_REFRESH] = False
    out[CAP_DATA_WRITE] = False
    out[CAP_MANAGE_ACCOUNTS] = False
    return out


def caps_template(role: str) -> dict[str, bool]:
    """新账号安全默认模板（设置页「应用角色默认」）。

    - 管理员：全开
    - 整体：view_main + 全部 export；无 admin/write/refresh/manage
    - BU：关闭全部 export + 关闭 write/refresh/admin；view_main 关
    """
    r = (role or "").strip()
    out = {k: False for k in FINE_CAP_KEYS}
    if r == accounts.PERM_ADMIN or r == "管理员":
        return {k: True for k in FINE_CAP_KEYS}
    if r == accounts.PERM_MAIN or r == "整体":
        out[CAP_VIEW_MAIN] = True
        for k in _EXPORT_KEYS:
            out[k] = True
        return out
    # BU / 其它：安全默认
    return out


def materialize_caps(acc: dict | None) -> dict[str, bool]:
    """解析账号能力：缺字段 → 角色默认；有「能力」→ 覆盖对应 key。

    总账号强制 admin_access + manage_accounts。
    """
    base = default_caps_for_role(acc)
    if not acc:
        return base
    raw = acc.get("能力")
    if isinstance(raw, dict):
        for k in FINE_CAP_KEYS:
            if k in raw:
                base[k] = bool(raw[k])
    # 总账号不可降到无管理
    if accounts.is_master_account(acc.get("账号")):
        base[CAP_ADMIN_ACCESS] = True
        base[CAP_MANAGE_ACCOUNTS] = True
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
    """能进管理端：admin_access（存量管理员角色默认 True）。"""
    return has_fine_cap(acc, CAP_ADMIN_ACCESS)


def can_export(acc: dict | None, *, cfg: dict | None = None) -> bool:
    return has_fine_cap(acc, CAN_EXPORT, cfg=cfg)


def can_view_salary(acc: dict | None, *, cfg: dict | None = None) -> bool:
    return has_fine_cap(acc, CAN_VIEW_SALARY, cfg=cfg)


def can_main(acc: dict | None) -> bool:
    """能看整体页：view_main 能力（存量默认与旧 can_main 一致）。"""
    return has_fine_cap(acc, CAP_VIEW_MAIN)


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
    """清洗客户端「能力」字段；非法 → None（表示不写，走默认）。"""
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
    """自检：authz 与 accounts 旧判断一致（调试用；存量无能力字段时）。"""
    if acc and isinstance(acc.get("能力"), dict):
        return {"is_admin": True, "can_main": True, "note": "能力字段覆盖，跳过严格 parity"}
    return {
        "is_admin": is_admin(acc) == accounts.is_admin(acc),
        "can_main": can_main(acc)
        == (accounts.is_admin(acc) or accounts.is_main(acc) or bool((acc or {}).get("可看整体页"))),
    }
