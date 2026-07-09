#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智云（明道云）四源自动抓取：调内部接口拉表 → 产出与人工导出同构的 xlsx 写进料口 数据/。

架构契约（07 迭代计划）：
- 产物 = 与人工导出同列名的 xlsx，落 数据/<下单|回款记录|项目明细|内部译员>.xlsx；下游 readers 以下零改。
- 三态返回（同 fetch.fetch_ledger）：fetched / local_fallback（保留上次文件+体检黄）/ no_source；永不抛异常中断管道。
- 服务器地址/appId/worksheetId/AccountId/cookie 全部读 数据/智云配置.json（不进 git，公开仓库零内网信息）。
- 必需列（config.columns 声明）抓完必须在场，缺了该表按失败处理——铁律"必需列缺失即报错，不静默算 0"。

智云配置.json 结构（部署机/本机本地手填）：
{
  "base_url": "http://<内网IP>:<端口>",
  "app_id": "<应用GUID>",
  "account_id": "<账号GUID>",
  "md_pss_id": "<登录cookie值>",          // 先手动贴；Playwright 自动登录后由程序刷新
  "tables": {
    "orders":   {"worksheetId": "<表ID>"},
    "receipts": {"worksheetId": "<表ID>"},
    "project_detail": {"worksheetId": "<表ID>"},
    "inhouse":  {"worksheetId": "<表ID>"}
  }
}
"""
from __future__ import annotations

import json
from pathlib import Path

import loaders

# 每个源：进料口文件名的 config.files 键 + 必需列的 config.columns 键
SOURCES = {
    "orders": {"file_key": "orders", "required_cols": ["order_amount", "order_date"]},
    "receipts": {"file_key": "receipts", "required_cols": ["receipt_amount", "receipt_date"]},
    "project_detail": {"file_key": "project_detail_stem",
                       "required_cols": ["project_delivery_date", "project_revenue",
                                         "project_cost", "project_line"]},
    "inhouse": {"file_key": "inhouse",
                "required_cols": ["inhouse_amount", "inhouse_date", "inhouse_type"]},
}

PAGE_SIZE = 1000
MAX_PAGES = 500  # 翻页安全上限（50万行，远超任何表；防接口异常时死循环）


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
            out.append(x.get("fullname") or x.get("departmentName") or x.get("name")
                       or x.get("organizeName") or x.get("sourcevalue") or "")
        else:
            out.append(str(x))
    return "/".join(o for o in out if o)


def rows_to_records(rows: list[dict], controls: list[dict]) -> list[dict[str, str]]:
    """原始行（controlId 为键）→ 中文列名记录（全字段，等价人工导出勾"导出所有字段"）。"""
    cols = [(c["controlName"], c) for c in controls if c.get("controlName")]
    return [{name: parse_cell(row.get(c["controlId"]), c) for name, c in cols} for row in rows]


def check_required_columns(records: list[dict[str, str]], cfg: dict, source: str) -> list[str]:
    """返回缺失的必需列名列表（空=齐）。records 为空也按缺列处理。"""
    wanted = [cfg["columns"][k] for k in SOURCES[source]["required_cols"]]
    have = set(records[0].keys()) if records else set()
    return [w for w in wanted if w not in have]


def fetch_all_rows(post, worksheet_id: str, app_id: str) -> list[dict]:
    """翻页拉全量。post(path, body)->dict 由调用方注入（真实 requests 或测试桩）。"""
    out, page = [], 1
    while page <= MAX_PAGES:
        body = {"worksheetId": worksheet_id, "appId": app_id, "pageSize": PAGE_SIZE,
                "pageIndex": page, "status": 1, "sortControls": [],
                "notGetTotal": page > 1, "searchType": 1, "keyWords": "",
                "filterControls": [], "fastFilters": [], "navGroupFilters": []}
        d = post("Worksheet/GetFilterRows", body).get("data") or {}
        rows = d.get("data") or []
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            return out
        page += 1
    raise RuntimeError(f"翻页超过安全上限 {MAX_PAGES} 页仍未拉完，接口行为异常（拒收疑似坏数据）")


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

def _load_zhiyun_cfg(cfg: dict, root: Path | None) -> dict | None:
    p = loaders.data_dir(cfg, root) / "智云配置.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _make_post(zy: dict):
    import requests
    headers = {"Content-Type": "application/json",
               "Authorization": f"md_pss_id {zy['md_pss_id']}",
               "AccountId": zy["account_id"],
               "X-Requested-With": "XMLHttpRequest"}

    def post(path: str, body: dict) -> dict:
        r = requests.post(f"{zy['base_url']}/wwwapi/{path}", headers=headers,
                          json=body, timeout=120)
        r.raise_for_status()
        return r.json()
    return post


def _dest_path(cfg: dict, source: str, root: Path | None) -> Path:
    name = cfg["files"][SOURCES[source]["file_key"]]
    if not name.endswith(".xlsx"):
        name += ".xlsx"  # project_detail_stem 是词干
    return loaders.data_dir(cfg, root) / name


def fetch_source(cfg: dict, source: str, root: Path | None = None,
                 post=None, zy: dict | None = None) -> dict:
    """抓一个源到进料口。返回 {status, detail}，三态同 fetch_ledger，永不抛异常。"""
    local = _dest_path(cfg, source, root)

    def fallback(reason: str) -> dict:
        if local.exists():
            return {"status": "local_fallback", "detail": f"{reason}，用数据目录现有文件（体检黄）"}
        return {"status": "no_source", "detail": f"{reason}，且无本地文件"}

    zy = zy or _load_zhiyun_cfg(cfg, root)
    if not zy:
        return fallback("未配置 数据/智云配置.json（自动抓未启用）")
    tbl = (zy.get("tables") or {}).get(source) or {}
    if not tbl.get("worksheetId"):
        return fallback(f"智云配置缺 tables.{source}.worksheetId")

    try:
        post = post or _make_post(zy)
        info = post("Worksheet/getWorksheetInfo",
                    {"worksheetId": tbl["worksheetId"], "appId": zy["app_id"],
                     "getTemplate": True})
        controls = info["data"]["template"]["controls"]
        rows = fetch_all_rows(post, tbl["worksheetId"], zy["app_id"])
        records = rows_to_records(rows, controls)
        missing = check_required_columns(records, cfg, source)
        if missing:
            return fallback(f"抓到 {len(records)} 行但缺必需列 {missing}（可能无权限/表不对）")
        write_records_xlsx(records, local)
        return {"status": "fetched", "detail": f"智云抓取 {len(records)} 行 → {local.name}"}
    except Exception as e:  # noqa: BLE001 铁律：抓失败不中断管道
        return fallback(f"智云抓取失败（{type(e).__name__}: {e}）")


def fetch_all(cfg: dict, root: Path | None = None) -> dict[str, dict]:
    """抓全部四源，返回 {source: {status, detail}}。供 pipeline/体检使用。"""
    return {s: fetch_source(cfg, s, root) for s in SOURCES}
