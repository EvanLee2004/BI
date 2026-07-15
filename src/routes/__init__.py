"""HTTP 路由包（批次3：从 server.create_app 纯搬家）。\n\nregister_all(app, d) — d 为 SimpleNamespace，含鉴权/壳/配置闭包。\n"""
from .register import register_all

__all__ = ["register_all"]
