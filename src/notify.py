#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机告警（2.6.4）：logging + 告警.log，零外发。

禁止飞书/webhook/邮件。告警落盘见 alert_store。
2.6.8 T1：local_fallback 必须说人话（源名 + 本地副本日期），禁止「体检红：红」。
"""
from __future__ import annotations

import logging

log = logging.getLogger("kanban.notify")


def _pipeline_reasons(report: dict) -> list[str]:  # noqa: C901
    """从管道 report 抽人话原因列表（可单测）。"""
    report = report or {}
    reasons: list[str] = []
    if (report.get("disk") or {}).get("red"):
        reasons.append("磁盘剩余不足")
    fetch = report.get("fetch") or {}
    fst = fetch.get("status")
    if fst == "no_source":
        reasons.append("收单台账无可用数据源（共享与本地都没有）")
    elif fst == "local_fallback":
        # 2.6.8 T1：必须点名源 + 本地副本时间
        src = fetch.get("source") or "收单台账"
        as_of = fetch.get("local_as_of_cn") or fetch.get("local_as_of") or ""
        data_end = fetch.get("data_as_of_cn") or as_of or "未知"
        if as_of:
            reasons.append(
                f"{src}共享盘不可达，用的是 {as_of} 的本地副本（数据止于 {data_end}）"
            )
        else:
            det = (fetch.get("detail") or "")[:160]
            reasons.append(det or f"{src}共享盘不可达，已沿用本地旧台账")
    elif fst and fst not in ("fetched", "skipped", "skipped_no_share"):
        det = (fetch.get("detail") or "")[:120]
        reasons.append(f"收单台账抓取异常（{fst}：{det}）" if det else f"收单台账抓取异常（{fst}）")
    if not (report.get("db_check") or {}).get("ok", True):
        reasons.append("数据库 quick_check 异常")
    # 智云源 local_fallback / no_source
    for src, zv in (report.get("fetch_zhiyun") or {}).items():
        if not isinstance(zv, dict) or str(src).startswith("_"):
            continue
        zst = zv.get("status")
        if zst == "local_fallback":
            reasons.append(f"智云·{src} 本次未抓到，沿用本地旧文件")
        elif zst == "no_source":
            reasons.append(f"智云·{src} 无可用数据")
        elif zst == "empty_fetch":
            reasons.append(f"智云·{src} 抓到 0 行")
    return reasons


def format_pipeline_alert_detail(report: dict) -> str:
    """体检红告警正文（不含「体检红：」前缀）。永远不许只剩裸「红」。"""
    reasons = _pipeline_reasons(report)
    if reasons:
        return "；".join(reasons)
    # 兜底：摘要关键字段，禁止「体检红：红」
    bits = []
    fetch = report.get("fetch") or {}
    if fetch.get("status"):
        bits.append(f"fetch={fetch.get('status')}")
    if fetch.get("detail"):
        bits.append(str(fetch.get("detail"))[:80])
    z = report.get("fetch_zhiyun") or {}
    if isinstance(z, dict):
        bad = [
            f"{k}:{v.get('status')}"
            for k, v in z.items()
            if isinstance(v, dict) and v.get("status") not in (None, "fetched", "skipped", "skipped_no_share")
        ]
        if bad:
            bits.append("zhiyun=" + ",".join(bad[:4]))
    summary = "；".join(bits) if bits else "无更多字段"
    return f"体检红（原因未归类，详见体检明细：{summary}）"


def maybe_alert_pipeline(cfg: dict, report: dict, root=None) -> None:
    """管道体检红：本地 log + 告警文件。"""
    try:
        if report.get("result") != "红":
            return
        detail = format_pipeline_alert_detail(report)
        # 双保险：禁止裸「红」
        if detail.strip() in ("红", "黄", "绿", str(report.get("result") or "")):
            detail = "体检红（原因未归类，详见体检明细）"
        log.warning("pipeline red: %s", detail)
        try:
            import alert_store

            alert_store.append_alert("error", "pipeline", f"体检红：{detail}", cfg=cfg, root=root)
        except Exception:
            pass
    except Exception:
        pass


def maybe_alert_text(cfg: dict, text: str, root=None) -> None:
    """任意文本告警：本地 log + 告警文件。"""
    try:
        if not text:
            return
        msg = str(text)[:500]
        log.warning("%s", msg)
        try:
            import alert_store

            cat = "general"
            if "账号" in msg:
                cat = "accounts"
            elif "配置" in msg:
                cat = "config"
            elif "定时" in msg or "schedule" in msg.lower():
                cat = "schedule"
            elif "台账" in msg or "共享" in msg or "fallback" in msg.lower():
                cat = "ledger"
            alert_store.append_alert("warning", cat, msg, cfg=cfg, root=root)
        except Exception as e:
            log.warning("alert_store append failed: %s", type(e).__name__)
    except Exception:
        pass


def alert_event(kind: str, detail: str = "", root=None) -> None:
    """看门狗/更新：本地 log + 告警文件。"""
    try:
        msg = f"{kind}" + (f" · {detail}" if detail else "")
        log.warning("alert_event %s", msg[:200])
        try:
            import alert_store

            alert_store.append_alert(
                "error" if kind in ("boot_crash", "rollback", "update_fail") else "warning",
                kind or "event",
                msg[:500],
                root=root,
            )
        except Exception:
            pass
    except Exception:
        pass


def cli_alert(argv: list[str] | None = None) -> int:
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        return 0
    alert_event(args[0], " ".join(args[1:]) if len(args) > 1 else "")
    return 0
