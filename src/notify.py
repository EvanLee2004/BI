#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机告警（2.6.4）：logging + 告警.log，零外发。

禁止飞书/webhook/邮件。告警落盘见 alert_store。
"""
from __future__ import annotations

import logging

log = logging.getLogger("kanban.notify")


def maybe_alert_pipeline(cfg: dict, report: dict, root=None) -> None:
    """管道体检红：本地 log + 告警文件。"""
    try:
        if report.get("result") != "红":
            return
        reasons = []
        if (report.get("disk") or {}).get("red"):
            reasons.append("磁盘")
        if report.get("fetch", {}).get("status") == "no_source":
            reasons.append("收单无源")
        if not (report.get("db_check") or {}).get("ok", True):
            reasons.append("db_check")
        detail = "；".join(reasons) or (
            f"结果={report.get('result')}，未命中已知原因，详见体检明细"
        )
        # 禁止「体检红：红」这种无信息量文案
        if detail in ("红", "黄", "绿") or detail == str(report.get("result")):
            detail = f"结果={report.get('result')}，未命中已知原因，详见体检明细"
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
