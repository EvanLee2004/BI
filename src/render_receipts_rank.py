#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 render.py 纯搬家（任务书54.13）；禁止改算法。"""
from __future__ import annotations

import json
import charts
import tpl
from render_shell import (
    DRAWER_HTML,
    PARTICLES_HTML,
    PW_MODAL_HTML,
    RK_MODAL_HTML,
    DAILY_HTML,
)
from render_widgets import (
    _title_version_html,
    _amt,
    render_basic,
    render_period_bar,
    _pv,
    _esc,
)
from render_common import GROUP_COLORS, LED_OF


from render_expense_ui import expense_monthly_from_period_ledgers, apply_expense_salary_hide

def _budget_tag(budget):
    """任务书41·B：回款情况卡头预算小字整行删除（KPI 进度条仍保留 G 钳制）。
    保留函数与调用点，恒返空串，避免其它拼装路径再拼出冗余标签。"""
    return ""

def _receipt_insight_totals(
    tot_o, tot_r, delivered_gross=None, budget=None, show_delivered_unpaid=False, period_label=""
):
    """回款右侧驾驶舱（A3·陆总#2）：①总下单/总回款首行 ②已交付未回款可隐藏
    ③回款占下单 ④年目标进度。金额由调用方传入，本函数只拼 HTML、零运算。
    period_label：任务书37·A4 紧邻标注所属周期，防误读为历史累计。"""
    tot_o = float(tot_o or 0.0)
    tot_r = float(tot_r or 0.0)
    gap = tot_o - tot_r  # 下单 − 回款：>0 表示尚待回款（含未交付）
    ytd_pct = (tot_r / tot_o * 100.0) if tot_o else None
    ytd_txt = f"{ytd_pct:.1f}%" if ytd_pct is not None else "—"
    bar_w = max(0.0, min(float(ytd_pct or 0), 100.0))
    gap_hint = "尚待回款" if gap > 0 else ("回款超下单" if gap < 0 else "持平")
    gap_num = charts.fmt_wan(abs(gap))
    pl = (period_label or "").strip()
    pl_html = f" · {_esc(pl)}" if pl else ""

    hero = tpl.fill(
        "render/rc_totals.html",
        gap_hint=gap_hint,
        gap_num=gap_num,
        tot_o=charts.fmt_wan(tot_o),
        tot_r=charts.fmt_wan(tot_r),
        period_label=pl_html,
    )
    recv = ""
    if show_delivered_unpaid and delivered_gross is not None:
        ar = float(delivered_gross) - tot_r
        ar_s = ("−" if ar < 0 else "") + charts.fmt_wan(abs(ar)) + "万"
        recv = tpl.fill("render/rc_recv.html", ar_s=ar_s)
    rate = tpl.fill(
        "render/rc_rate.html", ytd_txt=ytd_txt, bar_w=bar_w, tot_o=charts.fmt_wan(tot_o), tot_r=charts.fmt_wan(tot_r)
    )
    pills = ""
    bud = ""
    rb = (budget or {}).get("receipt") if budget else None
    ob = (budget or {}).get("order") if budget else None
    for _key, title, b in (("receipt", "回款年目标", rb), ("order", "下单年目标", ob)):
        if not (b and b.get("target")):
            continue
        pct = b.get("pct")
        if pct is None:
            pct_txt = "—"
        elif pct > 999:
            pct_txt = ">999% · 目标待校准"
        else:
            pct_txt = f"{pct:.1f}%"
        bw = max(0.0, min(float(pct or 0), 100.0))
        bud += tpl.fill("render/rc_bud.html", title=title, pct_txt=pct_txt, bw=bw, target=charts.fmt_wan(b["target"]))
    return tpl.fill("render/rc_side.html", content=f"{hero}{recv}{rate}{pills}{bud}")

