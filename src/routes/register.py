"""路由总注册：按域调用 routes.*（批次3 纯搬家）。"""

from __future__ import annotations

from . import auth, cockpit, admin_pages, data_api, export, config_api, manual, config_engine_api


def register_all(app, d):
    """注册全部 HTTP 路由。d = create_app 注入的 SimpleNamespace。"""
    auth.register(app, d)
    cockpit.register(app, d)
    admin_pages.register(app, d)
    data_api.register(app, d)
    export.register(app, d)
    config_api.register(app, d)
    manual.register(app, d)
    config_engine_api.register(app, d)
