#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染层兼容入口（任务书54.13）：对外 import 路径不变，实现已拆到 render_* 模块。

只 re-export，不改算法。
"""
from __future__ import annotations

import charts  # noqa: F401  # 兼容 render.charts
import tpl  # noqa: F401  # 兼容 render.tpl.fill

from render_common import GROUP_COLORS, LED_OF  # noqa: F401

from render_expense_ui import (  # noqa: F401
    render_trend,
    render_donut,
    render_expense_views,
    render_bu_expense_views,
    render_dept_budget,
    expense_monthly_from_period_ledgers,
    apply_expense_salary_hide,
    pack_expense_trend_months,
    render_expense_trend,
    _hbar_rows,
    _ledger_subtotal,
    _fine_to_rows,
    _HBAR_SINK,
)

from render_pl_ui import (  # noqa: F401
    render_pl_table,
    render_bu_pl_table,
    _pl_structure_to_html,
    _row,
    _pct_row,
    _open_row,
    _drow,
    _d_ledger,
    _detail_block,
    _bu_pending_row,
)

from render_receipts_rank import (  # noqa: F401
    render_receipts,
    render_rankings,
    render_profit_rankings,
    dual_rankings_from_daily,
    attach_monthly_to_dual,
    compact_monthly_display,
    monthly_data_script,
    monthly_mkey,
    _receipt_insight_totals,
    _merge_dual_rank,
)

from render_assemble import (  # noqa: F401
    build_dashboard_fragments,
    assemble_dashboard_html,
    render_dashboard,
    build_bu_dashboard_fragments,
    assemble_bu_dashboard_html,
    render_bu_page,
)

# 兼容旧代码可能用的内部名再导出一批
from render_receipts_rank import (  # noqa: F401
    _budget_tag,
    _rank_card,
    _dual_card,
    _profit_rank_card,
    _months_for_period_key,
    _period_months_map,
)


# 兼容：原 render 把 widgets/shell 符号挂在本模块命名空间
from render_widgets import (  # noqa: F401
    _title_version_html,
    _amt,
    render_basic,
    render_period_bar,
    _pv,
    _esc,
)

from render_receipts_rank import (  # noqa: F401
    _rank_amt,
    _rank_rows_html,
    _rank_card,
    _merge_dual_rank,
    _monthly_dual_rows,
    _json_num,
    _dual_rows_html,
    _dual_card,
    _budget_tag,
    _receipt_insight_totals,
    _receipt_insight_panel,
    _receipt_insight_from_period,
    _months_for_period_key,
    _period_months_map,
    _margin_meta,
    _pname,
    _profit_rank_rows_html,
    _profit_rank_card,
    _conc_tag,
    monthly_mkey,
    compact_monthly_display,
    monthly_data_script,
    attach_monthly_to_dual,
    dual_rankings_from_daily,
)
from render_expense_ui import (  # noqa: F401
    _hbar_rows,
    _ledger_subtotal,
    _fine_to_rows,
    _HBAR_SINK,
)
from render_pl_ui import (  # noqa: F401
    _row,
    _pct_row,
    _open_row,
    _drow,
    _d_ledger,
    _detail_block,
    _pl_structure_to_html,
    _bu_pending_row,
)

from render_shell import (  # noqa: F401
    DRAWER_HTML,
    PARTICLES_HTML,
    PW_MODAL_HTML,
    RK_MODAL_HTML,
    DAILY_HTML,
)

__all__ = [
    "GROUP_COLORS",
    "LED_OF",
    "render_trend",
    "render_donut",
    "render_expense_views",
    "render_bu_expense_views",
    "render_dept_budget",
    "expense_monthly_from_period_ledgers",
    "apply_expense_salary_hide",
    "pack_expense_trend_months",
    "render_expense_trend",
    "render_pl_table",
    "render_bu_pl_table",
    "render_receipts",
    "render_rankings",
    "render_profit_rankings",
    "dual_rankings_from_daily",
    "attach_monthly_to_dual",
    "compact_monthly_display",
    "monthly_data_script",
    "monthly_mkey",
    "build_dashboard_fragments",
    "assemble_dashboard_html",
    "render_dashboard",
    "build_bu_dashboard_fragments",
    "assemble_bu_dashboard_html",
    "render_bu_page",
    "render_basic",
    "render_period_bar",
    "DAILY_HTML",
    "_pv",
    "_esc",
    "_amt",
]
