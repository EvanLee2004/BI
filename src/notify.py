#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""告警出口（已废止飞书外发）。

2026-07-25 明昊硬令：
- **禁止**再向公司大群 /「财经新闻」机器人 / 任何飞书 webhook 发消息（含测试）。
- 曾误用财务每日新闻同通道做 2.6.3 B5 联通测试，已清生产 `feishu_webhook_url`。
- 本模块所有外发函数为 **永久 no-op**：不读 webhook、不 HTTP、不抛异常。
- 需要告警时只写本地日志；若将来要新通道，必须单独建告警群且书面批准，禁止复用新闻 bot。
"""
from __future__ import annotations

import logging

log = logging.getLogger("kanban.notify")

# 功能开关：永远 False。禁止改为 True 除非明昊书面批准新通道。
FEISHU_OUTBOUND_ENABLED = False


def webhook_url(cfg: dict | None) -> str:
    """兼容旧调用：始终返回空（忽略配置里残留的 URL）。"""
    return ""


def post_feishu_text(url: str, text: str, timeout: float = 3.0) -> bool:
    """永久禁用：不发任何 HTTP。"""
    if url or text:
        log.info("feishu outbound disabled; drop message (len=%s)", len(text or ""))
    return False


def maybe_alert_pipeline(cfg: dict, report: dict, root=None) -> None:
    """管道红：仅打本地 log，不外发。"""
    try:
        result = report.get("result")
        if result == "红":
            log.warning("pipeline red (feishu outbound disabled): %s", result)
    except Exception:
        pass


def maybe_alert_text(cfg: dict, text: str) -> None:
    """任意文本告警：仅本地 log，不外发。"""
    try:
        if text:
            log.warning("alert text (feishu outbound disabled): %s", str(text)[:200])
    except Exception:
        pass


def alert_event(kind: str, detail: str = "", root=None) -> None:
    """看门狗/更新脚本：仅本地 log。"""
    try:
        log.warning("alert_event kind=%s detail=%s (feishu outbound disabled)", kind, (detail or "")[:200])
    except Exception:
        pass


def cli_alert(argv: list[str] | None = None) -> int:
    """deploy/linux 看门狗入口：不外发。"""
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        return 0
    kind = args[0]
    detail = " ".join(args[1:]) if len(args) > 1 else ""
    alert_event(kind, detail)
    return 0
