#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刀1 回归红线：改造后"从库算"的 summary 与 v6-final"从文件算"的 summary **逐数字一分不差**。

- 旧路径：loaders 直接读 6 文件 → profit.build_summary（即 v6-final run.py 的算法）。
- 新路径：ingest 建库 → db 读回 → profit.build_summary（同一算法、换数据源）。
- 深比对整份 summary（忽略 meta.generated_at 时间戳）。任何一处数字不同即 FAIL、打印路径。

跑：python3 tests/regress_db_vs_files.py    （退出码 0=一致）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders
import profit
import db
import ingest  # noqa: E402


def _rows_yuan_to_fen(rows: list, amount_keys: list[str]) -> list:
    """xlsx 读出的金额（元 float/int/str）→ 分 int，与 db.load_* 同单位。"""
    import money as _money

    out = []
    for r in rows:
        d = dict(r)
        for k in amount_keys:
            if k in d:
                d[k] = _money.yuan_to_fen(loaders.parse_amount(d.get(k))) or 0
        out.append(d)
    return out


def _ledger_yuan_to_fen(header, rows, ledger_year):
    """台账行含税金额 元→分 int（空单元格保持 None）。"""
    import money as _money
    import columns as _columns

    lcols = _columns.resolve_ledger_columns(header)
    ca = lcols["含税金额"]
    out = []
    for row in rows:
        lst = list(row)
        if len(lst) > ca:
            raw = lst[ca]
            if raw is None or (isinstance(raw, str) and not str(raw).strip()):
                lst[ca] = None
            else:
                lst[ca] = _money.yuan_to_fen(loaders.parse_amount(raw)) or 0
        out.append(tuple(lst))
    return out


def summary_from_files(cfg, today, ledger_year):
    # 手填自 v7 起以库为唯一可信源（管理端写库，手填与调整表.xlsx 不再回写）——
    # 两条路径共用库里的 manual，红线只守护"5 个文件源入库==直读文件"这件事；
    # 否则管理端一改手填，旧 xlsx 立即过时、红线永久假红（2026-07-13 实际踩到）。
    # 任务书33：算账单位=分；文件路径在此统一元→分，与 db.load_* 对齐。
    conn = db.connect(cfg)
    manual = db.load_manual(cfg, conn)
    conn.close()
    c = cfg["columns"]
    lh, lr = loaders.load_ledger(cfg, str(ledger_year))
    # 任务书35：与入库 norm_ledger 一致，跳过全空格式化行（红线 health.rows 对齐）
    from ingest import normalize as _normalize
    import columns as _columns

    _lcols = _columns.resolve_ledger_columns(lh)
    lr = _normalize.filter_ledger_empty_rows(lh, lr, _lcols)
    lr = _ledger_yuan_to_fen(lh, lr, ledger_year)
    return profit.build_summary(
        cfg,
        _rows_yuan_to_fen(
            loaders.load_project_detail(cfg),
            [c["project_revenue"], c["project_cost"]],
        ),
        _rows_yuan_to_fen(loaders.load_orders(cfg), [c["order_amount"]]),
        _rows_yuan_to_fen(loaders.load_receipts(cfg), [c["receipt_amount"]]),
        _rows_yuan_to_fen(loaders.load_inhouse(cfg), [c["inhouse_amount"]]),
        lh,
        lr,
        ledger_year,
        today,
        manual_raw=manual,
    )


def summary_from_db(cfg, today, ledger_year):
    conn = db.connect(cfg)
    ingest.build_std_db(cfg, ledger_year, conn=conn)
    lh, lr = db.load_ledger(cfg, conn)
    s = profit.build_summary(
        cfg,
        db.load_project_detail(cfg, conn),
        db.load_orders(cfg, conn),
        db.load_receipts(cfg, conn),
        db.load_inhouse(cfg, conn),
        lh,
        lr,
        ledger_year,
        today,
        manual_raw=db.load_manual(cfg, conn),
    )
    conn.close()
    return s


def _strip_ts(s):
    """去掉会随时间变的字段，只比数字/结构。"""
    import copy

    s = copy.deepcopy(s)
    s.get("meta", {}).pop("generated_at", None)
    return s


def diff(a, b, path=""):
    """返回不一致点列表 [(路径, 旧, 新)]。

    数字「一分不差」= 绝对差 ≤ 1e-9（金额已统一为分整数后应全等；嵌套 tuple 递归比）。
    """
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append((f"{path}.{k}", "<缺>", b[k]))
            elif k not in b:
                out.append((f"{path}.{k}", a[k], "<缺>"))
            else:
                out += diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            out.append((f"{path}[len]", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    else:
        if isinstance(a, (int, float)) or isinstance(b, (int, float)):
            try:
                if abs(float(a or 0) - float(b or 0)) > 1e-9:
                    out.append((path, a, b))
            except (TypeError, ValueError):
                if a != b:
                    out.append((path, a, b))
        elif a != b:
            out.append((path, a, b))
    return out


def main() -> int:
    cfg = loaders.load_config()
    today = loaders.pinned_today(cfg)
    yr = today.year
    old = _strip_ts(summary_from_files(cfg, today, yr))
    new = _strip_ts(summary_from_db(cfg, today, yr))
    d = diff(old, new)
    if not d:
        np = len(old["periods"])
        print(f"✓ 回归红线通过：从库算与从文件算 逐数字一致（{np} 个周期 + 趋势/回款/体检/未分类 全部相同）")
        return 0
    print(f"✗ 回归红线 FAIL：{len(d)} 处不一致（旧=从文件，新=从库）：")
    for pth, a, b in d[:40]:
        print(f"   {pth}: 旧={a!r}  新={b!r}")
    if len(d) > 40:
        print(f"   …还有 {len(d) - 40} 处")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
