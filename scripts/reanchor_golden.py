#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从当前代码 + fixtures 生成 golden/baseline_numbers.json 候选。

默认只输出 diff 报告，**不落盘**。
加 ``--write`` 才写入 golden/baseline_numbers.json（须人工审 diff 后使用）。

用法：
  .venv/bin/python scripts/reanchor_golden.py
  .venv/bin/python scripts/reanchor_golden.py --write

何时允许重锚：见 tests/README.md「golden 重锚」。
本脚本不在 run_verify 中自动调用。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KANBAN_OFFLINE", "1")


def main() -> int:
    ap = argparse.ArgumentParser(description="golden baseline_numbers reanchor (default: dry-run)")
    ap.add_argument("--write", action="store_true", help="写入 golden/baseline_numbers.json")
    args = ap.parse_args()

    import api_v1
    import core
    import loaders

    cfg = loaders.load_config(ROOT)
    # 与 run_verify 一致：离线 + golden fixtures
    cfg = dict(cfg)
    if (ROOT / "_golden_data").is_dir():
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False

    import datetime

    today = loaders.pinned_today(cfg) or datetime.date(2026, 6, 30)
    summary, _html, _ing, _bu = core.generate(cfg, today, trigger="reanchor")
    nums = api_v1.extract_numbers(summary)

    golden_path = ROOT / "golden" / "baseline_numbers.json"
    old = {}
    if golden_path.is_file():
        old = json.loads(golden_path.read_text(encoding="utf-8"))

    # 浅层 + 递归 diff 关键标量
    diffs = []

    def walk(a, b, path=""):
        if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
            diffs.append(f"{path}: type {type(a).__name__} vs {type(b).__name__}")
            return
        if isinstance(a, dict):
            keys = set(a) | set(b)
            for k in sorted(keys, key=str):
                if k not in a:
                    diffs.append(f"{path}.{k}: only in new")
                elif k not in b:
                    diffs.append(f"{path}.{k}: only in old")
                else:
                    walk(a[k], b[k], f"{path}.{k}" if path else str(k))
        elif isinstance(a, list):
            if len(a) != len(b):
                diffs.append(f"{path}: list len {len(a)} vs {len(b)}")
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        else:
            if a != b:
                diffs.append(f"{path}: {a!r} → {b!r}")

    walk(old, nums)
    print(f"old keys≈{len(old)} new keys≈{len(nums)} diffs={len(diffs)}")
    for line in diffs[:80]:
        print(" ", line)
    if len(diffs) > 80:
        print(f"  … +{len(diffs) - 80} more")

    if args.write:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(json.dumps(nums, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE {golden_path}")
    else:
        print("dry-run only（加 --write 才落盘）")
    return 0 if not diffs or not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
