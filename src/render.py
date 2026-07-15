#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装经营驾驶舱 HTML（科技风暗色默认 + 浅色切换）。四段骨架：基本情况/经营利润/收入与毛利结构/下单与回款（回款情况+下单回款排名）。
全局时间选择器（月/季/年，默认年）驱动 基本情况+利润表+费用构成 一起切；趋势图/回款图是整年时间线。
所有金额 Python 算好，JS 只做主题切换/周期切换/展开折叠/提示定位，不做任何金额运算。
HTML 外置 static/templates/render/，本模块只算值与 format 填充。"""
from __future__ import annotations

import charts
import theme
import version as product_version
import tpl
from render_shell import (
    DRAWER_HTML, PARTICLES_HTML, PW_MODAL_HTML, RK_MODAL_HTML, DAILY_HTML,
)
from render_widgets import (
    KPI_CARDS, RECEIPT_NOTE,
    _kpi_val, _prev_period_key, _wan, _title_version_html, _amt, _target_bar,
    _kpi_peak_row, _bu_orders_block, _kpi_period_label, render_basic,
    render_period_bar, _pv, _esc,
)

GROUP_COLORS = {"营销费用": "var(--blue)", "管理费用": "var(--purple)", "固定运营费用": "var(--teal)",
                "研发费用": "var(--orange)", "财务费用": "var(--cost)"}
LED_OF = {"营销费用": "市场费用", "管理费用": "管理费用", "固定运营费用": "固定运营费用",
          "研发费用": "技术服务费", "财务费用": "财务费用"}

# ---------- 板块②-1 交付金额 · 毛利趋势（整年，静态；周期高亮同回款卡）----------
def render_trend(trend, hl, *, period_months_map=None, year_key=None):
    # 看端卡头只留「按月」；柱顶/线上说明见图例，不堆运营备注。
    # 迭代：卡根挂 data-rm-map（复用 _period_months_map）供前端只切高亮，柱图全年视角不变。
    import json
    yk = year_key or ""
    rm_map = period_months_map or {}
    map_json = json.dumps(rm_map, ensure_ascii=False, separators=(",", ":"))
    return tpl.fill("render/trend_card.html",
                    yk=_esc(yk), map_json=_esc(map_json),
                    chart=charts.combo_bar_line_chart(trend, hl))

# ---------- 费用构成环形图（随周期切）----------
def render_donut(p):
    e = p["expense"]; man = p["manual"]; led = p["ledger_expenses"]
    groups = ["营销费用", "管理费用", "固定运营费用", "研发费用", "财务费用"]
    segs = [(g, e[g], GROUP_COLORS[g]) for g in groups if e[g] > 0]
    # 悬浮明细：每类拆成 手填人力 / 台账 两块（陆总口径）
    detail = {
        "营销费用": [("营销人力成本(手填)", man["营销人力成本"]), ("市场费用(台账)", led["市场费用"])],
        "管理费用": [("管理人力成本(手填)", man["管理人力成本"]), ("管理费用(台账)", led["管理费用"])],
        "固定运营费用": [("固定运营费用(台账)", led["固定运营费用"])],
        "研发费用": [("研发人力成本(手填)", man["研发人力成本"]), ("技术服务费(台账)", led["技术服务费"])],
        "财务费用": [("财务费用(台账)", led["财务费用"]), ("财务费用补充(手填)", man["财务费用补充"])],
    }
    legend = "".join(
        tpl.fill("render/donut_legend_item.html",
                 color=GROUP_COLORS[g], name=g, amt=charts.fmt_wan(e[g]))
        for g in groups)
    return tpl.fill("render/donut_wrap.html",
                    donut=charts.donut(segs, "期间费用", charts.fmt_wan(e["total"]) + "万", detail=detail),
                    legend=legend)

# 横条「未填/未标」沉底名：部门/BU 视角=未分类；类别视角=未标注明细类型（config 同文案）
_HBAR_SINK = frozenset({"未分类", "未标注明细类型"})

def _hbar_rows(rows, prefix):
    """横向条形列表（台账白名单口径分组）+ 每组的抽屉明细块。rows=[(组名,合计,[(细项,金额),...]),...]。
    宽度按最大组归一（服务端算好，前端零运算）；未分类/未标注明细类型灰色沉底。"""
    if rows is None:
        return tpl.load("render/ev_empty_old.html")
    if not rows:
        return tpl.load("render/ev_empty_none.html")
    ordered = [r for r in rows if r[0] not in _HBAR_SINK] + [r for r in rows if r[0] in _HBAR_SINK]
    mx = max(v for _, v, _ in rows) or 1
    out, details = [], []
    for name, val, fine in ordered:
        key = f"{prefix}:{name}"
        w = max(2.0, val / mx * 100)
        cls = " unfilled" if name in _HBAR_SINK else ""
        out.append(tpl.fill("render/hbar_row.html",
                            cls=cls, key=_esc(key), name=_esc(name),
                            w=w, amt=charts.fmt_wan(val)))
        inner = "".join(_drow(n, -a, "", "", sub=True) for n, a in fine[:12])
        rest = fine[12:]
        if rest:
            inner += _drow(f"其他{len(rest)}项", -sum(a for _, a in rest), "", "", sub=True)
        details.append(_detail_block(key, f"{name} · 费用构成（{charts.fmt_wan(val)}万）", inner))
    return tpl.fill("render/hbar_list.html", rows="".join(out), details="".join(details))

def _ledger_subtotal(rows):
    return charts.fmt_wan(sum(v for _, v, _ in rows)) + "万" if rows else "0万"

def render_expense_views(p, fine_rows, pc_rows, dept_rows=None):
    """期间费用构成卡：按大类｜按类别｜按业务BU（利润中心）｜按部门（预算归属部门）。
    四态台账白名单含税口径同一；卡头合计含手填人力，横条小计仅为台账部分。
    dept_rows=summary['expense_by_department'][周期]（与 pc 同形），金额全后端算好。"""
    e = p["expense"]
    tabs = tpl.load("render/expense_tabs.html")
    # 看端：横条小计可扫读；长口径说明留给管理端数据/异常页，此处不堆字
    fine_note = f'台账小计 {_ledger_subtotal(fine_rows)}'
    pc_note = f'台账小计 {_ledger_subtotal(pc_rows)}'
    dept_note = f'台账小计 {_ledger_subtotal(dept_rows)}'
    return tpl.fill("render/expense_card.html",
                    total=charts.fmt_wan(e["total"]), tabs=tabs,
                    donut=render_donut(p),
                    fine_rows=_hbar_rows(fine_rows, "fine"), fine_note=fine_note,
                    pc_rows=_hbar_rows(pc_rows, "pc"), pc_note=pc_note,
                    dept_rows=_hbar_rows(dept_rows, "dept"), dept_note=dept_note)

def _fine_to_rows(fine_k):
    """把 {大类:[(细类,金额)…]} 摊平成「按类别」横条行 [(细类,合计,[(大类,金额)…])…]（迭代22·D2）。
    同名细类跨大类合并；抽屉里按大类拆开看。金额全后端 round，前端零运算。"""
    if not fine_k:
        return []
    agg: dict[str, float] = {}
    src: dict[str, list] = {}
    for cat, pairs in fine_k.items():
        for name, amt in pairs or []:
            agg[name] = agg.get(name, 0.0) + float(amt)
            src.setdefault(name, []).append((cat, float(amt)))
    rows = [(n, round(v, 2), sorted(src[n], key=lambda x: -x[1])) for n, v in agg.items()]
    rows.sort(key=lambda r: -r[1])
    return rows

def render_bu_expense_views(p, fine_k):
    """BU 页期间费用构成卡：按大类（环形）｜按类别（横条）两态。
    与整体页「按类别」同口径（预算明细费用类型）；不出「按部门」。"""
    e = p.get("expense") or {}
    rows = _fine_to_rows(fine_k)
    tabs = tpl.load("render/bu_expense_tabs.html")
    return tpl.fill("render/bu_expense_card.html",
                    total=charts.fmt_wan(e.get("total") or 0), tabs=tabs,
                    donut=render_donut(p),
                    fine_rows=_hbar_rows(rows, "fine"),
                    subtotal=_ledger_subtotal(rows))

def render_dept_budget(dept_budget):
    """部门费用预算执行卡。迭代19 陆总拍板：界面下线（半吊子汇总无意义）；函数保留给旧测试/兼容，恒返回空。"""
    return ""

# ---------- 板块②-2 管理利润表（点大类→侧边抽屉看构成，主表定高不再顶下方图表）----------
def _row(name, impact, kind, src="", total=False, grand=False):
    cls = "pl-row" + (" total grand" if grand else " total" if total else "")
    dot = tpl.fill("render/dot.html", kind=kind) if kind else tpl.load("render/dot_none.html")
    src_html = tpl.fill("render/src.html", src=src) if src else ""
    return tpl.fill("render/pl_row.html",
                    cls=cls, dot=dot, name=name, src_html=src_html,
                    amt=_amt(impact, colored=(total or grand)))

def _pct_row(name, pct, src=""):
    """比率行（如税前利润率）：金额列显示百分数，不参与任何求和。pct=None → 灰显 —。"""
    src_html = tpl.fill("render/src.html", src=src) if src else ""
    txt = f"{pct:.1f}%" if pct is not None else "—"
    return tpl.fill("render/pct_row.html", name=name, src_html=src_html, txt=txt)

def _open_row(cat, name, impact):
    """可点大类行：点击弹出右侧抽屉看构成（不再就地展开、不顶下方图表）。"""
    return tpl.fill("render/open_row.html", cat=cat, name=name, amt=_amt(impact))

def _drow(name, impact, kind, src="", sub=False):
    """抽屉内明细行（始终展开、无需切换）。
    金额只显示绝对值：行名已带「加/减」语义，用户只看数额；主表利润影响仍走 _row/_open_row 带符号。"""
    cls = "pl-drow" + (" sub" if sub else "")
    dot = tpl.fill("render/dot.html", kind=kind) if kind else tpl.load("render/dot_none.html")
    src_html = tpl.fill("render/src.html", src=src) if src else ""
    return tpl.fill("render/drow.html",
                    cls=cls, dot=dot, name=_esc(name), src_html=src_html,
                    amt=_amt(abs(float(impact or 0))))

def _d_ledger(name, amount, src, fine_pairs, limit=8):
    """抽屉内台账叶子 + 其费用明细细类（平铺，不再二次点开）。"""
    out = _drow(name, -amount, "ledger", src)
    pairs = sorted(fine_pairs or [], key=lambda x: -x[1])
    for n, a in pairs[:limit]:
        out += _drow(n, -a, "", "", sub=True)
    rest = pairs[limit:]
    if rest:
        out += _drow(f"其他{len(rest)}项", -sum(a for _, a in rest), "", "", sub=True)
    return out

def _detail_block(cat, title, inner):
    return tpl.fill("render/detail_block.html",
                    cat=_esc(cat), title=_esc(title), inner=inner)

def render_pl_table(p, fine, unclassified_amt=None):
    """管理利润表（看端·领导视角）：行旁只留计算公式；运营备注/填数提示不展示（管理端数据页看）。"""
    e = p["expense"]; man = p["manual"]; led = p["ledger_expenses"]
    prod_manual = ["PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）"]
    # 主表：公式留 / 运营备注去
    rows = [_row("交付收入（不含税）", p["revenue_net"], "system", "交付金额÷1.06")]
    rows.append(_open_row("cost", "交付成本（生产成本）", -p["production_cost"]))
    rows.append(_row("管理毛利", p["gross_profit"], "", total=True))
    rows.append(_open_row("sales", "营销费用", -e["营销费用"]))
    rows.append(_open_row("admin", "管理费用", -e["管理费用"]))
    rows.append(_open_row("fixed", "固定运营费用", -e["固定运营费用"]))
    rows.append(_open_row("rd", "研发费用", -e["研发费用"]))
    rows.append(_open_row("fin", "财务费用", -e["财务费用"]))
    rows.append(_row("附加税费", -p["surtax"], "system", "净收入×6%×12%"))
    rows.append(_row("其他损益", p["other_pl"], "manual", ""))
    if unclassified_amt and unclassified_amt > 0:
        rows.append(_row("未计入费用（台账未填大类）", -unclassified_amt, "ledger", ""))
    rows.append(_row("税前利润", p["pretax_profit"], "",
                     "管理毛利−期间费用−附加税±其他", grand=True))
    # 陆总0714/A4#3：税前利润率（=税前利润÷交付收入；显示名原「税前利润率」）
    rows.append(_pct_row("税前利润率", p.get("pretax_margin_pct"), "税前利润÷交付收入"))

    # 抽屉：只列名目+金额，不堆「手填·默认0」类运营旁注
    # 抽屉行名不带「加/减」：用户只看名目与金额
    cost_inner = (_drow("系统直接成本", -p["system_direct_cost"], "system")
                  + _drow("系统内部译员", p["inhouse_cost"], "system")
                  + _drow("直接成本增值税", man.get("直接成本增值税", 0.0), "manual")
                  + "".join(_drow(n, -man[n], "manual") for n in prod_manual))
    details = "".join([
        _detail_block("cost", "交付成本（生产成本）构成", cost_inner),
        _detail_block("sales", "营销费用构成",
                      _drow("营销人力成本", -man["营销人力成本"], "manual")
                      + _d_ledger("市场费用", led["市场费用"], "", fine.get("市场费用"))),
        _detail_block("admin", "管理费用构成",
                      _drow("管理人力成本", -man["管理人力成本"], "manual")
                      + _d_ledger("管理费用", led["管理费用"], "", fine.get("管理费用"))),
        _detail_block("fixed", "固定运营费用构成",
                      _d_ledger("固定运营费用明细", led["固定运营费用"], "", fine.get("固定运营费用"))),
        _detail_block("rd", "研发费用构成",
                      _drow("研发人力成本", -man["研发人力成本"], "manual")
                      + _d_ledger("技术服务费", led["技术服务费"], "", fine.get("技术服务费"))),
        _detail_block("fin", "财务费用构成",
                      _d_ledger("财务费用", led["财务费用"], "", fine.get("财务费用"))
                      + _drow("财务费用补充", -man["财务费用补充"], "manual")),
    ])
    kinds = tpl.load("render/kinds.html")
    return tpl.fill("render/pl_table.html",
                    rows="".join(rows), kinds=kinds, details=details)

# ---------- 板块②-3 回款按月（整年，静态）+ 每月回款/下单比线 ----------
def _budget_tag(budget):
    """预算完成标签（卡头）：没填预算 → 空串（页面与无预算时代一分不差）。"""
    if not budget:
        return ""
    parts = []
    for key, name in (("receipt", "回款"), ("order", "下单")):
        b = budget.get(key)
        if b:
            p = b.get("pct")
            if p is None:
                pct = "—"
            elif p > 999:
                pct = f"{p:.0f}%"
            else:
                pct = f"{p:.1f}%"
            parts.append(tpl.fill("render/budget_tag_part.html",
                                  name=name, target=charts.fmt_wan(b["target"]), pct=pct))
    return tpl.fill("render/budget_tag.html", parts="　".join(parts)) if parts else ""

def _receipt_insight_totals(tot_o, tot_r, delivered_gross=None, budget=None,
                            show_delivered_unpaid=False):
    """回款右侧驾驶舱（A3·陆总#2）：①总下单/总回款首行 ②已交付未回款可隐藏
    ③回款占下单 ④年目标进度。金额由调用方传入，本函数只拼 HTML、零运算。"""
    tot_o = float(tot_o or 0.0)
    tot_r = float(tot_r or 0.0)
    gap = tot_o - tot_r  # 下单 − 回款：>0 表示尚待回款（含未交付）
    ytd_pct = (tot_r / tot_o * 100.0) if tot_o else None
    ytd_txt = f"{ytd_pct:.1f}%" if ytd_pct is not None else "—"
    bar_w = max(0.0, min(float(ytd_pct or 0), 100.0))
    gap_hint = "尚待回款" if gap > 0 else ("回款超下单" if gap < 0 else "持平")
    gap_num = charts.fmt_wan(abs(gap))

    hero = tpl.fill("render/rc_totals.html",
                    gap_hint=gap_hint, gap_num=gap_num,
                    tot_o=charts.fmt_wan(tot_o), tot_r=charts.fmt_wan(tot_r))
    recv = ""
    if show_delivered_unpaid and delivered_gross is not None:
        ar = float(delivered_gross) - tot_r
        ar_s = ("−" if ar < 0 else "") + charts.fmt_wan(abs(ar)) + "万"
        recv = tpl.fill("render/rc_recv.html", ar_s=ar_s)
    rate = tpl.fill("render/rc_rate.html",
                    ytd_txt=ytd_txt, bar_w=bar_w,
                    tot_o=charts.fmt_wan(tot_o), tot_r=charts.fmt_wan(tot_r))
    pills = ""
    bud = ""
    rb = (budget or {}).get("receipt") if budget else None
    ob = (budget or {}).get("order") if budget else None
    for key, title, b in (("receipt", "回款年目标", rb), ("order", "下单年目标", ob)):
        if not (b and b.get("target")):
            continue
        pct = b.get("pct")
        if pct is None:
            pct_txt = "—"
        elif pct > 999:
            pct_txt = f"{pct:.0f}%·目标偏小"
        else:
            pct_txt = f"{pct:.1f}%"
        bw = max(0.0, min(float(pct or 0), 100.0))
        bud += tpl.fill("render/rc_bud.html",
                        title=title, pct_txt=pct_txt, bw=bw,
                        target=charts.fmt_wan(b["target"]))
    return tpl.fill("render/rc_side.html", content=f"{hero}{recv}{rate}{pills}{bud}")

def _receipt_insight_panel(receipt_order_monthly, budget=None, delivered_gross=None,
                           show_delivered_unpaid=False):
    """回款右侧驾驶舱（全年按月加总版，兼容旧调用）。"""
    if not receipt_order_monthly:
        return tpl.load("render/rc_side_empty.html")
    tot_r = tot_o = 0.0
    for _label, rec, order, _ratio in receipt_order_monthly:
        tot_r += rec or 0.0
        tot_o += order or 0.0
    return _receipt_insight_totals(
        tot_o, tot_r, delivered_gross=delivered_gross, budget=budget,
        show_delivered_unpaid=show_delivered_unpaid)

def _receipt_insight_from_period(p, budget=None, show_delivered_unpaid=False):
    """单周期回款侧栏：用该周期已算好的 orders/receipts/revenue_gross（随 .pv 切，零运算）。"""
    return _receipt_insight_totals(
        p.get("orders"), p.get("receipts"),
        delivered_gross=p.get("revenue_gross"), budget=budget,
        show_delivered_unpaid=show_delivered_unpaid)

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

def render_receipts(receipt_order_monthly, budget=None, *, period_months_map=None,
                    year_key=None, delivered_gross=None, periods=None, default_key=None,
                    show_delivered_unpaid=False):
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
            _pv(k, dk, _receipt_insight_from_period(
                periods[k], budget if k == yk else None,
                show_delivered_unpaid=show_delivered_unpaid))
            for k in periods)
    else:
        side = _receipt_insight_panel(
            receipt_order_monthly, budget, delivered_gross=delivered_gross,
            show_delivered_unpaid=show_delivered_unpaid)
    rm_map = period_months_map or {}
    map_json = json.dumps(rm_map, ensure_ascii=False, separators=(",", ":"))
    return tpl.fill("render/rc_card.html",
                    yk=_esc(yk), map_json=_esc(map_json),
                    budget_tag=_budget_tag(budget),
                    chart=charts.receipt_order_chart(receipt_order_monthly, budget_month=budget_month),
                    side=side)

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
        meta = f'{it["count"]}笔'
        if share:
            meta += f'·{it["amount"] / total * 100:.0f}%' if total > 0 else "·—"
        rows.append(tpl.fill("render/rank_row.html",
                             i=i, title=_esc(it["name"]), name=_esc(it["name"]),
                             w=w, amt=_rank_amt(it["amount"]), meta=meta))
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
            more = tpl.fill("render/rank_more.html",
                            names=others["names"], amt=_rank_amt(others["amount"]),
                            count=others["count"])
        full = ""
        if embed_full and others:
            full_items = rk.get("full_items") or items
            full = tpl.fill("render/rank_full.html",
                            rows=_rank_rows_html(full_items, total))
        body = tpl.fill("render/rank_body.html", rows=rows_html, more=more, full=full)
    tag_html = tpl.fill("render/rank_tag.html", tag=_esc(tag)) if tag else ""
    return tpl.fill("render/rank_card.html",
                    kind=_esc(kind), title=title, tag_html=tag_html, body=body)

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
            seen.add(n); names.append(n)
    for src in (r_rk or {}).get("full_items") or (r_rk or {}).get("items") or []:
        n = src["name"]
        if n and n not in seen and n != "（未填）":
            seen.add(n); names.append(n)
    # 排序：按 max(下单,回款) 降序
    def score(n):
        return max(float((o_map.get(n) or {}).get("amount") or 0),
                   float((r_map.get(n) or {}).get("amount") or 0))
    names.sort(key=score, reverse=True)
    full = []
    for n in names:
        oa = float((o_map.get(n) or {}).get("amount") or 0)
        ra = float((r_map.get(n) or {}).get("amount") or 0)
        full.append({"name": n, "order": oa, "receipt": ra,
                     "order_disp": _rank_amt(oa), "receipt_disp": _rank_amt(ra)})
    items = full[:top]
    rest = full[top:]
    others = None
    if rest:
        others = {"names": len(rest), "order": round(sum(x["order"] for x in rest), 2),
                  "receipt": round(sum(x["receipt"] for x in rest), 2),
                  "order_disp": _rank_amt(sum(x["order"] for x in rest)),
                  "receipt_disp": _rank_amt(sum(x["receipt"] for x in rest))}
    mx = max((max(x["order"], x["receipt"]) for x in full), default=0) or 1
    for x in items:
        x["wo"] = max(x["order"] / mx * 100, 0)
        x["wr"] = max(x["receipt"] / mx * 100, 0)
    return {"items": items, "others": others, "full_items": full, "mx": mx}


def _dual_rows_html(items):
    if not items:
        return tpl.load("render/ev_empty.html")
    out = []
    for i, it in enumerate(items, 1):
        out.append(tpl.fill("render/dual_row.html",
                            i=i, title=_esc(it["name"]), name=_esc(it["name"]),
                            wo=it.get("wo") or 0, wr=it.get("wr") or 0,
                            o_amt=it.get("order_disp") or _rank_amt(it.get("order") or 0),
                            r_amt=it.get("receipt_disp") or _rank_amt(it.get("receipt") or 0)))
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
            more = tpl.fill("render/rank_more.html",
                            names=others["names"],
                            amt=f'下单{others.get("order_disp") or _rank_amt(others.get("order") or 0)} / 回款{others.get("receipt_disp") or _rank_amt(others.get("receipt") or 0)}',
                            count=others["names"])
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


def render_rankings(p, embed_full=False):
    """A6：下单与回款双血条两卡（按销售 / 按客户）；去掉按部门。"""
    rk = p.get("rankings") or {}
    s, e = p.get("range", ("", ""))
    dual_s = _merge_dual_rank(rk.get("orders_by_sales"), rk.get("receipts_by_sales"))
    dual_c = _merge_dual_rank(rk.get("orders_by_customer"), rk.get("receipts_by_customer"))
    return tpl.fill("render/dual_grid.html",
                    s=_esc(s), e=_esc(e),
                    sales=_dual_card("下单/回款 · 按销售", dual_s, "sales", embed_full=embed_full),
                    cust=_dual_card("下单/回款 · 按客户", dual_c, "customer", embed_full=embed_full))


# ---------- 板块③ 收入与毛利结构（确认口径，按客户/销售，随周期切）----------
def _margin_meta(mp):
    """系统成本率 meta：None（收入 0）→ 灰显「系统成本率 —」。
    陆总 0714 改叫「系统成本率」（=系统抓的项目成本÷交付收入）——生产环节大家习惯看成本率；
    只在利润表层才还原成"生产毛利"的利润概念。入参 mp=cost_pct。"""
    return f'系统成本率 {mp:.0f}%' if mp is not None else "系统成本率 —"

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
        rows.append(tpl.fill("render/profit_rank_row.html",
                             i=i, pname=_pname(it["name"]), w=w,
                             amt=_rank_amt(it["revenue"]), meta=_meta(it)))
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
            more = tpl.fill("render/profit_more.html",
                            names=others["names"], amt=_rank_amt(others["revenue"]),
                            meta=_meta(others))
        full = ""
        if embed_full and others:
            full_items = rk.get("full_items") or items
            full = tpl.fill("render/profit_full.html",
                            rows=_profit_rank_rows_html(full_items, show_meta=show_meta))
        body = tpl.fill("render/rank_body.html", rows=rows_html, more=more, full=full)
    return tpl.fill("render/profit_card.html",
                    dim=_esc(dim), title=title, tag=tag, body=body)

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
    return tpl.fill("render/profit_grid.html",
                    s=_esc(s), e=_esc(e),
                    cust=_profit_rank_card("收入 · 按客户", _conc_tag(cust), cust, "customer", embed_full=embed_full),
                    sale=_profit_rank_card("收入 · 按销售", _conc_tag(sale), sale, "sales", show_meta=False, embed_full=embed_full))

def build_dashboard_fragments(summary, cfg, logo_b64) -> dict:
    """B：整页渲染就绪碎片（全部显示串/HTML 段后端算好）。JS 只拼接，零金额运算。"""
    meta = summary["meta"]; P = summary["periods"]; FT = summary["expense_fine_type"]
    yk = meta["year_key"]
    all_keys = ([yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"]
                + meta["tab_groups"].get("区间", []))
    logo = tpl.fill("render/logo.html", src=logo_b64) if logo_b64 else ""
    unc = meta["unclassified"]["expense"]
    month_keys = meta["tab_groups"]["月"]
    budget = meta.get("budget")
    BUO = meta.get("bu_orders") or {}
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    kpi_views = "".join(
        _pv(k, yk, render_basic(k, P, meta["year"], month_keys, budget,
                                bu_orders=BUO.get(k), show_delivered_unpaid=show_ar))
        for k in all_keys)
    BP = summary.get("expense_by_profit_center", {})
    BD = summary.get("expense_by_department", {})
    donut_views = "".join(
        _pv(k, yk, render_expense_views(
            P[k], _fine_to_rows(FT.get(k) or {}), BP.get(k), BD.get(k)))
        for k in all_keys)
    unc_amt = float(unc.get("amount") or 0) if unc else 0.0
    pl_views = "".join(
        _pv(k, yk, render_pl_table(P[k], FT.get(k, {}), unclassified_amt=unc_amt if k == yk else None))
        for k in all_keys)
    profit_rank_views = "".join(_pv(k, yk, render_profit_rankings(P[k])) for k in all_keys)
    rank_views = "".join(_pv(k, yk, render_rankings(P[k])) for k in all_keys)
    hl = meta["current_month_label"].split("年")[1]
    rm_map = _period_months_map(summary)
    receipts_html = render_receipts(
        summary['receipt_order_monthly'], summary['meta'].get('budget'),
        period_months_map=rm_map, year_key=yk,
        periods=P, default_key=yk, show_delivered_unpaid=show_ar)
    receipts_budget = tpl.fill("render/period_receipts.html", html=receipts_html)
    trend_html = render_trend(summary['trend'], hl, period_months_map=rm_map, year_key=yk)
    return {
        "title": "甲骨易智能经营罗盘",
        "particles": PARTICLES_HTML,
        "logo": logo,
        "version": _title_version_html(),
        "generated_at": meta["generated_at"],
        "pw_modal": PW_MODAL_HTML,
        "period_bar": render_period_bar(summary),
        "kpi_views": kpi_views,
        "trend_html": trend_html,
        "donut_views": donut_views,
        "pl_views": pl_views,
        "profit_rank_views": profit_rank_views,
        "receipts_budget": receipts_budget,
        "daily_html": DAILY_HTML,
        "rank_views": rank_views,
        "drawer": DRAWER_HTML,
    }


def assemble_dashboard_html(frags: dict) -> str:
    """用碎片填充模板 → 完整 HTML（与历史 render_dashboard 逐字节一致）。"""
    body = tpl.fill("render/dashboard_body.html",
                    particles=frags["particles"], logo=frags["logo"], version=frags["version"],
                    generated_at=frags["generated_at"], pw_modal=frags["pw_modal"],
                    period_bar=frags["period_bar"], kpi_views=frags["kpi_views"],
                    trend_html=frags["trend_html"], donut_views=frags["donut_views"],
                    pl_views=frags["pl_views"], profit_rank_views=frags["profit_rank_views"],
                    receipts_budget=frags["receipts_budget"], daily_html=frags["daily_html"],
                    rank_views=frags["rank_views"], drawer=frags["drawer"])
    return tpl.fill("render/page_shell.html", title=frags.get("title") or "甲骨易智能经营罗盘", body=body)


def render_dashboard(summary, cfg, logo_b64):
    """兼容入口：碎片 → 组装（B 阶段后与 JS assemble 同源）。"""
    return assemble_dashboard_html(build_dashboard_fragments(summary, cfg, logo_b64))

# ---------- BU 分页（迭代 14 → 费用直记）：完整利润表 ----------
# 收入/成本：智云按销售过滤；费用：台账「利润归属中心」=本 BU 直记 + 可选公共池×比例；
# 手填：按 BU 范围（有填显示金额，无填标注待填）。严格保密：summary 已按本 BU 过滤。

def _bu_pending_row(name, note="—"):
    """待补数据行：金额位显示 — 而非 ¥0（不把"没有数"显示成"数是 0"）。"""
    return tpl.fill("render/bu_pending_row.html", name=_esc(name), note=_esc(note))

def render_bu_pl_table(p, alloc_meta=None, fine=None):
    """BU 版利润表（看端精简备注）：费用有数就显示；抽屉只列名目+金额；公式保留。"""
    alloc = alloc_meta or {}
    on = bool(alloc.get("enabled"))
    rdisp = alloc.get("ratio_disp") or ""
    exp = p.get("expense") or {}
    man = p.get("manual") or {}
    led = p.get("ledger_expenses") or {}
    exp_total = float(exp.get("total") or 0)
    has_fee = exp_total > 0.005 or any(float(led.get(c) or 0) > 0.005 for c in led)
    man_keys = ("营销人力成本", "管理人力成本", "研发人力成本", "财务费用补充",
                "PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失",
                "技术流量成本", "其他（生产成本）", "其他损益")
    has_manual = any(abs(float(man.get(k) or 0)) > 0.005 for k in man_keys)
    other_pl = float(p.get("other_pl") or 0)

    if on and rdisp:
        tag_note = f"含公共分摊 {rdisp}"
    elif has_fee:
        tag_note = "本BU直记"
    else:
        tag_note = ""

    fine = fine or {}
    alloc_added = p.get("alloc_added") or {}
    # 大类 → (抽屉key, 手填项, 台账类)；财务费用的手填是"补充"、挂台账行后面
    _GROUPS = (("sales", "营销费用", "营销人力成本", "市场费用"),
               ("admin", "管理费用", "管理人力成本", "管理费用"),
               ("fixed", "固定运营费用", None, "固定运营费用"),
               ("rd", "研发费用", "研发人力成本", "技术服务费"),
               ("fin", "财务费用", None, "财务费用"))

    rows = [_row("交付收入（不含税）", p["revenue_net"], "system", "交付金额÷1.06")]
    rows.append(_open_row("cost", "交付成本（生产成本）", -p["production_cost"]))
    rows.append(_row("管理毛利", p["gross_profit"], "", total=True))
    exp_details = []
    for cat_key, nm, man_key, led_cat in _GROUPS:
        v = float(exp.get(nm) or 0)
        if has_fee or abs(v) > 0.005:
            rows.append(_open_row(cat_key, nm, -v))
            alloc_amt = float(alloc_added.get(led_cat) or 0.0)
            direct_amt = round(float(led.get(led_cat) or 0.0) - alloc_amt, 2)
            inner = ""
            if man_key:
                inner += _drow(man_key, -float(man.get(man_key) or 0), "manual")
            inner += _d_ledger(led_cat, direct_amt, "", fine.get(led_cat))
            if nm == "财务费用":
                inner += _drow("财务费用补充", -float(man.get("财务费用补充") or 0), "manual")
            if alloc_amt > 0.005:
                inner += _drow("分摊自公共", -alloc_amt, "ledger")
            exp_details.append(_detail_block(cat_key, f"{nm}构成", inner))
        else:
            rows.append(_bu_pending_row(nm))
    rows.append(_row("附加税费", -p["surtax"], "system", "净收入×6%×12%"))
    if abs(other_pl) > 0.005 or has_manual:
        rows.append(_row("其他损益", other_pl, "manual", ""))
    else:
        rows.append(_bu_pending_row("其他损益"))
    pretax_src = "毛利−期间费用−附加税±其他"
    rows.append(_row("税前利润", p["pretax_profit"], "", pretax_src, grand=True))
    rows.append(_pct_row("税前利润率", p.get("pretax_margin_pct"), "税前利润÷交付收入"))

    prod_manual = ["PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）"]
    if has_manual:
        man_cost_html = "".join(
            _drow(n, -float(man.get(n) or 0), "manual") for n in prod_manual)
    else:
        man_cost_html = "".join(_drow(n, 0.0, "manual") for n in prod_manual)
    cost_inner = (_drow("系统直接成本", -p["system_direct_cost"], "system")
                  + _drow("系统内部译员", p["inhouse_cost"], "system")
                  + _drow("直接成本增值税", float(man.get("直接成本增值税") or 0), "manual")
                  + man_cost_html)
    details = _detail_block("cost", "交付成本构成", cost_inner) + "".join(exp_details)
    kinds = tpl.load("render/kinds.html")
    return (tpl.fill("render/pl_table.html",
                     rows="".join(rows), kinds=kinds, details=details), tag_note)

def render_bu_page(bu_name, summary, cfg, logo_b64):
    """单 BU 独立只读页（迭代22·D：口径与整体页全对齐，只是数按本 BU 过滤）：
    周期选择 + KPI + 趋势图 + 利润表（可下钻）+ 费用构成（大类/类别）+ 收入毛利结构 + 回款情况 + 排名 + 导出。
    铁律12：不含 /api/daily、/api/profit_ranking；「其余」用预渲染全量本地弹窗；回款侧栏随周期 .pv 切。"""
    meta = summary["meta"]; P = summary["periods"]; FT = summary.get("expense_fine_type") or {}
    yk = meta["year_key"]
    all_keys = ([yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"]
                + meta["tab_groups"].get("区间", []))
    logo = tpl.fill("render/logo.html", src=logo_b64) if logo_b64 else ""
    alloc = meta.get("public_allocation") or {"enabled": False}
    pl_parts, tag_note = [], ""
    for k in all_keys:
        pl_html, tag_note = render_bu_pl_table(P[k], alloc, fine=FT.get(k))
        pl_parts.append(_pv(k, yk, pl_html))
    pl_views = "".join(pl_parts)
    donut_views = "".join(_pv(k, yk, render_bu_expense_views(P[k], FT.get(k))) for k in all_keys)
    # embed_full：其余可展开且不调全公司 API
    profit_rank_views = "".join(
        _pv(k, yk, render_profit_rankings(P[k], embed_full=True)) for k in all_keys)
    rank_views = "".join(
        _pv(k, yk, render_rankings(P[k], embed_full=True)) for k in all_keys)
    name = _esc(bu_name)

    month_keys = meta["tab_groups"]["月"]
    budget = meta.get("budget")
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    kpi_views = "".join(
        _pv(k, yk, render_basic(k, P, meta["year"], month_keys, budget,
                                show_delivered_unpaid=show_ar))
        for k in all_keys)
    hl = meta["current_month_label"].split("年")[1]
    # 周期→月份映射一处生成，回款卡 + 趋势图共用
    rm_map = _period_months_map(summary)
    # 回款：柱图全年+高亮；侧栏各周期预渲染（本 BU 过滤后的数）
    receipts_html = render_receipts(
        summary['receipt_order_monthly'], budget,
        period_months_map=rm_map, year_key=yk,
        periods=P, default_key=yk, show_delivered_unpaid=show_ar)
    trend_html = render_trend(summary['trend'], hl, period_months_map=rm_map, year_key=yk)
    from urllib.parse import quote as _q
    export_url = f"/bu/{_q(bu_name)}/export.png"
    pl_tag = tpl.fill("render/bu_pl_tag.html", note=_esc(tag_note)) if tag_note else ""

    body = tpl.fill("render/bu_body.html",
                    particles=PARTICLES_HTML, logo=logo, name=name,
                    version=_title_version_html(), generated_at=meta['generated_at'],
                    export_url=export_url, pw_modal=PW_MODAL_HTML,
                    period_bar=render_period_bar(summary), kpi_views=kpi_views,
                    trend_html=trend_html, donut_views=donut_views,
                    pl_tag=pl_tag, pl_views=pl_views,
                    profit_rank_views=profit_rank_views, receipts_html=receipts_html,
                    rank_views=rank_views, drawer=DRAWER_HTML, rk_modal=RK_MODAL_HTML)
    return tpl.fill("render/page_shell.html",
                    title=f"甲骨易智能经营罗盘 · {name}", body=body)
