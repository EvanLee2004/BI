"""手填/预算/分摊校验辅助（2.6.1 R7 从 manual 拆出，语义零变更）。"""
from __future__ import annotations

from fastapi import HTTPException

import db
import profit

def _parse_money_yuan(v) -> float:
    """手填/预算金额：Decimal(str) 解析，返回元 float（db 层再 yuan_to_fen）。"""
    import money as _money

    d = _money.parse_decimal(v)
    if d is None:
        raise ValueError("空金额")
    return float(d)


def _parse_alloc_ratios_payload(ratios: dict, known: set) -> dict[str, float | None]:
    import money as _money

    vals: dict[str, float | None] = {}
    for b, v in ratios.items():
        b = str(b).strip()
        if b not in known:
            raise HTTPException(status_code=400, detail=f"未知 BU：{b}（以设置页 BU 名单为准）")
        if v is None or v == "":
            vals[b] = None
            continue
        try:
            fv = _money.quantize_rate(v, places=1)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"比例须为数字：{b}") from None
        if not (0 <= fv <= 100):
            raise HTTPException(status_code=400, detail=f"比例须在 0~100：{b}")
        vals[b] = fv
    return vals


def _parse_month_ym(month: str) -> tuple[int, int]:
    try:
        y, m = int(month[:4]), int(month[5:7])
        assert 1 <= m <= 12 and month[4] == "-"
        return y, m
    except (ValueError, AssertionError, IndexError):
        raise HTTPException(status_code=400, detail="归属月格式须为 YYYY-MM") from None


def _ledger_public_fine_amounts(cfg, conn, year: int, month: int) -> dict[str, dict]:
    """公共池台账明细 → {name: {amount_fen, cat, source}}。"""
    import datetime as _dt
    import columns as _columns

    by_fine: dict[str, dict] = {}
    lh, lr = db.load_ledger(cfg, conn)
    if not lh:
        return by_fine
    lcols = _columns.resolve_ledger_columns(lh)
    public_rows = profit.filter_ledger_rows_by_pc(lh, lr, {"公共"})
    start = _dt.date(year, month, 1)
    end = (
        _dt.date(year, month + 1, 1) - _dt.timedelta(days=1)
        if month < 12
        else _dt.date(year, 12, 31)
    )
    fine_by_cat = profit.compute_expenses_by_fine_type(
        public_rows, year, start, end, cfg, lcols
    )
    for cat, pairs in (fine_by_cat or {}).items():
        for fine, amt in pairs or []:
            name = str(fine or "").strip()
            if not name:
                continue
            fen = float(amt or 0)
            if name in by_fine:
                by_fine[name]["amount_fen"] = round(by_fine[name]["amount_fen"] + fen, 2)
            else:
                by_fine[name] = {
                    "amount_fen": round(fen, 2),
                    "cat": str(cat),
                    "source": "auto",
                }
    return by_fine


def _merge_overrides_into_fine(
    by_fine: dict[str, dict],
    overrides: dict[str, int],
    editable: set[str],
    cat_map: dict[str, str],
) -> None:
    """就地合并金额覆盖与可填空项。"""
    for name in set(list(by_fine.keys()) + list(overrides.keys()) + list(editable)):
        ov = overrides.get(name)
        if ov is not None:
            cat = (by_fine.get(name) or {}).get("cat") or cat_map.get(name, "固定运营费用")
            by_fine[name] = {
                "amount_fen": float(int(ov)),
                "cat": str(cat),
                "source": "override",
            }
        elif name not in by_fine and name in editable:
            by_fine[name] = {
                "amount_fen": 0.0,
                "cat": str(cat_map.get(name, "固定运营费用")),
                "source": "auto",
            }


def _item_amount_yuan(conn, month: str, cat: str, rows_lookup: list[dict]) -> float | None:
    import money as _money

    ov = db.get_public_detail_amount_overrides(conn, month).get(cat)
    if ov is not None:
        return float(_money.fen_to_yuan(int(ov)))
    for row in rows_lookup:
        if row.get("category") == cat:
            return float(row.get("amount_yuan") or 0)
    return None