def _receipt_insight_panel(
    receipt_order_monthly, budget=None, delivered_gross=None, show_delivered_unpaid=False, period_label=""
):
    """回款右侧驾驶舱（全年按月加总版，兼容旧调用）。"""
    if not receipt_order_monthly:
        return tpl.load("render/rc_side_empty.html")
    tot_r = tot_o = 0.0
    for _label, rec, order, _ratio in receipt_order_monthly:
        tot_r += rec or 0.0
        tot_o += order or 0.0
    return _receipt_insight_totals(
        tot_o,
        tot_r,
        delivered_gross=delivered_gross,
        budget=budget,
        show_delivered_unpaid=show_delivered_unpaid,
        period_label=period_label,
    )

def _receipt_insight_from_period(p, budget=None, show_delivered_unpaid=False, period_label=""):
    """单周期回款侧栏：用该周期已算好的 orders/receipts/revenue_gross（随 .pv 切，零运算）。"""
    return _receipt_insight_totals(
        p.get("orders"),
        p.get("receipts"),
        delivered_gross=p.get("revenue_gross"),
        budget=budget,
        show_delivered_unpaid=show_delivered_unpaid,
        period_label=period_label or p.get("label") or "",
    )

def _months_for_period_key(key: str, year_key: str) -> list[int]:
    """单个周期 key → 月份列表（与顶部选择器 key 形如 2026年 / 2026年Q1 / 2026年3月 / 2026年1-3月 对齐）。"""
    if not key or key == year_key or (key.endswith("年") and "Q" not in key and "月" not in key):
        return list(range(1, 13))
    try:
        rest = key.split("年", 1)[1]
    except IndexError:
        return list(range(1, 13))
    if rest.startswith("Q"):
        q = int(rest[1:])
        sm = (q - 1) * 3 + 1
        return [sm, sm + 1, sm + 2]
    if rest.endswith("月"):
        body = rest[:-1]  # 去「月」
        if "-" in body:
            a, b = body.split("-", 1)
            return list(range(int(a), int(b) + 1))
        return [int(body)]
    return list(range(1, 13))

def _period_months_map(summary) -> dict[str, list[int]]:
    """周期 key → 应高亮的月份列表（Python 侧预生成塞 data-rm-map，前端只读应用、不解析 key）。
    年=1..12 全亮；季=该季 3 月；月=单月；区间=起止月闭区间。"""
    meta = summary.get("meta") or {}
    yk = meta.get("year_key") or ""
    groups = meta.get("tab_groups") or {}
    keys = [yk] + list(groups.get("季度") or []) + list(groups.get("月") or []) + list(groups.get("区间") or [])
    # 去重保序
    seen, ordered = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            ordered.append(k)
    return {k: _months_for_period_key(k, yk) for k in ordered}

def render_receipts(
    receipt_order_monthly,
    budget=None,
    *,
    period_months_map=None,
    year_key=None,
    delivered_gross=None,
    periods=None,
    default_key=None,
    show_delivered_unpaid=False,
):
    """回款图（下单+回款双柱 + 线上率%）+ 右侧驾驶舱（A3：总下单/总回款首行）。
    迭代21：卡根挂 data-rm-map（周期→月份）供前端只切高亮，柱图全年视角不变。
    periods=各周期 dict 时：侧栏按 .pv 预渲染随「看哪段」切（数字跟周期，铁律2 前端零运算）；
    年目标条只挂在全年块。delivered_gross 仅兼容旧调用（无 periods 时用）。
    show_delivered_unpaid：陆总#1 默认 False，隐藏「已交付未回款」。"""
    import json

    rb = (budget or {}).get("receipt") if budget else None
    budget_month = (rb["target"] / 12.0) if rb and rb.get("target") else None
    yk = year_key or ""
    dk = default_key or yk
    if periods and yk:
        # 侧栏随周期切：本期下单/回款/交付；预算条只在全年显示（年目标 vs 年完成）
        side = "".join(
            _pv(
                k,
                dk,
                _receipt_insight_from_period(
                    periods[k],
                    budget if k == yk else None,
                    show_delivered_unpaid=show_delivered_unpaid,
                    period_label=k,
                ),
            )
            for k in periods
        )
    else:
        side = _receipt_insight_panel(
            receipt_order_monthly,
            budget,
            delivered_gross=delivered_gross,
            show_delivered_unpaid=show_delivered_unpaid,
            period_label=yk or "",
        )
    rm_map = period_months_map or {}
    map_json = json.dumps(rm_map, ensure_ascii=False, separators=(",", ":"))
    return tpl.fill(
        "render/rc_card.html",
        yk=_esc(yk),
        map_json=_esc(map_json),
        budget_tag=_budget_tag(budget),
        chart=charts.receipt_order_chart(receipt_order_monthly, budget_month=budget_month),
        side=side,
    )

