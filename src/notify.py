#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""飞书自定义机器人告警（任务书43·可观测）。

- webhook 空/未配置 → 完全静默、零行为变化
- 发送失败/超时(≤3s) → try/except，绝不影响主流程
- 不落密码/token 到日志
"""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("kanban.notify")


def webhook_url(cfg: dict | None) -> str:
    return str((cfg or {}).get("feishu_webhook_url") or "").strip()


def post_feishu_text(url: str, text: str, timeout: float = 3.0) -> bool:
    """POST 飞书 text 消息。成功 True；任何失败 False（不抛）。"""
    if not url:
        return False
    body = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        log.warning("feishu webhook failed: %s", type(e).__name__)
        return False
    except Exception as e:
        log.warning("feishu webhook unexpected: %s", type(e).__name__)
        return False


def maybe_alert_pipeline(cfg: dict, report: dict, root=None) -> None:
    """管道结果红 / 回滚类触发时告警。失败静默。"""
    try:
        url = webhook_url(cfg)
        if not url:
            return
        result = report.get("result")
        if result != "红":
            return
        host = socket.gethostname()
        reasons = []
        if (report.get("disk") or {}).get("red"):
            reasons.append("磁盘空间不足")
        if report.get("fetch", {}).get("status") == "no_source":
            reasons.append("收单台账无源")
        if not (report.get("db_check") or {}).get("ok", True):
            reasons.append("数据库 quick_check 异常")
        msg = f"【经营罗盘告警】{host} 体检红 · {'；'.join(reasons) or '见运行日志'} · {report.get('result')}"
        post_feishu_text(url, msg)
    except Exception:
        pass


def maybe_alert_text(cfg: dict, text: str) -> None:
    url = webhook_url(cfg)
    if not url:
        return
    post_feishu_text(url, text)
