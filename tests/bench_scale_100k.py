#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书33·A5：10 万行规模基准（只记录、不优化）。

用法（勿进 run_verify，耗时长）：
  KANBAN_OFFLINE=1 .venv/bin/python tests/bench_scale_100k.py

输出 JSON 行到 stdout + 写入 docs/bench_scale_100k_latest.json（若可写）。
"""
from __future__ import annotations

import json
import os
import resource
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("KANBAN_OFFLINE", "1")

import db  # noqa: E402
import ingest  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import core  # noqa: E402


N = int(os.environ.get("KANBAN_BENCH_N", "100000"))


def _peak_rss_mb() -> float:
    # macOS ru_maxrss 单位字节；Linux 为 KB
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024.0


def seed_synthetic(conn, n: int) -> None:
    """直接插 std 合成行（跳过 xlsx），金额分。"""
    batch = []
    for i in range(n):
        ym = f"2026-{(i % 12) + 1:02d}"
        d = f"{ym}-{(i % 28) + 1:02d}"
        fen = money.yuan_to_fen((i % 10000) + 0.12) or 0
        batch.append(
            (
                f"SO-{i}",
                f"SO-{i}",
                f"客户{i % 500}",
                "线1",
                f"销售{i % 50}",
                d,
                fen,
                fen // 3,
                ym,
                d,
                ym,
            )
        )
        if len(batch) >= 5000:
            conn.executemany(
                "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,"
                "归属月,原值_交付日期,原值_归属月,已删除) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                batch,
            )
            batch = []
    if batch:
        conn.executemany(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,"
            "归属月,原值_交付日期,原值_归属月,已删除) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
            batch,
        )
    # 额外 1 万费用明细供 query_detail 翻页
    exp = []
    for i in range(min(10000, n // 10)):
        ym = f"2026-{(i % 12) + 1:02d}"
        exp.append(
            (
                f"L-{i}",
                str((i % 12) + 1),
                f"{ym}-10",
                money.yuan_to_fen(50.0 + i % 100) or 0,
                "公共",
                "管理费用",
                "办公",
                "财务",
                ym,
                ym,
            )
        )
    conn.executemany(
        "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
        "预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除) VALUES(?,?,?,?,?,?,?,?,?,?,0)",
        exp,
    )
    conn.commit()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="kanban_bench_"))
    cfg = dict(loaders.load_config(ROOT))
    cfg["db_path"] = str((tmp / "看板.db").resolve())
    cfg["data_dir"] = str(tmp)
    # 空源文件目录，避免 fetch
    result = {"n_income": N, "tmp": str(tmp)}

    t0 = time.perf_counter()
    conn = db.connect(cfg, tmp)
    seed_synthetic(conn, N)
    seed_s = time.perf_counter() - t0
    result["seed_seconds"] = round(seed_s, 3)
    result["peak_rss_mb_after_seed"] = round(_peak_rss_mb(), 1)

    # 重建管道（空 xlsx → 会清 std；改为只测 page + query）
    # 用已有 std 做 query_detail 与 generate 需要文件源。此处仅测：
    # 1) query_detail 翻页 2) summary_from_conn 3) db 文件大小
    t1 = time.perf_counter()
    q = db.query_detail(conn, "收入明细", page=1, page_size=50)
    result["query_detail_page1"] = {
        "total": q["total"],
        "rows": len(q["rows"]),
        "seconds": round(time.perf_counter() - t1, 4),
    }
    t2 = time.perf_counter()
    q2 = db.query_detail(conn, "收入明细", page=max(1, q["pages"] // 2), page_size=50, q="客户1")
    result["query_detail_search"] = {
        "total": q2["total"],
        "seconds": round(time.perf_counter() - t2, 4),
    }

    db_path = db.db_path(cfg, tmp)
    result["db_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)
    result["db_check"] = db.pragma_quick_check(conn)
    result["peak_rss_mb"] = round(_peak_rss_mb(), 1)

    # 说明：完整 update 管道依赖真实 xlsx；本基准测「库内 10 万行」读写路径
    result["note"] = (
        "合成 std 直接插入（非 xlsx 进料）；query_detail 翻页/搜索 + 库体积 + RSS。"
        "完整 generate 需真实数据目录，见交付报告。"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    out = ROOT / "docs" / "bench_scale_100k_latest.json"
    try:
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    except OSError as e:
        print(f"skip write docs: {e}", file=sys.stderr)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