def _rank_amt(v):
    """排名金额显示：负数（红冲/退款净额）用全角负号，与利润表 _amt 一致。"""
    return ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"

def _rank_rows_html(items, total, *, share=True):
    """排名行 HTML。金额/占比后端已定（入参 amount 为数、展示用 _rank_amt）。"""
    if not items:
        return tpl.load("render/ev_empty.html")
    mx = max((it["amount"] for it in items), default=0) or 1
    rows = []
    for i, it in enumerate(items, 1):
        w = max(it["amount"] / mx * 100, 0)
        meta = f"{it['count']}笔"
        if share:
            meta += f"·{it['amount'] / total * 100:.0f}%" if total > 0 else "·—"
        rows.append(
            tpl.fill(
                "render/rank_row.html",
                i=i,
                title=_esc(it["name"]),
                name=_esc(it["name"]),
                w=w,
                amt=_rank_amt(it["amount"]),
                meta=meta,
            )
        )
    return "".join(rows)

def _rank_card(title, tag, rk, kind="", embed_full=False):
    """一张排名卡：名次 + 名称 + 横条(按最大值归一) + 金额 + 笔数/占比。金额均后端算好，前端零运算。
    kind=接口里 rankings 的键（orders_by_dept…），「其余」行点开全量明细时前端用它取数。
    embed_full=True（BU 页）：预渲染 .rk-full 全量，本地弹窗展开，不调全公司 API（铁律12）。
    用户端不展示「（未填）」行——未填归类只在管理端异常处理；后端 unfilled 仍算（守恒）。"""
    items = (rk or {}).get("items") or []
    total = (rk or {}).get("total") or 0
    if not items:
        body = tpl.load("render/ev_empty.html")
    else:
        rows_html = _rank_rows_html(items, total)
        others = rk.get("others")
        more = ""
        if others:
            more = tpl.fill(
                "render/rank_more.html", names=others["names"], amt=_rank_amt(others["amount"]), count=others["count"]
            )
        full = ""
        if embed_full and others:
            full_items = rk.get("full_items") or items
            full = tpl.fill("render/rank_full.html", rows=_rank_rows_html(full_items, total))
        body = tpl.fill("render/rank_body.html", rows=rows_html, more=more, full=full)
    tag_html = tpl.fill("render/rank_tag.html", tag=_esc(tag)) if tag else ""
    return tpl.fill("render/rank_card.html", kind=_esc(kind), title=title, tag_html=tag_html, body=body)

