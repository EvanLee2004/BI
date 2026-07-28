"""管理利润表（任务书46·5 纯搬家；任务书51·B2 单一结构；2.7.9 G4 去掉 HTML 再导出）。"""
from domain.pl.structure import (
    abs_amt_disp,
    amt_disp,
    kpi_peak_for,
    kpi_target_bar,
    pl_structure,
    structure_for_vm,
)

__all__ = [
    "pl_structure",
    "structure_for_vm",
    "amt_disp",
    "abs_amt_disp",
    "kpi_peak_for",
    "kpi_target_bar",
]
