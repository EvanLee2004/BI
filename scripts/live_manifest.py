#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.6.0 视觉活体 manifest 校验（G0 契约 / G5 填图）。

每条记录必须含：commit / route / viewport / theme / fixture /
steps / expected / actual / image。
缺字段 → 校验失败（门禁可红）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "commit",
    "route",
    "viewport",
    "theme",
    "fixture",
    "steps",
    "expected",
    "actual",
    "image",
)

ALLOWED_THEMES = frozenset({"neon", "dark", "light"})


def validate_entry(entry: dict[str, Any]) -> tuple[bool, list[str]]:
    errs: list[str] = []
    if not isinstance(entry, dict):
        return False, ["entry is not an object"]
    for k in REQUIRED_FIELDS:
        if k not in entry:
            errs.append(f"missing field: {k}")
            continue
        v = entry[k]
        if v is None or v == "":
            errs.append(f"empty field: {k}")
        if k == "steps" and not isinstance(v, list):
            errs.append("steps must be a list")
        if k == "theme" and isinstance(v, str) and v not in ALLOWED_THEMES:
            errs.append(f"theme must be one of {sorted(ALLOWED_THEMES)}, got {v!r}")
    return (len(errs) == 0), errs


def validate_manifest(doc: dict[str, Any] | list) -> tuple[bool, list[str]]:
    errs: list[str] = []
    if isinstance(doc, list):
        entries = doc
    elif isinstance(doc, dict):
        entries = doc.get("entries") or doc.get("shots") or []
        if not isinstance(entries, list):
            return False, ["manifest.entries must be a list"]
    else:
        return False, ["manifest must be object or list"]
    if not entries:
        # G0：允许空 entries 骨架，但若存在 entry 则必须完整；
        # 缺字段的 entry 必须红。空 manifest 本身在 G5 才要求填满。
        return True, []
    for i, e in enumerate(entries):
        ok, e_errs = validate_entry(e if isinstance(e, dict) else {})
        if not ok:
            errs.extend(f"[{i}] {x}" for x in e_errs)
    return (len(errs) == 0), errs


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: live_manifest.py <manifest.json> [...]", file=sys.stderr)
        return 2
    failed = 0
    for path_s in args:
        path = Path(path_s)
        if not path.is_file():
            print(f"FAIL {path}: not a file")
            failed += 1
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"FAIL {path}: json {e}")
            failed += 1
            continue
        ok, errs = validate_manifest(doc)
        if ok:
            print(f"OK   {path}")
        else:
            print(f"FAIL {path}")
            for e in errs:
                print(f"  - {e}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
