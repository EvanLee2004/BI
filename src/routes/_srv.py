#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路由共享：延迟 import server（任务书64·D9）。

各 routes/* 曾重复写 `import server as _srv` 闭包，抽成一处避免漂移。
"""

from __future__ import annotations


def srv():
    """返回 server 模块（调用时再 import，打破环依赖）。"""
    import server as _srv

    return _srv


def start_refresh_async(cfg, root=None, trigger="manual"):
    return srv().start_refresh_async(cfg, root, trigger)


def recompute(cfg, root=None):
    return srv().recompute(cfg, root)
