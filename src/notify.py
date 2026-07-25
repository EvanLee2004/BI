#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机告警日志（无外发）。

2026-07-25 明昊硬令后：
- **已删除**飞书 webhook / 自定义机器人外发能力（含 post HTTP、配置项、设置页入口）。
- **禁止**向公司大群、「财经新闻」机器人、财务每日新闻同通道发任何消息（含测试）。
- 本模块只写 **logging**；失败绝不影响主流程。
- 看门狗/管道仍可调用本模块，语义=「记一条本地告警日志」。
"""
from __future__ import annotations

import logging

log = logging.getLogger("kanban.notify")


def maybe_alert_pipeline(cfg: dict, report: dict, root=None) -> None:
    """管道体检红：只打本地 warning。"""
    try:
        if report.get("result") == "红":
            reasons = []
            if (report.get("disk") or {}).get("red"):
                reasons.append("磁盘")
            if report.get("fetch", {}).get("status") == "no_source":
                reasons.append("收单无源")
            if not (report.get("db_check") or {}).get("ok", True):
                reasons.append("db_check")
            log.warning("pipeline red: %s", "；".join(reasons) or report.get("result"))
    except Exception:
        pass


def maybe_alert_text(cfg: dict, text: str) -> None:
    """任意文本告警：只打本地 warning。"""
    try:
        if text:
            log.warning("%s", str(text)[:500])
    except Exception:
        pass


def alert_event(kind: str, detail: str = "", root=None) -> None:
    """看门狗/更新脚本：只打本地 warning。"""
    try:
        log.warning("alert_event kind=%s detail=%s", kind, (detail or "")[:200])
    except Exception:
        pass


def cli_alert(argv: list[str] | None = None) -> int:
    """deploy/linux：python -m notify kind [detail…]"""
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        return 0
    kind = args[0]
    detail = " ".join(args[1:]) if len(args) > 1 else ""
    alert_event(kind, detail)
    return 0
