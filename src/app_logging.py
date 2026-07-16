#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一 logging（任务书43）：RotatingFileHandler → 数据/日志/kanban.log；不改业务逻辑。

绝不容密码/token 明文进日志（配合 tests 抽查）。
"""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

# 敏感字段打码
_SECRET_RE = re.compile(
    r"(?i)(password|passwd|token|cookie|secret|authorization|md_pss_id)\s*[=:]\s*([^\s,;]+)"
)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            if _SECRET_RE.search(msg):
                record.msg = _SECRET_RE.sub(r"\1=***", msg)
                record.args = ()
        except Exception:
            pass
        return True


def setup_logging(cfg: dict | None = None, root: Path | None = None) -> Path | None:
    """幂等配置 root logger + 文件滚动。返回日志文件路径。"""
    global _CONFIGURED
    if _CONFIGURED:
        return None
    try:
        import loaders

        ddir = loaders.data_dir(cfg or loaders.load_config(root), root)
        log_dir = ddir / "日志"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "kanban.log"
        fh = RotatingFileHandler(str(log_path), maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        fh.addFilter(_RedactFilter())
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        # 避免重复 handler
        if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
            root_logger.addHandler(fh)
        # 也给 kanban.* 用
        logging.getLogger("kanban").addFilter(_RedactFilter())
        _CONFIGURED = True
        return log_path
    except Exception:
        return None