def _clear_detail_rules(conn, month: str, cat: str, user: str) -> None:
    existing = db.get_alloc_detail_rules(conn, month).get(cat) or {}
    for b in list(existing.keys()):
        db.set_alloc_detail_rule(conn, month, cat, b, None, None, user)


def _save_detail_rules_for_cat(
    conn, month: str, cat: str, spec, known: set, user: str, rows_lookup: list[dict]
) -> None:
    """写/清一条明细精配；超额 → HTTP 400。"""
    if spec is None or spec == "" or spec == {}:
        _clear_detail_rules(conn, month, cat, user)
        return
    if not isinstance(spec, dict):
        raise HTTPException(status_code=400, detail=f"detail_rules[{cat}] 格式错误")
    mode = spec.get("mode")
    values = spec.get("values") or {}
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail=f"detail_rules[{cat}].values 须为对象")
    rules_for_item = {
        str(b): {"mode": mode, "value": v}
        for b, v in values.items()
        if v is not None and v != ""
    }
    try:
        db.validate_alloc_detail_item_rules(
            rules_for_item, item_amount_yuan=_item_amount_yuan(conn, month, cat, rows_lookup)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    existing = db.get_alloc_detail_rules(conn, month).get(cat) or {}
    for b in set(list(existing.keys()) + list(values.keys())):
        if b not in known:
            raise HTTPException(status_code=400, detail=f"未知 BU：{b}")
        v = values.get(b)
        try:
            db.set_alloc_detail_rule(
                conn,
                month,
                cat,
                b,
                None if v is None or v == "" else mode,
                None if v is None or v == "" else v,
                user,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e


def _merge_alloc_month(conn, month: str, known: set, vals: dict[str, float | None]) -> dict:
    """合并基准=该月生效比例（含沿用值）；返回合并后的 {BU:比例}。"""
    merged, _src = db.effective_alloc_month(conn, month)
    merged = {b: p for b, p in merged.items() if b in known}
    for b, v in vals.items():
        if v is None:
            merged.pop(b, None)
        else:
            merged[b] = v
    total = sum(p for b, p in merged.items() if b in known)
    if total > 100.05:
        raise HTTPException(
            status_code=400,
            detail=f"该月各 BU 比例合计 {total:g}% 超过 100%，请调整（可以小于 100%，剩余留公司层）",
        )
    return merged


def _prepare_manual_batch_items(items: list, names: set, default_scope: str) -> list[tuple[str, float, str]]:
    """F-02 校验手填批量行 → [(项目, 金额, 范围), ...]。"""
    prepared: list[tuple[str, float, str]] = []
    for it in items:
        item = (it or {}).get("项目", "")
        if item not in names:
            raise HTTPException(status_code=400, detail=f"未知手填项目：{item}")
        try:
            金额 = _parse_money_yuan((it or {}).get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"金额须为数字：{item}") from None
        sc = str((it or {}).get("范围") or default_scope).strip() or "全公司"
        prepared.append((item, 金额, sc))
    return prepared


def _prepare_budget_batch_items(items: list) -> list[tuple[str, str, float, str]]:
    """F-02 校验预算批量行 → [(年份, 指标, 金额, 范围), ...]。"""
    prepared: list[tuple[str, str, float, str]] = []
    for it in items:
        it = it or {}
        metric = it.get("指标", "")
        if metric not in db.BUDGET_METRICS:
            raise HTTPException(status_code=400, detail=f"未知预算指标：{metric}")
        year = str(it.get("年份", "")).strip()
        if not (year.isdigit() and len(year) == 4):
            raise HTTPException(status_code=400, detail="年份须为4位数字")
        try:
            金额 = _parse_money_yuan(it.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"金额须为数字：{metric}") from None
        scope = str(it.get("范围", "全公司")).strip() or "全公司"
        if metric == "费用年预算" and scope == "全公司":
            raise HTTPException(status_code=400, detail="费用年预算须指定部门（范围）")
        if ("毛利率" in metric or "利润率" in metric) and (金额 < 0 or 金额 > 100):
            raise HTTPException(status_code=400, detail=f"比率类目标须为 0~100：{metric}")
        prepared.append((year, metric, 金额, scope))
    return prepared


