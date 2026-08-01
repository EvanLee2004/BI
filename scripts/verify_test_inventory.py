#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure every standard test module is listed in tests/run_verify.sh."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

RUNNER_PATH = Path("tests/run_verify.sh")
TEST_LINE = re.compile(r"^\s*(tests/(?:[^\s/]+/)*test_[^\s]+\.py)\s*$", re.MULTILINE)
EXCLUDED_DIRS = {"optional", "_archived"}


def standard_tests(root: Path) -> set[str]:
    """Return test modules that the daily gate must execute."""
    tests_dir = root / "tests"
    return {
        path.relative_to(root).as_posix()
        for path in tests_dir.rglob("test_*.py")
        if not (set(path.relative_to(tests_dir).parts) & EXCLUDED_DIRS)
    }


def registered_tests(root: Path) -> set[str]:
    """Read the explicit SERIAL/PARALLEL lists without executing the runner."""
    return set(TEST_LINE.findall((root / RUNNER_PATH).read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()

    discovered = standard_tests(root)
    registered = registered_tests(root)
    missing = sorted(discovered - registered)
    print(f"测试清单对账：发现 {len(discovered)}，登记 {len(registered)}，遗漏 {len(missing)}")
    if not missing:
        return 0
    print("未登记到 tests/run_verify.sh 的测试：")
    print("\n".join(missing))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