def _merge_dual_rank(o_rk, r_rk, top=10):
    """合并下单/回款排名为双血条主体列表。金额与宽度后端算好。"""
    o_map = {it["name"]: it for it in (o_rk or {}).get("full_items") or (o_rk or {}).get("items") or []}
    r_map = {it["name"]: it for it in (r_rk or {}).get("full_items") or (r_rk or {}).get("items") or []}
    # 主体 = 下单或回款有名（排除未填）
    names = []
    seen = set()
    for src in (o_rk or {}).get("full_items") or (o_rk or {}).get("items") or []:
        n = src["name"]
        if n and n not in seen and n != "（未填）":
            seen.add(n)
            names.append(n)
    for src in (r_rk or {}).get("full_items") or (r_rk or {}).get("items") or []:
        n = src["name"]
        if n and n not in seen and n != "（未填）":
            seen.add(n)
            names.append(n)

    # 排序：按 max(下单,回款) 降序
    def score(n):
        return max(float((o_map.get(n) or {}).get("amount") or 0), float((r_map.get(n) or {}).get("amount") or 0))

    names.sort(key=score, reverse=True)
    full = []
    for n in names:
        oa = float((o_map.get(n) or {}).get("amount") or 0)
        ra = float((r_map.get(n) or {}).get("amount") or 0)
        full.append({"name": n, "order": oa, "receipt": ra, "order_disp": _rank_amt(oa), "receipt_disp": _rank_amt(ra)})
    items = full[:top]
    rest = full[top:]
    others = None
    if rest:
        others = {
            "names": len(rest),
            "order": round(sum(x["order"] for x in rest), 2),
            "receipt": round(sum(x["receipt"] for x in rest), 2),
            "order_disp": _rank_amt(sum(x["order"] for x in rest)),
            "receipt_disp": _rank_amt(sum(x["receipt"] for x in rest)),
        }
    mx = max((max(x["order"], x["receipt"]) for x in full), default=0) or 1
    for x in items:
        x["wo"] = max(x["order"] / mx * 100, 0)
        x["wr"] = max(x["receipt"] / mx * 100, 0)
    return {"items": items, "others": others, "full_items": full, "mx": mx}

def monthly_mkey(year, dim: str, name: str) -> str:
    """页面级月度字典键：年|维|主体。维 sales→销售、customer→客户。"""
    label = "销售" if dim == "sales" else "客户"
    try:
        y = int(year or 0)
    except (TypeError, ValueError):
        y = 0
    return f"{y}|{label}|{name}"

def _monthly_dual_rows(name: str, series: dict | None) -> list[dict]:
    """陆总#8：主体 1~12 月双血条显示串（金额/宽度已算好，JS 只拼 DOM）。"""
    series = series or {}
    o = list(series.get("order") or [0.0] * 12)
    r = list(series.get("receipt") or [0.0] * 12)
    while len(o) < 12:
        o.append(0.0)
    while len(r) < 12:
        r.append(0.0)
    o, r = o[:12], r[:12]
    mx = max([max(float(o[i]), float(r[i])) for i in range(12)] + [0.0]) or 1.0
    out = []
    for i in range(12):
        oa, ra = float(o[i] or 0), float(r[i] or 0)
        out.append(
            {
                "i": i + 1,
                "name": f"{i + 1}月",
                "order": oa,
                "receipt": ra,
                "order_disp": _rank_amt(oa),
                "receipt_disp": _rank_amt(ra),
                "wo": round(max(oa / mx * 100, 0), 1),
                "wr": round(max(ra / mx * 100, 0), 1),
            }
        )
    return out

def _json_num(v) -> float | int:
    """JSON 数：整值出 int，与 JS JSON.stringify 一致（避免 100.0 vs 100）。"""
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return 0
    if f == int(f):
        return int(f)
    return round(f, 1)

def compact_monthly_display(monthly) -> list[dict]:
    """任务书34：入库/页面级字典用紧凑显示串（无 raw 金额，JS 零运算）。"""
    rows = []
    for m in monthly or []:
        rows.append(
            {
                "i": _json_num(m.get("i")),
                "name": m.get("name"),
                "wo": _json_num(m.get("wo")),
                "wr": _json_num(m.get("wr")),
                "order_disp": m.get("order_disp") or _rank_amt(m.get("order") or 0),
                "receipt_disp": m.get("receipt_disp") or _rank_amt(m.get("receipt") or 0),
            }
        )
    return rows

