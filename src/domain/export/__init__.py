"""导出 PNG/Excel 边界（任务书46·5 纯搬家 re-export）。"""
try:
    from export_png import screenshot_png
except ImportError:  # pragma: no cover
    screenshot_png = None  # type: ignore

__all__ = ["screenshot_png"]
