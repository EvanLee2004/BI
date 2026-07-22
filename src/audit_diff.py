#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置变更留痕 / 体检理由 / 抓取 banner（54.13 从 server 纯搬家）。"""
from __future__ import annotations

from pathlib import Path

import db
import loaders
from app_state import STATIC_DIR

def _audit(cfg, root, account, changes) -> None:
    """写配置变更留痕。changes=(类别,摘要) 或其列表；空摘要跳过。摘要绝不含密码明文（调用方脱敏）。"""
    if not changes:
        return
    if isinstance(changes, tuple):
        changes = [changes]
    conn = db.connect(cfg, root)
    try:
        for cat, summ in changes:
            db.log_config_change(conn, account, cat, summ)
    finally:
        conn.close()

def _join_summary(prefix: str, items: list[str], cap: int = 8) -> str:
    """把多条变更并成一句人读摘要；超过 cap 条只列前 cap 条 + 总数（防超长）。"""
    if len(items) <= cap:
        return prefix + "；".join(items)
    return prefix + "；".join(items[:cap]) + f"；等共 {len(items)} 项"

def _sale_map(bus: list) -> dict:
    m = {}
    for b in bus:
        for s in b.get("销售") or []:
            m[str(s).strip()] = b["name"]
    return m


def _fmt_ratio(v) -> str:
    return "空" if v is None else f"{v:g}%"


def _diff_bu_alloc_lines(old_bus, new_bus, old_alloc: bool, new_alloc: bool) -> list[str]:
    alloc_lines = []
    if bool(old_alloc) != bool(new_alloc):
        alloc_lines.append(f"公共费用分摊 {'开' if new_alloc else '关'}←{'开' if old_alloc else '关'}")
    orat = {b["name"]: b.get("分摊比例") for b in old_bus}
    nrat = {b["name"]: b.get("分摊比例") for b in new_bus}
    for nm in sorted(set(orat) | set(nrat)):
        o, n = orat.get(nm), nrat.get(nm)
        if o != n:
            alloc_lines.append(f"{nm} {_fmt_ratio(o)}→{_fmt_ratio(n)}")
    return alloc_lines


def _diff_bu_config(old_bus: list, new_bus: list, old_alloc: bool = False, new_alloc: bool = False) -> list:
    """销售归属/BU 结构/分摊比例变化 → [(类别,摘要)]（old/new 均规范化 bus 列表）。"""
    om, nm = _sale_map(old_bus), _sale_map(new_bus)
    moves = [
        f"{s} {om.get(s) or '未归属'}→{nm.get(s) or '未归属'}"
        for s in sorted(set(om) | set(nm))
        if om.get(s) != nm.get(s)
    ]
    onames = {b["name"] for b in old_bus}
    nnames = {b["name"] for b in new_bus}
    oown = {b["name"]: "、".join(b.get("负责人") or []) for b in old_bus}
    nown = {b["name"]: "、".join(b.get("负责人") or []) for b in new_bus}
    struct = (
        [f"新增 BU {x}" for x in sorted(nnames - onames)]
        + [f"删除 BU {x}" for x in sorted(onames - nnames)]
        + [
            f"{x} 负责人改为「{nown.get(x) or '（空）'}」"
            for x in sorted(nnames & onames)
            if oown.get(x) != nown.get(x)
        ]
    )
    out = []
    if moves:
        out.append(("销售归属", _join_summary("销售归属：", moves)))
    if struct:
        out.append(("BU配置", _join_summary("BU配置：", struct)))
    alloc_lines = _diff_bu_alloc_lines(old_bus, new_bus, old_alloc, new_alloc)
    if alloc_lines:
        out.append(("分摊", _join_summary("分摊：", alloc_lines)))
    return out

def _diff_accounts(old_accs: list, new_accs: list) -> list:
    """账号增删改（含改权限/改密码/改显示名）→ [(账号,摘要)]。密码只记「改密码」不记值。"""
    om = {a["账号"]: a for a in old_accs}
    nm = {a["账号"]: a for a in new_accs}
    lines = [f"新增 {a}（{nm[a].get('权限')}）" for a in sorted(set(nm) - set(om))]
    lines += [f"删除 {a}" for a in sorted(set(om) - set(nm))]
    for a in sorted(set(om) & set(nm)):
        o, n = om[a], nm[a]
        chg = []
        if o.get("权限") != n.get("权限"):
            chg.append(f"权限 {o.get('权限')}→{n.get('权限')}")
        # 明文为真相源；只记「改密码」不记值（任务书64·P）
        if str(o.get("密码") or "") != str(n.get("密码") or "") or int(o.get("密码版本") or 0) != int(
            n.get("密码版本") or 0
        ):
            chg.append("改密码")
        if (o.get("显示名") or "") != (n.get("显示名") or ""):
            chg.append("改显示名")
        if chg:
            lines.append(f"{a} " + "、".join(chg))
    return [("账号", _join_summary("账号：", lines))] if lines else []

