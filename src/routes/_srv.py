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


def start_refresh_async(cfg, root=None, trigger="manual", on_complete=None):
    """透传 on_complete（2.6.7 C-3 / 3.7.8）：定时 success 只在真成功时登记。"""
    return srv().start_refresh_async(cfg, root, trigger, on_complete=on_complete)


def recompute(cfg, root=None, *, rebuild_std: bool = False, already_locked: bool = False):
    """透传 already_locked（3.7.8 P0）：写路径已持 _LOCK 时禁止二次抢锁死锁。"""
    return srv().recompute(
        cfg, root, rebuild_std=rebuild_std, already_locked=already_locked
    )
