"""任务书46·4 管理端口径配置 API —— 任务书54 下线 HTTP 面。

配置引擎内核（domain.config_engine）保留：seed/默认值/校验仍在 ingest 与启动路径使用。
口径配置 UI 与读写接口于 54 号（明昊拍板）下线；本模块 register 为空操作，路由不注册。
"""
from __future__ import annotations


def register(app, d):
    """任务书54：不再挂载 /api/config/caliber*（引擎内核保留）。"""
    del app, d  # 接口签名保持 register(app, d) 与其它 routes 一致
