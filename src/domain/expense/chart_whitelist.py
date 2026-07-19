# -*- coding: utf-8 -*-
"""期间费用图（折线 area / 热力）大类白名单（54.15 R-30）。

与期间费用环形图 / 管理利润表同一套「计入期间费用」的大类：
config.expense_categories_included + 显示层并入的「其他」。
台账「成本」「非利润表」等 excluded 类一律不进两图。
禁止在 area 与 heat 两处各写一份白名单——只从此模块取。
"""
from __future__ import annotations

from typing import Iterable


def period_expense_chart_categories(cfg: dict | None, categories: Iterable[str] | None = None) -> list[str]:
    """返回两图可用的大类列表（保持传入顺序；无 categories 时仅返回白名单全集）。"""
    cfg = cfg or {}
    allowed = set(cfg.get("expense_categories_included") or [])
    allowed.add("其他")  # 工资等并入后的显示名
    # 明确剔除（即使误入 included 也不进图）
    ban = {"成本", "非利润表"}
    allowed -= ban
    if categories is None:
        # 稳定顺序：included 原序 + 其他
        out = [c for c in (cfg.get("expense_categories_included") or []) if c in allowed]
        if "其他" in allowed and "其他" not in out:
            out.append("其他")
        return out
    return [c for c in categories if c in allowed]


def filter_expense_monthly_raw_for_charts(raw: dict | None, cfg: dict | None) -> dict:
    """过滤 compute_expense_monthly_by_cat 结果：仅保留白名单大类，并重算各月 total。"""
    raw = dict(raw or {})
    cats = period_expense_chart_categories(cfg, raw.get("categories") or [])
    months_out = []
    for m in raw.get("months") or []:
        by = dict(m.get("by_cat") or {})
        by2 = {k: float(by.get(k) or 0) for k in cats}
        tot = sum(by2.values())
        months_out.append({**m, "by_cat": by2, "total": tot})
    return {
        **raw,
        "categories": cats,
        "months": months_out,
        "chart_whitelist_note": "仅期间费用大类（已剔成本/非利润表）",
    }


def merge_ledger_caliber_filters(filters, cfg: dict | None, *, show_all: bool):
    """看端明细默认口径：仅期间费用白名单大类（与图表一致）。

    show_all=True → 原样返回 filters（台账全量，仍受列白名单/隐工资约束）。
    show_all=False → 在 filters 上叠加 对应报表大类 IN 白名单（与用户筛选项 AND）。
    返回可直接传给 db.query_detail 的 filters（dict 或 JSON 字符串，与入参同型）。
    """
    if show_all:
        return filters
    import json as _json

    cats = period_expense_chart_categories(cfg)
    if not cats:
        return filters
    # parse
    fdict = {}
    if filters:
        if isinstance(filters, str):
            s = filters.strip()
            if s:
                try:
                    raw = _json.loads(s)
                    if isinstance(raw, dict):
                        fdict = dict(raw)
                except (TypeError, ValueError, _json.JSONDecodeError):
                    fdict = {}
        elif isinstance(filters, dict):
            fdict = dict(filters)
    existing = fdict.get("对应报表大类") if isinstance(fdict.get("对应报表大类"), dict) else {}
    # 若用户已 in 筛选，取交集；否则用白名单全集
    user_in = existing.get("in") or existing.get("values")
    if user_in is not None:
        if isinstance(user_in, str):
            user_in = [user_in]
        allowed = set(cats)
        inter = [str(x) for x in user_in if str(x) in allowed]
        fdict["对应报表大类"] = {**existing, "in": inter or ["__no_match__"]}
    else:
        fdict["对应报表大类"] = {**existing, "in": list(cats)}
    # preserve type
    if isinstance(filters, str) or filters is None:
        return _json.dumps(fdict, ensure_ascii=False)
    return fdict
