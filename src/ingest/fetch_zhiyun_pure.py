#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智云抓取 · 纯函数层（2.6.1 R7 从 fetch_zhiyun 拆出，语义零变更）。"""

from __future__ import annotations

import json
from pathlib import Path

# 每个源：进料口文件名的 config.files 键 + 必需列的 config.columns 键
SOURCES = {
    "orders": {"file_key": "orders", "required_cols": ["order_amount", "order_date"], "date_col_key": "order_date"},
    "receipts": {
        "file_key": "receipts",
        "required_cols": ["receipt_amount", "receipt_date"],
        "date_col_key": "receipt_date",
    },
    "project_detail": {
        "file_key": "project_detail_stem",
        "required_cols": ["project_delivery_date", "project_revenue", "project_cost", "project_line"],
        "date_col_key": "project_delivery_date",
    },
    "inhouse": {
        "file_key": "inhouse",
        "required_cols": ["inhouse_amount", "inhouse_date", "inhouse_type"],
        "date_col_key": "inhouse_date",
    },
}
# date_col_key = 该源"归属月"所依据的日期字段（与清洗层 normalize 一致）；
# 服务器端只抓这个日期 **>= config.zhiyun_since** 的行（只要当年、少抓快抓）。
# 实现：filterType=13 实测为**严格大于** value，故 value 传 since 的前一天（见 build_date_since_filter）。
# 日期为空的行本就归属月=None、看板不计入任何月份，被服务器过滤掉不影响口径。

PAGE_SIZE = 1000
MAX_PAGES = 500  # 翻页安全上限（50万行，远超任何表；防接口异常时死循环）
# 2.2.8 行数对账容差：|actual−total| ≤ max(ABS, ceil(total×REL)) 则接受（并发多/少几行）
ROW_TOTAL_ABS_TOL = 5
ROW_TOTAL_REL_TOL = 0.005
# 任务书30 批次0.5 / 任务书35 补做：本次成功抓取行数比上次少超此比例 → 体检黄（不拦）
DEFAULT_ROW_DROP_RATIO = 0.30


# ---------- 纯函数层（离线可测） ----------


def parse_cell(cell, ctrl: dict) -> str:
    """按明道云字段类型把单元格解析成导出同款文本（成员/部门/选项/关联通用，解析失败回退原串）。"""
    if cell in (None, ""):
        return ""
    if isinstance(cell, (list, dict)):  # 已是对象（个别接口不回 JSON 串）直接走结构解析
        v, s = cell, json.dumps(cell, ensure_ascii=False)
    else:
        s = str(cell)
        if s[:1] not in ("[", "{"):
            return s
        try:
            v = json.loads(s)
        except (ValueError, TypeError):
            return s
    if not isinstance(v, list):
        return s
    if v and isinstance(v[0], str):  # 选项 key → 中文
        m = {o["key"]: o["value"] for o in (ctrl.get("options") or [])}
        return "/".join(m.get(k, k) for k in v)
    out = []
    for x in v:  # 成员/部门/关联 = 对象数组
        if isinstance(x, dict):
            out.append(
                x.get("fullname")
                or x.get("departmentName")
                or x.get("name")
                or x.get("organizeName")
                or x.get("sourcevalue")
                or ""
            )
        else:
            out.append(str(x))
    return "/".join(o for o in out if o)


def rows_to_records(rows: list[dict], controls: list[dict]) -> list[dict[str, str]]:
    """原始行（controlId 为键）→ 中文列名记录（全字段，等价人工导出勾"导出所有字段"）。

    ⚠同名列合并：智云可有多个同名控件（如两个"整单交付日期"，一个有值一个空）。
    按控件顺序取**首个非空**值，空值不覆盖已有非空——否则空的同名列会把有值的清掉
    （2026-07-10 踩坑：项目明细归月依据"整单交付日期"因此被清空、收入归不到月）。
    """
    cols = [(c["controlName"], c) for c in controls if c.get("controlName")]
    out = []
    for row in rows:
        rec: dict[str, str] = {}
        for name, c in cols:
            val = parse_cell(row.get(c["controlId"]), c)
            if name not in rec or (not rec[name] and val):
                rec[name] = val
        out.append(rec)
    return out


