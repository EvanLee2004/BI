"""重点客户分析（3.4.0）· domain 纯函数入口。"""
from domain.key_customers.compute import (
    DEFAULT_OPEN_TIERS,
    LAZY_TIERS,
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
    "grade_ytd_fen",
    "is_silent",
    "compute_key_customers",
]