def _manual_items_json(cfg: dict | None = None) -> str:
    """手填项目名列表 JSON（注入管理端 JS；与 config.manual_items 同步）。"""
    import json as _json

    items = [it["name"] for it in (cfg or {}).get("manual_items") or []] or [
        "营销人力成本",
        "管理人力成本",
        "研发人力成本",
        "财务费用补充",
        "PM人力成本",
        "VM人力成本",
        "实际内部译员成本",
        "税费损失",
        "技术流量成本",
        "其他（生产成本）",
        "其他损益",
    ]
    return _json.dumps(items, ensure_ascii=False, separators=(",", ":"))

def _admin_page(_dash_html: str, summary: dict, cfg: dict | None = None) -> str:
    """管道跑通后标记「管理端可进完整台」（写入 has_data；兼容旧键 admin_html）。

    任务书65·L1/L2：不再生成/依赖 legacy 整页 HTML。签名保留兼容历史调用。
    """
    _ = (_dash_html, summary, cfg)
    return "ready"

def _bootstrap_page() -> str:
    """首次部署引导页（F-02）：仅 static/admin/bootstrap.html。"""
    p = STATIC_DIR / "admin" / "bootstrap.html"
    if not p.is_file():
        raise FileNotFoundError(f"缺少引导页：{p}")
    return p.read_text(encoding="utf-8")

def admin_ui_source() -> str:
    """供测试搜锚点：Vue 管理端源码 + 引导页拼接（任务书65 单轨后；非运行路径）。"""
    from pathlib import Path

    parts: list[str] = []
    # 引导页仍在 static
    boot = STATIC_DIR / "admin" / "bootstrap.html"
    if boot.is_file():
        parts.append(boot.read_text(encoding="utf-8"))
    # Vue 管理端
    admin_src = Path(__file__).resolve().parent.parent / "frontend" / "src" / "admin"
    if admin_src.is_dir():
        for p in sorted(admin_src.rglob("*")):
            if p.suffix in (".vue", ".ts", ".css", ".js") and p.is_file():
                try:
                    parts.append(p.read_text(encoding="utf-8"))
                except OSError:
                    pass
    return "\n".join(parts)

def _run_reasons_fetch(report: dict, reasons: list[str]) -> None:
    """抓数失败类 reasons（红优先列「哪路本次未抓到」）。同名控件只在 info，不在此。"""
    fetch = report.get("fetch", {}) or {}
    st = fetch.get("status")
    if st == "no_source":
        reasons.append("收单台账无可用数据源（共享路径与本地副本都没有）→ 判红")
    elif st and st not in ("fetched", "skipped", "skipped_no_share"):
        det = (fetch.get("detail") or "")[:80]
        reasons.append(f"收单台账本次未抓到（{st}：{det}）→ 判红" if det else f"收单台账本次未抓到（{st}）→ 判红")
    for src, zv in (report.get("fetch_zhiyun") or {}).items():
        if not isinstance(zv, dict) or str(src).startswith("_"):
            continue
        zst = zv.get("status")
        if zst and zst not in ("fetched", "skipped", "skipped_no_share"):
            reasons.append(f"智云·{src} 本次未抓到（{zst}：{(zv.get('detail') or '')[:80]}）→ 判红")
        for w in zv.get("warnings") or []:
            # 骤降等业务提醒（黄）；同名控件已只进 info，不会出现在 warnings
            reasons.append(f"智云·{src}：{w}")


def _run_reasons_adjust_db_disk(report: dict, reasons: list[str]) -> None:
    adj = report.get("adjust", {}) or {}
    if adj.get("expired", 0):
        reasons.append(f"{adj['expired']} 条调整「过期疑似」（源头已改、调整未套用）→ 去『异常处理·数据修正』看")
    if adj.get("missing", 0):
        reasons.append(
            f"{adj['missing']} 条调整定位键失配未套用（源头行删了/改了金额，剔除或改值没生效）→ 去『异常处理·数据修正』人工复核"
        )
    # 任务书66·D：定位键重复不进 run_reasons（不驱动黄灯）；信息见 report.info / health.info
    dbc = report.get("db_check") or {}
    if dbc and not dbc.get("ok", True):
        reasons.append(f"数据库 quick_check 异常：{dbc.get('detail') or 'unknown'} → 判红")
    disk = report.get("disk") or {}
    if disk.get("red"):
        fr = disk.get("free_ratio")
        if isinstance(fr, float):
            reasons.append(f"数据盘剩余不足（{fr:.0%} < {float(disk.get('min_ratio') or 0.1):.0%}）→ 判红")
        else:
            reasons.append("数据盘剩余不足 → 判红")
    bak = report.get("backup") or {}
    if bak.get("status") == "error" or bak.get("ok") is False:
        reasons.append(f"每日备份失败：{bak.get('detail') or bak.get('status')}")
    if (report.get("zhiyun_login_cooldown") or {}).get("active"):
        reasons.append("智云登录冷却中（凭据疑似失效，需人工检查）→ 判红")


