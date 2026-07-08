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

import loaders, profit, db, ingest  # noqa: E402


def summary_from_files(cfg, today, ledger_year):
    lh, lr = loaders.load_ledger(cfg, str(ledger_year))
    return profit.build_summary(
        cfg, loaders.load_project_detail(cfg), loaders.load_orders(cfg),
        loaders.load_receipts(cfg), loaders.load_inhouse(cfg), lh, lr, ledger_year, today)


def summary_from_db(cfg, today, ledger_year):
    conn = db.connect(cfg)
    ingest.build_std_db(cfg, ledger_year, conn=conn)
    lh, lr = db.load_ledger(cfg, conn)
    s = profit.build_summary(
        cfg, db.load_project_detail(cfg, conn), db.load_orders(cfg, conn),
        db.load_receipts(cfg, conn), db.load_inhouse(cfg, conn), lh, lr, ledger_year, today,
        manual_raw=db.load_manual(cfg, conn))
    conn.close()
    return s


def _strip_ts(s):
    """去掉会随时间变的字段，只比数字/结构。"""
    import copy
    s = copy.deepcopy(s)
    s.get("meta", {}).pop("generated_at", None)
    return s


def diff(a, b, path=""):
    """返回不一致点列表 [(路径, 旧, 新)]。数字按精确相等比（都已 round 过）。"""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append((f"{path}.{k}", "<缺>", b[k]))
            elif k not in b:
                out.append((f"{path}.{k}", a[k], "<缺>"))
            else:
                out += diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{path}[len]", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    else:
        if isinstance(a, float) or isinstance(b, float):
            if abs((a or 0) - (b or 0)) > 1e-9:
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