def attach_monthly_to_dual(
    dual: dict,
    monthly_dim: dict | None,
    *,
    year: int = 0,
    dim: str = "sales",
    store: dict | None = None,
) -> dict:
    """把 rankings_monthly 某维归一：items 只挂 mkey；完整 12 月显示串写入 store。

    任务书34：禁止再把 12 月 JSON 嵌进每一行（payload 膨胀）。
    """
    monthly_dim = monthly_dim or {}
    if store is None:
        store = {}

    def _one(it: dict) -> None:
        name = it.get("name") or ""
        mkey = monthly_mkey(year, dim, name)
        it["mkey"] = mkey
        # 行上不再带 monthly 大数组
        it.pop("monthly", None)
        if mkey not in store:
            full = _monthly_dual_rows(name, monthly_dim.get(name))
            store[mkey] = compact_monthly_display(full)

    for it in dual.get("items") or []:
        _one(it)
    for it in dual.get("full_items") or []:
        _one(it)
    return dual

def monthly_data_script(store: dict | None) -> str:
    """页面级月度字典脚本（模板 render/rk_monthly_data.html，与 JS 同形）。"""
    import json

    if not store:
        return ""
    payload = json.dumps(store, ensure_ascii=False, separators=(",", ":"))
    # 防 </script> 截断
    payload = payload.replace("<", "\\u003c")
    return tpl.fill("render/rk_monthly_data.html", payload=payload)

def _dual_rows_html(items):
    if not items:
        return tpl.load("render/ev_empty.html")
    out = []
    for i, it in enumerate(items, 1):
        mkey = it.get("mkey") or ""
        out.append(
            tpl.fill(
                "render/dual_row.html",
                i=i,
                title=_esc(it["name"]),
                name=_esc(it["name"]),
                wo=it.get("wo") or 0,
                wr=it.get("wr") or 0,
                o_amt=it.get("order_disp") or _rank_amt(it.get("order") or 0),
                r_amt=it.get("receipt_disp") or _rank_amt(it.get("receipt") or 0),
                mkey=_esc(mkey),
            )
        )
    return "".join(out)

def _dual_card(title, dual, dim="", embed_full=False):
    items = (dual or {}).get("items") or []
    if not items:
        body = tpl.load("render/ev_empty.html")
    else:
        rows_html = _dual_rows_html(items)
        others = dual.get("others")
        more = ""
        if others:
            more = tpl.fill(
                "render/rank_more.html",
                names=others["names"],
                amt=f"下单{others.get('order_disp') or _rank_amt(others.get('order') or 0)} / 回款{others.get('receipt_disp') or _rank_amt(others.get('receipt') or 0)}",
                count=others["names"],
            )
        full = ""
        if embed_full and others:
            full_items = dual.get("full_items") or items
            # recompute widths for full
            mx = dual.get("mx") or max((max(x["order"], x["receipt"]) for x in full_items), default=1) or 1
            for x in full_items:
                x["wo"] = max(x["order"] / mx * 100, 0)
                x["wr"] = max(x["receipt"] / mx * 100, 0)
                x.setdefault("order_disp", _rank_amt(x["order"]))
                x.setdefault("receipt_disp", _rank_amt(x["receipt"]))
            full = tpl.fill("render/rank_full.html", rows=_dual_rows_html(full_items))
        body = tpl.fill("render/rank_body.html", rows=rows_html, more=more, full=full)
    return tpl.fill("render/dual_card.html", dim=_esc(dim), title=title, body=body)

