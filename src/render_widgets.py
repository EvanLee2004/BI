#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周期选择 / KPI 基本情况 等纯渲染小部件（从 render.py 按符号迁出）。
HTML 外置 static/templates/render/，本模块只填占位符。"""

from __future__ import annotations

import charts
import version as product_version
import tpl

# 基本情况 KPI 卡（陆总 2026-07-13：5 张）
# (标签, 取值键, 来源, 涨为好, 附率键, 趋势线色, 目标键)
# 交付金额=智云含税交付额(不÷1.06)；脚注另标确认口径交付收入
KPI_CARDS = [
    ("下单", "orders", "智云·下单预估额", True, None, "var(--purple)", "order"),
    ("交付金额", "revenue_gross", "智云直接抓·含税 · 确认口径÷1.06见脚注", True, None, "var(--blue)", None),
    ("管理毛利", "gross_profit", "完整口径·交付收入−生产成本", True, "gross_margin_pct", "var(--orange)", "margin"),
    (
        "税前利润",
        "pretax_profit",
        "毛利−各项费用−附加税±其他",
        True,
        "pretax_margin_pct",
        "var(--pos)",
        "pretax_margin",
    ),
    ("回款", "receipts", "智云·回款(到账)", True, None, "var(--teal)", "receipt"),
]

# 回款/下单比解释小字：陆总 0714 拍板不再展示（"这行不用写，大家都理解"）；常量保留给旧测试/兼容
RECEIPT_NOTE = "当月回款多对应往月下单，反映资金回笼节奏，非当月回收率"


# ---------- 板块③ 下单与回款排名（随周期切）----------
def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _kpi_val(p, key):
    """KPI 取值：一律取 period 已算好的字段（不做派生聚合，前端零运算）。"""
    return p[key]


def _prev_period_key(pkey, year):
    """环比的上一同粒度周期 key：年→无（缺上年数据）；季→上季(Q1无)；月→上月(1月无)。"""
    yk = f"{year}年"
    if pkey == yk:
        return None
    if "Q" in pkey:
        q = int(pkey.split("Q")[1])
        return f"{yk}Q{q - 1}" if q > 1 else None
    mpart = pkey.split("年")[1].replace("月", "")
    if "-" in mpart:  # 自定义月区间：无"同粒度上期"概念
        return None
    m = int(mpart)
    return f"{yk}{m - 1}月" if m > 1 else None


def _wan(v):
    return charts.fmt_wan(v) + "万"


def _title_version_html() -> str:
    """顶栏产品名旁版本徽章（用户端 / 管理端「看」/ BU 页同源；唯一源=根目录 VERSION）。
    与管理端顶栏一致：主号去 -beta 后缀，试运行/公测附阶段。"""
    v = product_version.read_version()
    base = v.partition("-")[0]
    stage = product_version.product_stage(v)
    text = f"v{base}" if (not stage or stage == "正式版") else f"v{base} · {stage}"
    return tpl.fill("render/title_version.html", text=_esc(text))


def _amt(v, colored=False, muted=False):
    s = ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"
    cls = "pl-amt"
    if colored:
        cls += " pos" if v >= 0 else " neg"
    return tpl.fill("render/amt.html", cls=cls, s=s)


def _target_bar(budget, tkey, pkey, year, p):
    """KPI 下业务目标进度条（任务书51·B2：消费 domain.pl.structure.kpi_target_bar）。

    tkey=order/receipt/margin/pretax_margin；无目标→空态小字。
    仅「1-6 月」区间用 H1 目标；Q1≠H1。年目标 done=全年累计。
    """
    from domain.pl.structure import kpi_target_bar

    bar = kpi_target_bar(tkey, pkey, p, budget)
    if bar is None:
        return ""
    if bar.get("empty"):
        return tpl.load("render/kpi_tgt_empty.html")
    if bar.get("kind") == "margin":
        return tpl.fill(
            "render/kpi_tgt_margin.html",
            label=bar.get("label") or "年目标",
            tgt=bar.get("tgt"),
            cur_s=bar.get("cur_disp") or "—",
            cls=bar.get("cls") or "low",
            w=bar.get("bar_w") or 0,
            pct_s=bar.get("pct_disp") or "—",
        )
    return tpl.fill(
        "render/kpi_tgt_amount.html",
        label=bar.get("label") or "年目标",
        tgt_wan=bar.get("tgt_wan") or "0",
        done_wan=bar.get("done_wan") or "0",
        cls=bar.get("cls") or "low",
        w=bar.get("bar_w") or 0,
        pct_s=bar.get("pct_disp") or "—",
    )


# ---------- 板块① 基本情况（单周期，5 KPI：值+环比+目标进度+峰值/对照）----------
def _kpi_peak_row(month_keys, P, key, year):
    """全年逐月峰值一行（任务书51·B2：消费 domain.pl.structure.kpi_peak_for）。"""
    from domain.pl.structure import kpi_peak_for

    summary = {
        "meta": {"year": year, "tab_groups": {"月": list(month_keys or [])}},
        "periods": P or {},
    }
    peak = kpi_peak_for(summary, key)
    if not peak:
        return ""
    return tpl.fill(
        "render/kpi_peak_row.html",
        lab=_esc(peak.get("label") or ""),
        val_wan=peak.get("value_wan") or "0",
    )


def _bu_orders_block(bu_list):
    """下单卡内各 BU 进度（陆总0714·C1）：期内下单额 + 全年累计/BU 年目标。
    布局：上行 名+金额+率，下行 全宽进度条（更清晰）。
    有目标 → 填充=年累计/年目标；未设目标 → 仍画轨道，填充=期内额相对最大 BU（比大小，非达成率）。
    只在全公司整体页出现（BU 页不传此参数·铁律12）。金额/率全部后端算好。"""
    if not bu_list:
        return ""
    max_amt = max((float(d.get("amount") or 0.0) for d in bu_list), default=0.0) or 1.0
    rows = ""
    for d in bu_list:
        amt_v = float(d.get("amount") or 0.0)
        amt = charts.fmt_wan(amt_v)
        pct = d.get("pct")
        if pct is not None:
            w = min(max(float(pct), 0.0), 100.0)
            cls = "ok" if pct >= 100 else ("warn" if pct >= 80 else "low")
            badge = tpl.fill("render/kpi_bu_badge_pct.html", pct=pct)
            track = tpl.fill("render/kpi_bu_track.html", cls=cls, w=w)
            tip = f"年目标 {charts.fmt_wan(d['target'])}万 · 全年累计 {charts.fmt_wan(d.get('year_amount') or 0)}万"
        else:
            # 未设目标：轨道仍在；填充只反映相对大小（最大 BU=100%），文案标明未设
            w = min(max(amt_v / max_amt * 100.0, 0.0), 100.0) if amt_v else 0.0
            badge = tpl.load("render/kpi_bu_badge_none.html")
            track = tpl.fill("render/kpi_bu_track_soft.html", w=w)
            tip = "该 BU 未填下单年目标（管理端·人工填写·业绩目标·选 BU 范围）；条长仅为部门间相对大小"
        rows += tpl.fill(
            "render/kpi_bu_row.html", tip=_esc(_esc(tip)), name=_esc(d["name"]), amt=amt, badge=badge, track=track
        )
    return tpl.fill("render/kpi_bus.html", rows=rows)


def _kpi_period_label(pkey, year):
    """基本情况卡头旁的时段角标：全年写「2026年」；季/月/区间去掉年份前缀写「Q1」「3月」「1-6月」。
    与顶部「看哪段」同源（.pv 按周期预渲染，前端只切显示、零运算）。"""
    yk = f"{year}年"
    if pkey == yk:
        return yk
    if isinstance(pkey, str) and pkey.startswith(yk):
        rest = pkey[len(yk) :]
        return rest or yk
    return str(pkey or yk)


def render_basic(pkey, P, year, month_keys, budget=None, bu_orders=None, show_delivered_unpaid=False):
    """基本情况 KPI。month_keys=全年月周期列表（算峰值用）；不再画迷你折线。
    show_delivered_unpaid：陆总#1 默认 False，回款卡脚注「已交付未回款」隐藏。"""
    p = P[pkey]
    prev = _prev_period_key(pkey, year)
    period_tag = _esc(_kpi_period_label(pkey, year))
    cards = ""
    for label, key, src, up_good, pctkey, _color, tkey in KPI_CARDS:
        val = float(_kpi_val(p, key) or 0.0)
        vhtml = tpl.fill("render/kpi_u.html", val=charts.fmt_wan(val))
        # 环比上期（同粒度）
        if prev is not None and _kpi_val(P.get(prev) or {}, key):
            pv = float(_kpi_val(P[prev], key) or 0.0)
            if pv:
                d = (val - pv) / abs(pv) * 100
                good = (d >= 0) == up_good
                arrow = "▲" if d >= 0 else "▼"
                delta = tpl.fill("render/kpi_delta.html", cls=("up" if good else "down"), arrow=arrow, d=abs(d))
            else:
                delta = tpl.load("render/kpi_delta_muted.html")
        else:
            delta = tpl.load("render/kpi_delta_muted.html")
        sub = ""
        if key == "revenue_gross":
            sub = tpl.fill("render/kpi_sub.html", label="交付收入(÷1.06)", val=charts.fmt_wan(p["revenue_net"]) + "万")
            o = float(p.get("orders") or 0.0)
            if o > 0:
                sub += tpl.fill("render/kpi_sub.html", label="交付占下单", val=f"{val / o * 100:.0f}%")
        elif pctkey == "gross_margin_pct":
            sub = tpl.fill("render/kpi_sub.html", label="毛利率", val=f"{p[pctkey]:.1f}%")
        elif pctkey == "pretax_margin_pct":
            sub = tpl.fill("render/kpi_sub.html", label="利润率", val=f"{p[pctkey]:.1f}%")
        if key == "receipts":
            r = p["receipt_order_ratio_pct"]
            rtxt = f"{r:.1f}%" if r is not None else "—"
            sub = tpl.fill("render/kpi_sub.html", label="总回款/下单比", val=rtxt)
        tgt = _target_bar(budget, tkey, pkey, year, p)
        bus_html = _bu_orders_block(bu_orders) if key == "orders" else ""
        # 卡底有用信息：全年峰值；回款卡「已交付未回款」受 show_delivered_unpaid 开关
        foot_rows = _kpi_peak_row(month_keys, P, key, year)
        if key == "receipts" and show_delivered_unpaid:
            ar = float(p.get("revenue_gross") or 0.0) - val  # 交付金额(含税)−回款，近似应收
            ar_s = ("−" if ar < 0 else "") + charts.fmt_wan(abs(ar))
            foot_rows += tpl.fill("render/kpi_foot_ar.html", ar_s=ar_s)
        foot = tpl.fill("render/kpi_foot.html", foot_rows=foot_rows) if foot_rows else ""
        cards += tpl.fill(
            "render/kpi_card.html",
            label=label,
            period_tag=period_tag,
            vhtml=vhtml,
            sub=sub,
            delta=delta,
            tgt=tgt,
            bus_html=bus_html,
            foot=foot,
            src=src,
        )
    return tpl.fill("render/kpi_grid.html", cards=cards)


# ---------- 全局周期选择器（下拉菜单）----------
def render_period_bar(summary):
    """周期选择器：按钮 + 日历面板（快捷段：全年/季度；月份网格：点起始月再点结束月=自选区间）。
    所有可选周期（含全部月区间组合）都已后端预渲染成 .pv 块，前端只做显示切换、不算任何数。"""
    meta = summary["meta"]
    tg = meta["tab_groups"]
    year, yk = meta["year"], meta["year_key"]
    cur_month = len(tg["月"])
    chips = tpl.fill("render/period_chip.html", on=" on", key=yk, label="全年")
    chips += "".join(tpl.fill("render/period_chip.html", on="", key=q, label=q.split("年")[1]) for q in tg["季度"])
    cells = "".join(
        tpl.fill("render/period_m.html", m=m, disabled=("" if m <= cur_month else " disabled")) for m in range(1, 13)
    )
    return tpl.fill("render/period_bar.html", year=year, cur_month=cur_month, chips=chips, cells=cells)


def _pv(key, default_key, inner):
    style = "" if key == default_key else "display:none"
    return tpl.fill("render/pv.html", key=key, style=style, inner=inner)
