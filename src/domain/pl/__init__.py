"""管理利润表（任务书46·5 纯搬家 re-export；任务书51·B2 单一结构）。"""
from domain.pl.structure import (
    abs_amt_disp,
    amt_disp,
    kpi_peak_for,
    kpi_target_bar,
    pl_structure,
    structure_for_vm,
)
from render import render_pl_table, render_bu_pl_table

__all__ = [
    "render_pl_table",
    "render_bu_pl_table",
    "pl_structure",
    "structure_for_vm",
    "amt_disp",
    "abs_amt_disp",
    "kpi_peak_for",
    "kpi_target_bar",
]
