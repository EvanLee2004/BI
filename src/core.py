#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心生成流程（run.py 批处理 与 server.py 服务 共用）：跑更新管道 → 算 summary → 渲染 HTML。
独立成模块以免 run↔server 循环导入。"""
from __future__ import annotations

import bu
import profit
import render
import charts
import assets
import db
import ingest


def _assigned_sales(bucfg) -> set[str]:
    """所有 BU 名单里的销售名（去空白去空）。未配置 → 空集。"""
    out: set[str] = set()
    for b in (bucfg or {}).get("bus", []):
        for s in b.get("销售") or []:
            s = str(s).strip()
            if s:
                out.add(s)
    return out


def _unassigned_wan(v: float) -> str:
    """未归属金额展示串（万，负数全角−；服务端算好=铁律2）。"""
    return "¥" + ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"


def unassigned_snapshot(cfg, conn, today, root=None) -> dict:
    """管理端 A3 快照（不依赖 summary）：未归属人数 + 当年未归属下单额展示串。
    未归属人数=四源出现、非空、不在任何 BU；金额=当年（含销售空行）未归属下单额（精确差额）。"""
    import datetime
    assigned = _assigned_sales(bu.load_bu_config(cfg, root))
    people = db.list_salespeople(conn)
    n = sum(1 for p in people if p["name"] not in assigned)
    unassigned = [r for r in db.load_orders(cfg, conn)
                  if str(r.get("销售") or "").strip() not in assigned]
    amt = profit.compute_orders(unassigned, cfg["columns"],
                                datetime.date(today.year, 1, 1), datetime.date(today.year, 12, 31))
    return {"unassigned_count": n, "unassigned_orders_disp": _unassigned_wan(amt)}


def attach_unassigned(cfg, conn, today, summary, root=None) -> None:
    """A3 未归属显式提示：把「未归属人数 + 每周期未归属下单金额展示串」挂进 summary.meta.unassigned。
    人数=四源出现过、非空、不在任何 BU 名单的销售数（与管理端归属池同口径）；N=0 → 整体页/管理端都不渲染该行。
    金额=每周期未归属销售（含销售空行）下单额，随周期预渲染供前端零运算切换。"""
    bucfg = bu.load_bu_config(cfg, root)
    if not bucfg:
        # BU 分页未启用（没配任何 BU）→ 不提示、不判黄（整体页入口条本身也不出现）；
        # 管理端归属页仍显示真实未归属（走 unassigned_snapshot，那页正是用来配的）。
        summary.setdefault("meta", {})["unassigned"] = {"count": 0, "by_period": {}}
        return
    assigned = _assigned_sales(bucfg)
    people = db.list_salespeople(conn)                       # [{name(TRIM), rows}]
    n = sum(1 for p in people if p["name"] not in assigned)
    by_amt = profit.compute_unassigned_orders_by_period(
        db.load_orders(cfg, conn), assigned, cfg["columns"], today)
    summary.setdefault("meta", {})["unassigned"] = {
        "count": n,
        "by_period": {k: _unassigned_wan(v) for k, v in by_amt.items()},
    }


def alloc_context(cfg, conn, today, root=None):
    """公共费用按月分摊上下文（迭代20）。返回 None=没有任何比例记录（不分摊）；否则
    {public_month_led:{(y,m):{5类:额}}, ratios:{'YYYY-MM':{BU:比例%}}, bu_names:[...],
     warnings:[孤儿BU提示…], month_total(month)->float}。"""
    # 陆总0714：比例默认沿用最近一次填写月（改了从当月生效）——计算一律用「生效比例」；
    # 孤儿 BU 告警仍扫原始填写记录，避免同一条错误被沿用后逐月重复报
    raw = db.load_alloc_ratios(conn)
    ratios = db.effective_alloc_ratios(conn, today.year, today.month)
    if not ratios:
        return None
    lh, lr = db.load_ledger(cfg, conn)
    if not lh:
        return None
    import columns as _columns
    import periods as _periods
    import datetime as _dt
    lcols = _columns.resolve_ledger_columns(lh)
    public_rows = profit.filter_ledger_rows_by_pc(lh, lr, {"公共"})
    public_month_led: dict[tuple[int, int], dict] = {}
    for m in range(1, today.month + 1):
        start = _dt.date(today.year, m, 1)
        end = _dt.date(today.year, m + 1, 1) - _dt.timedelta(days=1) if m < 12 else _dt.date(today.year, 12, 31)
        led, _ = profit.compute_ledger_expenses(public_rows, today.year, start, end, cfg, lcols)
        public_month_led[(today.year, m)] = led
    bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
    bu_names = [b["name"] for b in bucfg["bus"]]
    warnings = []
    known = set(bu_names)
    for month, r in sorted(raw.items()):
        orphans = [b for b in r if b not in known]
        if orphans:
            warnings.append(f"{month} 分摊比例含未知 BU：{'、'.join(orphans)}（未生效，请到设置核对 BU 名）")
    return {"public_month_led": public_month_led, "ratios": ratios,
            "bu_names": bu_names, "warnings": warnings}


def attach_allocation_to_summary(cfg, conn, today, summary, root=None, ctx=None):
    """把按月分摊套进全公司 summary 的「构成·按业务BU」视图 + 体检警告（迭代20·防两处真相）。
    只挪归属不改总额：全公司利润表/税前一分不变（回归红线守）。"""
    ctx = ctx if ctx is not None else alloc_context(cfg, conn, today, root)
    if not ctx:
        return
    alloc = profit.alloc_amounts_by_period(
        ctx["public_month_led"], ctx["ratios"], ctx["bu_names"], today)
    BP = summary.get("expense_by_profit_center") or {}
    for key, per_bu in alloc.items():
        if key in BP and BP[key]:
            BP[key] = profit.apply_alloc_to_pc_view(BP[key], per_bu)
    health = (summary.get("meta") or {}).get("health")
    if health is not None and ctx["warnings"]:
        health.setdefault("warnings", []).extend(ctx["warnings"])
    summary.setdefault("meta", {})["monthly_allocation"] = {
        "months": sorted(ctx["ratios"].keys()), "bu_names": ctx["bu_names"]}


def attach_unknown_pc_warnings(cfg, conn, today, summary, root=None) -> None:
    """迭代21：台账「利润归属中心」未知名 → 体检 warnings（只加警告不改算数）。
    没配任何 BU（配置不存在/为空）时跳过——BU 功能未启用不该报警。"""
    bucfg = bu.load_bu_config(cfg, root)
    if not bucfg or not bucfg.get("bus"):
        return
    bu_names = [b.get("name") for b in bucfg["bus"] if str(b.get("name") or "").strip()]
    if not bu_names:
        return
    lh, lr = db.load_ledger(cfg, conn)
    if not lh:
        return
    import columns as _columns
    lcols = _columns.resolve_ledger_columns(lh)
    items = profit.scan_unknown_profit_centers(
        lr, today.year, lcols, cfg, bu_names, year=today.year)
    warns = profit.unknown_pc_warnings(items)
    if not warns:
        return
    health = (summary.get("meta") or {}).setdefault("health", {})
    health.setdefault("warnings", []).extend(warns)
    # 管理端 BU 卡用：服务端算好显示串（原文名已在 warning 文案里；此处给清单钩子）
    summary.setdefault("meta", {})["unknown_profit_centers"] = items


def attach_bu_orders(cfg, conn, today, summary, root=None) -> None:
    """陆总0714·C1：下单 KPI 卡展示三大 BU 下单进度（虚线=年目标、实线=达成）。
    每周期每 BU：期内下单额 + 全年累计/BU 年目标完成率（目标读该 BU 业绩目标·元）。
    挂 summary.meta.bu_orders={周期key:[{name,amount,year_amount,target,pct}…]}；
    只挂全公司 summary——BU 页绝不带其他 BU 数据（铁律12）。没配 BU → 不挂。"""
    bucfg = bu.load_bu_config(cfg, root)
    if not bucfg or not bucfg.get("bus"):
        return
    import periods as _periods
    orders = db.load_orders(cfg, conn)
    cols = cfg["columns"]
    ranges = _periods.all_period_ranges(today)
    yk = f"{today.year}年"
    per_bu = []
    for b in bucfg["bus"]:
        rows = profit.filter_rows_by_sales(orders, set(b.get("销售") or []))
        bud = db.load_budget(conn, scope=b["name"])
        target = ((bud.get(str(today.year)) or {}).get("下单年预算"))  # 元；未填=None
        per_bu.append((b["name"], rows, float(target) if target else None))
    out: dict[str, list] = {}
    for key, (_label, start, end, _grp) in ranges.items():
        out[key] = [{"name": name, "amount": profit.compute_orders(rows, cols, start, end),
                     "target": target} for name, rows, target in per_bu]
    year_amounts = {d["name"]: d["amount"] for d in out.get(yk, [])}
    for lst in out.values():
        for d in lst:
            ya = year_amounts.get(d["name"], 0.0)
            d["year_amount"] = ya
            d["pct"] = round(ya / d["target"] * 100.0, 1) if d["target"] else None
    summary.setdefault("meta", {})["bu_orders"] = out
    # C2：板块④「下单·按部门」→「下单·按BU」（销售→BU 映射聚合；未归属销售=（未归属）置底）
    sales_map = {}
    for b in bucfg["bus"]:
        for s in (b.get("销售") or []):
            sales_map.setdefault(str(s).strip(), b["name"])

    def _bu_of(row):
        return sales_map.get(str(row.get("销售") or "").strip(), "")

    for key, (_label, start, end, _grp) in ranges.items():
        p = summary["periods"].get(key)
        if not p or "rankings" not in p:
            continue
        p["rankings"]["orders_by_bu"] = profit.compute_ranking(
            orders, "销售", cols["order_amount"], cols["order_date"], start, end,
            empty_label="（未归属）", name_of=_bu_of)


def summary_from_conn(cfg, conn, today):
    """计算层只吃库：标准表 + 手填表 → summary（profit 不再自己扫文件）。
    迭代20：有按月分摊比例时，「构成·按业务BU」视图跟着分摊挪（总额不变）。
    迭代21：未知归属中心挂体检警告。"""
    s = profit.build_summary(
        cfg, db.load_project_detail(cfg, conn), db.load_orders(cfg, conn),
        db.load_receipts(cfg, conn), db.load_inhouse(cfg, conn),
        *db.load_ledger(cfg, conn), today.year, today,
        manual_raw=db.load_manual(cfg, conn), budget_raw=db.load_budget(conn),
        dept_budget_raw=db.load_dept_budget(conn),
        detax_rates=db.load_detax_rates(conn))   # 费用去税（陆总0714·默认空=不去税）
    attach_allocation_to_summary(cfg, conn, today, s)
    attach_unknown_pc_warnings(cfg, conn, today, s)
    attach_bu_orders(cfg, conn, today, s)   # 陆总0714·C1/C2：下单卡 BU 进度 + 下单排名按 BU
    return s


def build_bu_pages(cfg, conn, today, logo_b64, root=None) -> dict[str, dict]:
    """BU 分页（迭代 14·v7.9 账号制 · 迭代17 分摊）：读 BU 配置 → 每 BU 按销售名单过滤四源行
    → 独立 summary（分摊开时注入全公司台账公共×比例）→ 独立 HTML。
    返回 {BU名: {"name": BU名, "html": 页面}}；没配置/配置无效 → {}（功能不启用，主看板照旧）。
    严格保密由此保证：每页只吃本 BU 过滤后的行，渲染层拿不到其他 BU 的任何数据。"""
    bucfg = bu.load_bu_config(cfg, root)
    if not bucfg:
        return {}
    project = db.load_project_detail(cfg, conn)
    orders = db.load_orders(cfg, conn)
    receipts = db.load_receipts(cfg, conn)
    inhouse = db.load_inhouse(cfg, conn)
    # 迭代20：分摊改按月比例（manual_分摊比例表）；BU配置.json 旧静态比例已停用不再消费
    lh, lr = db.load_ledger(cfg, conn)
    ctx = alloc_context(cfg, conn, today, root)
    pages: dict[str, dict] = {}
    for b in bucfg["bus"]:
        bu_budget = db.load_budget(conn, scope=b["name"])  # 该 BU 业务目标（无则空）
        bu_name = b["name"]
        # 直记：利润归属中心归一后等于本 BU 名的台账行
        direct_rows = profit.filter_ledger_rows_by_pc(lh, lr, {bu_name}) if lh else []
        bu_manual = db.load_manual_scope(cfg, conn, bu_name)
        s = profit.build_bu_summary(
            cfg, project, orders, receipts, inhouse, today, set(b["销售"]),
            budget_raw=bu_budget or None,
            ledger_header=lh if lh else None,
            ledger_rows=direct_rows,
            ledger_year=today.year,
            manual_raw=bu_manual,
            bu_name=bu_name)
        if ctx:
            profit.apply_public_expense_allocation_monthly(
                s, ctx["public_month_led"], ctx["ratios"], bu_name, today)
        # summary 一并挂上：v1.4 JSON API /api/v1/cockpit/bu 只序列化、不算账（计算仍是上面 build_bu_summary）
        pages[b["name"]] = {"name": b["name"],
                            "html": render.render_bu_page(b["name"], s, cfg, logo_b64),
                            "summary": s}
    return pages


def generate(cfg, today, trigger="manual"):
    """跑一次更新管道 → 算 summary → 渲染 HTML（主页 + BU 分页）→ 存当日页面快照（历史回看用）。
    返回 (summary, html, ing报告, bu_pages)。"""
    conn = db.connect(cfg)
    ing = ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger=trigger,
                              archive_backups=True)
    summary = summary_from_conn(cfg, conn, today)
    logo = assets.load_logo_base64(cfg)
    bu_pages = build_bu_pages(cfg, conn, today, logo)
    attach_unassigned(cfg, conn, today, summary)
    conn.close()
    html = render.render_dashboard(summary, cfg, logo)
    try:  # 页面快照失败（磁盘满等）不影响出页面
        ing["page_snapshot"] = ingest.archive.snapshot_page(cfg, html, today)
    except OSError as e:
        ing["page_snapshot"] = {"status": "error", "detail": str(e)}
    return summary, html, ing, bu_pages