def check_required_columns(records: list[dict[str, str]], cfg: dict, source: str) -> list[str]:
    """返回缺失的必需列名列表（空=齐）。records 为空也按缺列处理。"""
    wanted = [cfg["columns"][k] for k in SOURCES[source]["required_cols"]]
    have = set(records[0].keys()) if records else set()
    return [w for w in wanted if w not in have]


def resolve_zhiyun_since(since: str | None, today=None) -> str:
    """规范化 config.zhiyun_since → 'YYYY-MM-DD' 或 ''（空=全量不过滤）。

    - ``"auto"``（大小写不敏感）：当年元旦（today.year-01-01；today 可注入便于单测）
    - 空串 / None：全量（不过滤）——与历史「留空=抓全量」一致
    - 写死 ``YYYY-MM-DD``：原样返回（兼容补历史）
    - 其它非法串：返回空（build_date_since_filter 跳过过滤）
    """
    from datetime import date as _date

    if since is None:
        return ""
    s = str(since).strip()
    if not s:
        return ""
    if s.lower() == "auto":
        t = today if today is not None else _date.today()
        return f"{int(t.year):04d}-01-01"
    # 写死日期：只认前 10 位 YYYY-MM-DD 形态
    head = s[:10]
    try:
        from datetime import datetime as _dt

        _dt.strptime(head, "%Y-%m-%d")
        return head
    except ValueError:
        return ""


def _since_filter_value(since: str) -> str:
    """zhiyun_since → filterType=13 的 value。

    2026-07-16 真实 API 实测：filterType=13 为**严格大于** value（不是 >=）。
    要包含 since 当天，value 必须传 since 的**前一天**（datetime 计算，禁止字符串硬减）。
    since 须已是 YYYY-MM-DD（先经 resolve_zhiyun_since）。
    """
    from datetime import datetime, timedelta

    s = str(since).strip()[:10]
    d = datetime.strptime(s, "%Y-%m-%d").date()
    return (d - timedelta(days=1)).isoformat()


def controls_with_name(controls: list[dict], name: str) -> list[dict]:
    """同名控件列表（顺序=模板顺序；抓取/过滤取第一个）。"""
    return [c for c in (controls or []) if c.get("controlName") == name]


def build_date_since_filter(controls: list[dict], date_col_name: str, since: str, today=None) -> list[dict]:
    """构造「该日期字段 **>= since**」的服务器端过滤。

    ⚠ filterType=13 实测语义=**严格大于** value（2026-07-16 陆总号 GetFilterRows 对账）：
    value=since 会丢掉 since 当天行；故 value=since 前一天，整体效果等价于 >= since。
    since 支持 ``"auto"``=当年元旦（见 resolve_zhiyun_since）；空/解析失败 → []（不过滤）。
    同名列多于一个时用**第一个**（与 rows_to_records 首个非空策略对齐）。
    """
    resolved = resolve_zhiyun_since(since, today=today)
    if not resolved or not date_col_name:
        return []
    matches = controls_with_name(controls, date_col_name)
    if not matches:
        return []
    ctrl = matches[0]
    try:
        value = _since_filter_value(resolved)
    except ValueError:
        return []  # since 非法日期 → 不过滤，避免整表抓挂
    return [
        {
            "controlId": ctrl["controlId"],
            "dataType": ctrl.get("type", 15),
            "spec": {},
            "filterType": 13,
            "dateRange": 0,
            "value": value,
            "values": [],
        }
    ]


def _extract_row_total(page_data: dict) -> int | None:
    """首页 GetFilterRows data 里取总条数。明道常见 count；兼容 total/totalNum。"""
    if not isinstance(page_data, dict):
        return None
    for k in ("count", "total", "totalNum", "allCount"):
        if k not in page_data or page_data[k] is None or page_data[k] == "":
            continue
        try:
            return int(page_data[k])
        except (TypeError, ValueError):
            continue
    return None