def dual_rankings_from_daily(rankings: dict, top: int = 10) -> dict:
    """任务书39·C：/api/daily 的四维单血条 → 双血条两卡就绪结构（显示串/宽度已算）。
    自定义区间不带月度下钻（mkey 空；语义：跨任意日段非完整自然月）。"""
    dual_s = _merge_dual_rank(rankings.get("orders_by_sales"), rankings.get("receipts_by_sales"), top=top)
    dual_c = _merge_dual_rank(rankings.get("orders_by_customer"), rankings.get("receipts_by_customer"), top=top)

    def pack(dual, title, dim):
        items = []
        for i, it in enumerate(dual.get("items") or [], 1):
            items.append(
                {
                    "i": i,
                    "name": it["name"],
                    "wo": round(it.get("wo") or 0, 1),
                    "wr": round(it.get("wr") or 0, 1),
                    "order_disp": it.get("order_disp") or _rank_amt(it.get("order") or 0),
                    "receipt_disp": it.get("receipt_disp") or _rank_amt(it.get("receipt") or 0),
                    "mkey": "",
                }
            )
        others = dual.get("others")
        others_out = None
        if others:
            others_out = {
                "names": others["names"],
                "amt": (
                    f"下单{others.get('order_disp') or _rank_amt(others.get('order') or 0)}"
                    f" / 回款{others.get('receipt_disp') or _rank_amt(others.get('receipt') or 0)}"
                ),
                "count": others["names"],
            }
        full_out = []
        full_src = dual.get("full_items") or dual.get("items") or []
        mx = dual.get("mx") or 1 or 1
        for i, it in enumerate(full_src, 1):
            oa = float(it.get("order") or 0)
            ra = float(it.get("receipt") or 0)
            full_out.append(
                {
                    "i": i,
                    "name": it["name"],
                    "wo": round(max(oa / mx * 100, 0), 1),
                    "wr": round(max(ra / mx * 100, 0), 1),
                    "order_disp": it.get("order_disp") or _rank_amt(oa),
                    "receipt_disp": it.get("receipt_disp") or _rank_amt(ra),
                    "mkey": "",
                }
            )
        return {
            "title": title,
            "dim": dim,
            "items": items,
            "others": others_out,
            "empty": not items,
            "embed_full": bool(others),
            "full_items": full_out if others else [],
        }

    return {
        "sales": pack(dual_s, "下单/回款 · 按销售", "sales"),
        "customer": pack(dual_c, "下单/回款 · 按客户", "customer"),
        "monthly_drill": False,  # 自定义日段不带 1~12 月下钻
    }

def render_rankings(p, embed_full=False, *, monthly_store: dict | None = None, emit_monthly_script: bool = True):
    """A6：下单与回款双血条两卡（按销售 / 按客户）；去掉按部门。
    陆总#8 / 任务书34：页面级 monthly 字典 + 行 data-mkey（无行内 12 月 JSON）。

    monthly_store：多周期共享字典（build_dashboard_fragments 注入一次脚本）。
    emit_monthly_script=False：只出网格，由调用方拼 monthly_data_script(store)。
    """
    rk = p.get("rankings") or {}
    s, e = p.get("range", ("", ""))
    rm = p.get("rankings_monthly") or {}
    year = rm.get("year") or 0
    store: dict = monthly_store if monthly_store is not None else {}
    dual_s = attach_monthly_to_dual(
        _merge_dual_rank(rk.get("orders_by_sales"), rk.get("receipts_by_sales")),
        rm.get("sales"),
        year=year,
        dim="sales",
        store=store,
    )
    dual_c = attach_monthly_to_dual(
        _merge_dual_rank(rk.get("orders_by_customer"), rk.get("receipts_by_customer")),
        rm.get("customer"),
        year=year,
        dim="customer",
        store=store,
    )
    grid = tpl.fill(
        "render/dual_grid.html",
        s=_esc(s),
        e=_esc(e),
        sales=_dual_card("下单/回款 · 按销售", dual_s, "sales", embed_full=embed_full),
        cust=_dual_card("下单/回款 · 按客户", dual_c, "customer", embed_full=embed_full),
    )
    if emit_monthly_script:
        return monthly_data_script(store) + grid
    return grid

def _margin_meta(mp):
    """系统成本率 meta：None（收入 0）→ 灰显「系统成本率 —」。
    陆总 0714 改叫「系统成本率」（=系统抓的项目成本÷交付收入）——生产环节大家习惯看成本率；
    只在利润表层才还原成"生产毛利"的利润概念。入参 mp=cost_pct。"""
    return f"系统成本率 {mp:.0f}%" if mp is not None else "系统成本率 —"

