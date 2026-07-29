#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G5 · 2.8.0：废除 PL HTML SHA 架构锁，改为 pl_structure / packers / 数字契约。

真路径：_golden_data → summary → pl_structure → structure_for_vm / pack_pl_by_period
→ extract_numbers 关键行 *_disp 对齐。
禁止 hashlib/整段 HTML 字节/SHA 作架构锁；禁止 mock 被测单元、禁止改算账凑绿。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import api_v1  # noqa: E402
import charts  # noqa: E402
import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
from domain.pl.structure import pl_structure, structure_for_vm  # noqa: E402
from viewmodels import packers  # noqa: E402

FAKE = ROOT / "_golden_data"

# 关键 PL 行名 → extract_numbers 金额键（与 G1 同口径）
PL_NAME_TO_KEY = {
    "交付收入（不含税）": "revenue_net",
    "毛利": "gross_profit",
    "税前利润": "pretax_profit",
}

_SHA_ARCH_RE = re.compile(
    r"hashlib\.sha256|pl_table_year_sha|render_pl_table_sha|sha_golden",
    re.I,
)


def _build_summary():
    cfg = dict(loaders.load_config(ROOT))
    cfg["data_dir"] = "_golden_data"
    cfg["db_path"] = "看板.db"
    cfg["zhiyun_auto_fetch"] = False
    cfg["period_pin"] = {"year": 2026, "month": 7}
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, ROOT)
    try:
        summary = core.summary_from_conn(cfg, conn, today)
    finally:
        conn.close()
    return summary, cfg


class TestG5NoHtmlShaArchitectureLock(unittest.TestCase):
    """门禁内不得再存在 PL HTML → SHA 架构锁。"""

    def test_no_pl_table_sha_fixture(self):
        """固化 SHA 文件已删除，不得被任何测再依赖。"""
        p = ROOT / "tests" / "fixtures" / "pl_table_year_sha.txt"
        self.assertFalse(p.is_file(), f"SHA fixture 仍存在: {p}")

    def test_tests_tree_no_sha_architecture_lock(self):
        """tests/ 内无 hashlib.sha256 / pl_table_year_sha / render_pl_table_sha 架构锁。"""
        hits: list[str] = []
        for path in (ROOT / "tests").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if _SHA_ARCH_RE.search(line):
                    # 允许本文件 docstring 说明与闸测自身字面
                    if path.name == "test_g5_2_8_0_pl_structure_contract.py":
                        continue
                    hits.append(f"{path.relative_to(ROOT)}:{i}:{line.rstrip()}")
        self.assertEqual(hits, [], "仍存在 HTML SHA 架构锁命中:\n" + "\n".join(hits[:30]))


class TestG5PlStructureNumbersContract(unittest.TestCase):
    """全年 PL：pl_structure / packers 关键行与 extract_numbers 数字同源。"""

    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cls.summary, cls.cfg = _build_summary()
        cls.numbers = api_v1.extract_numbers(cls.summary)
        cls.yk = cls.numbers.get("meta_year_key") or (cls.summary.get("meta") or {}).get("year_key") or ""
        if not cls.yk or cls.yk not in (cls.summary.get("periods") or {}):
            raise unittest.SkipTest(f"无 year_key 周期: {cls.yk!r}")
        cls.n_year = (cls.numbers.get("periods") or {}).get(cls.yk) or {}
        cls.P = cls.summary["periods"]
        cls.FT = cls.summary.get("expense_fine_type") or {}
        unc = (cls.summary.get("meta") or {}).get("unclassified") or {}
        cls.unc_amt = float((unc.get("expense") or {}).get("amount") or 0)

    def test_pl_structure_key_rows_have_disp(self):
        """pl_structure 全年关键行存在，且 amt_disp 与 numbers→fmt_wan 一致。"""
        unc = self.unc_amt if self.unc_amt > 0 else None
        struct = pl_structure(
            self.P[self.yk],
            self.FT.get(self.yk) or {},
            is_bu=False,
            unclassified_amt=unc,
        )
        rows = struct.get("rows") or []
        self.assertGreaterEqual(len(rows), 5, "PL 结构行过少")
        by_name = {r.get("name"): r for r in rows}
        for name, key in PL_NAME_TO_KEY.items():
            with self.subTest(name=name):
                self.assertIn(name, by_name, f"pl_structure 缺行 {name}；有 {list(by_name)[:20]}")
                raw = self.n_year.get(key)
                self.assertIsNotNone(raw, f"extract_numbers 缺 {key}")
                exp = charts.fmt_wan(raw) + "万"
                # structure 行可能用 amt_disp 或 impact+disp
                got = by_name[name].get("amt_disp")
                if not got:
                    # 部分结构用 impact 数值，structure_for_vm 再产 disp
                    vm = structure_for_vm(struct)
                    by_vm = {r.get("name"): r for r in (vm.get("rows") or [])}
                    got = (by_vm.get(name) or {}).get("amt_disp")
                self.assertEqual(got, exp, f"{name}: structure disp={got!r} exp={exp!r}")

    def test_pack_pl_equals_structure_for_vm(self):
        """packers.pack_pl_by_period 与 structure_for_vm(pl_structure) 全等。"""
        unc = self.unc_amt if self.unc_amt > 0 else None
        struct = pl_structure(
            self.P[self.yk],
            self.FT.get(self.yk) or {},
            is_bu=False,
            unclassified_amt=unc,
        )
        packed = packers.pack_pl_by_period(self.summary, is_bu=False).get(self.yk) or {}
        self.assertEqual(structure_for_vm(struct), packed)

    def test_pack_pl_key_rows_match_numbers(self):
        """pack_pl 关键行 amt_disp 与 extract_numbers 同源。"""
        packed = packers.pack_pl_by_period(self.summary, is_bu=False).get(self.yk) or {}
        rows = packed.get("rows") or []
        by_name = {r.get("name"): r for r in rows}
        for name, key in PL_NAME_TO_KEY.items():
            with self.subTest(name=name):
                self.assertIn(name, by_name)
                exp = charts.fmt_wan(self.n_year.get(key)) + "万"
                self.assertEqual(by_name[name].get("amt_disp"), exp)

    def test_no_html_sha_import_in_this_module(self):
        """本契约测不得 import hashlib（架构锁迁出后的自检）。"""
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertNotRegex(src, r"(?m)^\s*import hashlib\b")


if __name__ == "__main__":
    unittest.main()
