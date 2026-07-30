"""重点客户分析（3.4.0/3.4.1）· domain 纯函数入口。"""
from domain.key_customers.compute import (
    DEFAULT_OPEN_TIERS,
    HELP_LINES,
    HELP_LINE_METRIC,
    HELP_LINE_SALES,
    HELP_LINE_SILENT,
    LAZY_TIERS,
    SALES_COL_LABEL,
    SALES_COL_TIP,
    SILENT_TIP,
    TIER_ORDER,
    TIER_RANGE_DISP,
    compute_key_customers,
    grade_ytd_fen,
    is_silent,
)

__all__ = [
    "TIER_ORDER",
    "TIER_RANGE_DISP",
    "DEFAULT_OPEN_TIERS",
    "LAZY_TIERS",
    "HELP_LINES",
    "HELP_LINE_METRIC",
    "HELP_LINE_SILENT",
    "HELP_LINE_SALES",
    "SALES_COL_LABEL",
    "SALES_COL_TIP",
    "SILENT_TIP",
    "grade_ytd_fen",
    "is_silent",
    "compute_key_customers",
]
