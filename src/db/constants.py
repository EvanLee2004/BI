#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db._impl 原 db.py 正文（54.4·E）。看板.db 访问层：连接、建表、读标准表/手填表。

设计要点：
- 读回层**刻意返回与旧 loaders 完全相同的结构**，让 profit/columns/periods 原样计算，守刀1回归红线：
  * 智云四源 → list[dict]，键=config.columns 里的源列名（如「整单交付日期」「交付额/本币」）；
  * 收单台账 → (表头行, 数据行)，与 loaders.load_ledger 同形（逐行原样、含空行，保证行数一致）；
  * 手填 → {'YYYY-MM': {项目: 金额float}}，与 loaders.load_manual 同形。
- 金额库内 INTEGER 分（任务书33·A3）；读回转元 float 交给 profit/fmt；写入侧元→分。
"""

from __future__ import annotations


import money

# constants from _impl.py

"""db._impl 原 db.py 正文（54.4·E）。看板.db 访问层：连接、建表、读标准表/手填表。

设计要点：
- 读回层**刻意返回与旧 loaders 完全相同的结构**，让 profit/columns/periods 原样计算，守刀1回归红线：
  * 智云四源 → list[dict]，键=config.columns 里的源列名（如「整单交付日期」「交付额/本币」）；
  * 收单台账 → (表头行, 数据行)，与 loaders.load_ledger 同形（逐行原样、含空行，保证行数一致）；
  * 手填 → {'YYYY-MM': {项目: 金额float}}，与 loaders.load_manual 同形。
- 金额库内 INTEGER 分（任务书33·A3）；读回转元 float 交给 profit/fmt；写入侧元→分。
"""


DB_DEFAULT_REL = "看板.db"


_BUSY_TIMEOUT_MS = 5000


LEDGER_STD_COLS = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]


DETAIL_TABLES: dict[str, tuple[str, list[str], list[str]]] = {
    # searchable 含定位键/订单号（陆总现场要按单号或定位键搜）
    "收入明细": (
        "std_收入明细",
        ["定位键", "订单号", "客户", "业务线", "销售", "整单交付日期", "交付额", "项目成本", "归属月"],
        ["定位键", "订单号", "客户", "业务线", "销售"],
    ),
    "下单": (
        "std_下单",
        ["定位键", "订单号", "下单日期", "下单预估额", "部门", "销售", "归属月"],
        ["定位键", "订单号", "部门", "销售"],
    ),
    "回款": (
        "std_回款",
        ["定位键", "回款ID", "到账日期", "到账金额", "客户", "销售", "归属月"],
        ["定位键", "回款ID", "客户", "销售"],
    ),
    # 列头「销售」实为项目关联销售（非费用归属），管理端表头旁见 note
    # A2：主列/筛选=译员姓名（供应商姓名）；销售列保留次要展示（任务关联销售不可信）
    "内部译员": (
        "std_内部译员",
        ["定位键", "任务ID", "任务提交日期", "结算金额", "译员类型", "译员姓名", "销售", "归属月"],
        ["定位键", "任务ID", "译员类型", "译员姓名", "销售"],
    ),
    # A5：费用明细全列（含事项≈摘要）；系统列归属月置末 —— 管理端「数据调整」用全列
    "费用明细": (
        "std_费用明细",
        [
            "定位键",
            "收单月份",
            "收单日期",
            "含税金额",
            "业务BU",
            "对应报表大类",
            "预算明细费用类型",
            "预算归属部门",
            "事项",
            "提单人",
            "提单人部门",
            "业务员",
            "配音费合同号",
            "归属月",
        ],
        ["定位键", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门", "事项", "提单人", "业务员"],
    ),
}


VIEW_EXPENSE_COLUMNS: list[str] = [
    "收单日期",
    "事项",
    "含税金额",
    "对应报表大类",
    "预算明细费用类型",
    "业务员",
    "预算归属部门",
    "业务BU",
]


VIEW_EXPENSE_COLUMNS_BU: list[str] = [c for c in VIEW_EXPENSE_COLUMNS if c != "业务BU"]


VIEW_EXPENSE_HIDDEN: list[str] = [
    "定位键",
    "收单月份",
    "归属月",
    "提单人",
    "提单人部门",
    "配音费合同号",
]


DETAIL_DATE_COLS = frozenset(
    {
        "整单交付日期",
        "下单日期",
        "到账日期",
        "任务提交日期",
        "收单日期",
    }
)


UNCLASSIFIED_WHERE = "(对应报表大类 IS NULL OR TRIM(对应报表大类)='') AND 含税金额 IS NOT NULL AND 含税金额<>0"


UNFILLED_DEPT_WHERE = "(部门 IS NULL OR TRIM(部门)='') AND 下单预估额 IS NOT NULL AND 下单预估额<>0"


CONFIG_CHANGE_CATEGORIES = ("销售归属", "BU配置", "分摊", "账号", "设置", "密码", "更新")


BUDGET_METRICS = (
    "下单年预算",
    "回款年预算",
    "毛利率年目标",
    "下单H1目标",
    "回款H1目标",
    "毛利率H1目标",
    # A4·陆总#3：新增税前利润率目标（勿改既有键名）
    "税前利润率年目标",
    "税前利润率H1目标",
    "费用年预算",
)


BUDGET_RATE_METRICS = money.BUDGET_RATE_METRICS

__all__ = ['DB_DEFAULT_REL', '_BUSY_TIMEOUT_MS', 'LEDGER_STD_COLS', 'DETAIL_TABLES', 'VIEW_EXPENSE_COLUMNS', 'VIEW_EXPENSE_COLUMNS_BU', 'VIEW_EXPENSE_HIDDEN', 'DETAIL_DATE_COLS', 'UNCLASSIFIED_WHERE', 'UNFILLED_DEPT_WHERE', 'CONFIG_CHANGE_CATEGORIES', 'BUDGET_METRICS', 'BUDGET_RATE_METRICS']