def row_total_tolerance(declared_total: int) -> int:
    """有 total 时允许的 |actual−total| 上限：max(5, ceil(total×0.5%))."""
    import math

    if declared_total < 0:
        declared_total = 0
    return max(ROW_TOTAL_ABS_TOL, math.ceil(declared_total * ROW_TOTAL_REL_TOL))


def fetch_all_rows(post, worksheet_id: str, app_id: str, filter_controls: list[dict] | None = None) -> list[dict]:
    """翻页拉全量。post(path, body)->dict 由调用方注入（真实 requests 或测试桩）。

    filter_controls 非空时只抓命中过滤的行（如日期 >= zhiyun_since）。
    首页 notGetTotal=false 取 total；有 total 时差额在容差内接受（2.2.8），
    差额过大仍 raise（整表按失败，不静默残缺）。无 total 时靠末页 < pageSize 结束。
    """
    fc = filter_controls or []
    out, page = [], 1
    declared_total: int | None = None
    while page <= MAX_PAGES:
        body = {
            "worksheetId": worksheet_id,
            "appId": app_id,
            "pageSize": PAGE_SIZE,
            "pageIndex": page,
            "status": 1,
            "sortControls": [],
            "notGetTotal": page > 1,
            "searchType": 1,
            "keyWords": "",
            "filterControls": fc,
            "fastFilters": [],
            "navGroupFilters": [],
        }
        d = post("Worksheet/GetFilterRows", body).get("data") or {}
        rows = d.get("data") or []
        if page == 1:
            declared_total = _extract_row_total(d)
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        page += 1
    else:
        raise RuntimeError(f"翻页超过安全上限 {MAX_PAGES} 页仍未拉完，接口行为异常（拒收疑似坏数据）")
    if declared_total is not None:
        diff = abs(len(out) - declared_total)
        tol = row_total_tolerance(declared_total)
        if diff > tol:
            raise RuntimeError(
                f"行数对账失败：接口 total={declared_total}，实际 {len(out)}"
                f"（差额 {diff} > 容差 {tol}，拒收）"
            )
    return out


def write_records_xlsx(records: list[dict[str, str]], dest: Path) -> None:
    """写成与人工导出同构的 xlsx（单 sheet、首行表头）。原子替换：先写临时文件再换名。"""
    if not records:
        raise ValueError("空数据不落盘（调用方应先走必需列护栏）")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    headers = list(records[0].keys())
    ws.append(headers)
    for r in records:
        ws.append([r.get(h, "") for h in headers])
    tmp = dest.with_suffix(".tmp.xlsx")
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(tmp)
    tmp.replace(dest)


# ---------- 接线层（要内网 + 智云配置.json） ----------

# 内置默认连接配置（2026-07-13 明昊拍板进公开库：内网地址+表ID随代码走，部署机开箱免拷模板；
# 账号/密码/cookie 仍绝不进库——只在 数据/智云配置.json（gitignore）里，管理端设置页填）。
# 数据/智云配置.json 里同名字段非空则覆盖这里（老部署/换表零冲突）。
ZHIYUN_DEFAULTS: dict = {
    "base_url": "http://192.168.10.167:18880",
    "app_id": "6ff4fb2e-e68c-4ee9-83a0-836de8f72c11",
    "tables": {
        "orders": {"worksheetId": "6501688ebf25d7b91abdb465"},
        "receipts": {"worksheetId": "6555d2b1f9460e517040ba6c"},
        "project_detail": {"worksheetId": "65a4f4afdd2dc6df7283bf1a"},
        # 「任务」表=内部译员真源；min_rows 护栏：行级权限不足账号只抓到自己的任务（如 85 行）
        # → 行数低于门槛当失败降级、不覆盖现有文件；换全量权限账号自然全绿。
        "inhouse": {"worksheetId": "654da962f9460e517040a9f0", "min_rows": 1000},
    },
}