def _pname(name):
    """名称 span：悬浮 #tip 显示全名（长名截断也能看全）。data-tip 走 getAttribute+innerHTML
    两层解码→双层转义（铁律10）；title 保留为无 JS 时的原生兜底。"""
    n = _esc(name)
    return tpl.fill("render/pname.html", n=n, tip=_esc(n))

def _profit_rank_rows_html(items, show_meta=True):
    """收入排名行 HTML。"""
    if not items:
        return tpl.load("render/ev_empty.html")

    def _meta(it):
        return tpl.fill("render/rk_meta.html", text=_margin_meta(it.get("cost_pct"))) if show_meta else ""

    mx = max((abs(it["revenue"]) for it in items), default=0) or 1
    rows = []
    for i, it in enumerate(items, 1):
        w = max(it["revenue"] / mx * 100, 0)
        rows.append(
            tpl.fill(
                "render/profit_rank_row.html",
                i=i,
                pname=_pname(it["name"]),
                w=w,
                amt=_rank_amt(it["revenue"]),
                meta=_meta(it),
            )
        )
    return "".join(rows)

def _profit_rank_card(title, tag, rk, dim="", show_meta=True, embed_full=False):
    """收入/毛利排名卡：名次 + 名称 + 横条(按收入归一) + 收入 + 系统成本率。金额/率均后端算好，前端零运算（铁律2）。
    整体页「其余」→ /api/profit_ranking；BU 页 embed_full 预渲染 .pr-full 本地展开（铁律12）。
    show_meta=False → 隐藏成本率列（陆总 0714：按销售的率先不显示，防"人力算不算"连锁追问）。
    用户端不展示「（未填）」行。"""
    items = (rk or {}).get("items") or []

    def _meta(it):
        return tpl.fill("render/rk_meta.html", text=_margin_meta(it.get("cost_pct"))) if show_meta else ""

    if not items:
        body = tpl.load("render/ev_empty.html")
    else:
        rows_html = _profit_rank_rows_html(items, show_meta=show_meta)
        others = rk.get("others")
        more = ""
        if others:
            more = tpl.fill(
                "render/profit_more.html", names=others["names"], amt=_rank_amt(others["revenue"]), meta=_meta(others)
            )
        full = ""
        if embed_full and others:
            full_items = rk.get("full_items") or items
            full = tpl.fill("render/profit_full.html", rows=_profit_rank_rows_html(full_items, show_meta=show_meta))
        body = tpl.fill("render/rank_body.html", rows=rows_html, more=more, full=full)
    return tpl.fill("render/profit_card.html", dim=_esc(dim), title=title, tag=tag, body=body)

def _conc_tag(rk):
    """卡头标签：确认口径（小灰）+ 前 k 大占收入%（集中度，`.conc` 独立高亮、数字放大）。
    无数据 → 只留口径。返回整段 HTML（含自己的 span，卡头不再外包 .tag）。"""
    c = (rk or {}).get("conc_pct")
    k = (rk or {}).get("conc_k", 5)
    if c is None:
        return tpl.load("render/conc_tag_only.html")
    return tpl.fill("render/conc_tag.html", k=k, c=c)

def render_profit_rankings(p, embed_full=False):
    pr = p.get("profit_rankings") or {}
    s, e = p.get("range", ("", ""))
    cust, sale = pr.get("revenue_by_customer"), pr.get("revenue_by_sales")
    return tpl.fill(
        "render/profit_grid.html",
        s=_esc(s),
        e=_esc(e),
        cust=_profit_rank_card("收入 · 按客户", _conc_tag(cust), cust, "customer", embed_full=embed_full),
        sale=_profit_rank_card("收入 · 按销售", _conc_tag(sale), sale, "sales", show_meta=False, embed_full=embed_full),
    )