def _run_reasons(report: dict) -> list[str]:
    """从最近一次管道运行日志（体检JSON=report）推导"为啥黄/红"。
    与 ingest._log_run 方案 B 一致：红=应抓源本次未抓到/硬故障；黄=抓齐后的业务提醒。
    注意：这是「管道运行」信号（黄/红），与「数据体检」的未填分类等（警）是两套，别糊在一起。"""
    report = report or {}
    reasons: list[str] = []
    _run_reasons_fetch(report, reasons)
    _run_reasons_adjust_db_disk(report, reasons)
    # 备份成功不写 run_reasons（避免绿时顶栏堆字）；状态在体检 JSON backup 字段，管理端可查
    return reasons

_ZY_BANNER_NAMES = {
    "orders": "智云·下单",
    "receipts": "智云·回款",
    "project_detail": "智云·项目明细",
    "inhouse": "智云·内部译员",
}

_ZY_FILE_KEYS = {
    "orders": "orders",
    "receipts": "receipts",
    "project_detail": "project_detail_stem",  # 实际文件由 readers 解析；横幅用 mtime 时退回目录内匹配
    "inhouse": "inhouse",
}


def _file_as_of_label(path: Path) -> str:
    """本地文件修改时间 →「M月D日 HH:MM」；无文件→「上次本地」。"""
    try:
        if path and path.exists():
            import datetime as _dt

            dt = _dt.datetime.fromtimestamp(path.stat().st_mtime)
            return f"{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
    except OSError:
        pass
    return "上次本地"


def _short_fetch_reason(detail: str | None, limit: int = 72) -> str:
    """横幅短原因：去换行、截断，勿整段堆栈。"""
    d = " ".join(str(detail or "").split())
    if not d:
        return "未知原因"
    if len(d) > limit:
        return d[: limit - 1] + "…"
    return d


def build_fetch_fallback_banners(report: dict, cfg: dict, root=None) -> list[dict]:
    """2.2.8：任一源 local_fallback/no_source → 横幅「本次未抓到」（禁止「今日」歧义）。
    返回 [{source, status, as_of, text}, …]；全部 fetched 或无报告 → []。"""
    report = report or {}
    banners: list[dict] = []
    ddir = loaders.data_dir(cfg, root)
    files = cfg.get("files") or {}

    def _add(name: str, status: str | None, path: Path | None, detail: str | None = None):
        if not status or status in ("fetched", "skipped", "skipped_no_share"):
            return
        as_of = _file_as_of_label(path) if path else "上次本地"
        short = _short_fetch_reason(detail)
        if status == "no_source":
            text = f"⚠ {name}本次未抓到：{short}，且无本地可用文件"
        else:
            text = f"⚠ {name}本次未抓到：{short}。已沿用本地文件（{as_of}）"
        banners.append({"source": name, "status": status, "as_of": as_of, "text": text})

    fetch = report.get("fetch") or {}
    if isinstance(fetch, dict) and fetch.get("status"):
        led = ddir / files.get("ledger", "收单台账.xlsx")
        _add("收单台账", fetch.get("status"), led, fetch.get("detail"))

    for src, zv in (report.get("fetch_zhiyun") or {}).items():
        if not isinstance(zv, dict) or str(src).startswith("_"):
            continue
        st = zv.get("status")
        label = _ZY_BANNER_NAMES.get(src, f"智云·{src}")
        # 本地副本路径：orders/receipts/inhouse 为 xlsx 文件名；project_detail 为 stem
        fname = files.get(src) or files.get(_ZY_FILE_KEYS.get(src, src))
        path = None
        if fname:
            p = ddir / fname
            if p.exists():
                path = p
            else:
                # stem 如「项目明细」→ 找 项目明细*.xlsx
                cands = sorted(ddir.glob(f"{fname}*.xlsx")) if not str(fname).endswith(".xlsx") else []
                path = cands[-1] if cands else p
        _add(label, st, path, zv.get("detail"))
    return banners

