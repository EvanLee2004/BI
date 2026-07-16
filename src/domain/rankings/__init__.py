"""下单回款排名 + 收入毛利结构（任务书46·5 纯搬家 re-export）。"""
from profit import build_rankings_monthly, compute_profit_ranking, compute_ranking
from render import render_profit_rankings, render_rankings

__all__ = [
    "build_rankings_monthly",
    "compute_profit_ranking",
    "compute_ranking",
    "render_profit_rankings",
    "render_rankings",
]
