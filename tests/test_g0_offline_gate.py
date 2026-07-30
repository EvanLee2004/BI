# -*- coding: utf-8 -*-
"""G0：可信离线门禁自测（脱敏 fixture、真实 skip 统计、manifest 契约、3.5 专项入口）。

驱动真实 scripts/materialize_offline_fixtures + run_verify 清单，禁止 re-implement。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "tests" / "fixtures" / "offline_seed"
VERIFY = ROOT / "tests" / "run_verify.sh"
MANIFEST_SCHEMA = ROOT / "docs" / "验收证据" / "3_6_0" / "live" / "manifest.schema.json"
PY = sys.executable


class TestOfflineFixtureMaterialize(unittest.TestCase):
    def test_seed_present_and_synthetic(self):
        self.assertTrue(SEED.is_dir(), "offline_seed must exist")
        for name in (
            "下单.xlsx",
            "项目明细.xlsx",
            "回款记录.xlsx",
            "手填与调整.xlsx",
            "收单台账.xlsx",
            "内部译员.xlsx",
            "看板账号.json",
            "BU配置.json",
        ):
            self.assertTrue((SEED / name).is_file(), name)
        acc = json.loads((SEED / "看板账号.json").read_text(encoding="utf-8"))
        accounts = acc.get("accounts") or []
        self.assertGreaterEqual(len(accounts), 3)
        for a in accounts:
            self.assertNotEqual(a.get("账号"), "lushasha")
            # 允许与 DEFAULT_PW 字面量对齐的测试口令；禁止生产真人账号名
            self.assertTrue(str(a.get("密码") or "").strip())

    def test_materialize_deterministic_hashes(self):
        script = ROOT / "scripts" / "materialize_offline_fixtures.py"
        r = subprocess.run(
            [PY, str(script), "--check-hash"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hash check OK", r.stdout)

    def test_materialize_rejects_missing_seed_file(self):
        """临时破坏 seed 必须红，恢复后由其它用例绿。"""
        script = ROOT / "scripts" / "materialize_offline_fixtures.py"
        target = SEED / "下单.xlsx"
        bak = target.read_bytes()
        try:
            target.unlink()
            r = subprocess.run(
                [PY, str(script)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(r.returncode, 0, "broken seed must fail materialize")
            self.assertTrue(
                "missing seed file" in (r.stderr + r.stdout)
                or "下单.xlsx" in (r.stderr + r.stdout),
                r.stderr + r.stdout,
            )
        finally:
            target.write_bytes(bak)


class TestVerifyIncludes35AndRuntimeSkip(unittest.TestCase):
    def test_run_verify_lists_key_customers_3_5(self):
        text = VERIFY.read_text(encoding="utf-8")
        self.assertIn("tests/test_key_customers_3_5_0.py", text)
        self.assertIn("tests/test_g0_offline_gate.py", text)

    def test_run_verify_reports_runtime_counts_not_only_static_sites(self):
        text = VERIFY.read_text(encoding="utf-8")
        # 必须汇总本轮 passed/failed/skipped
        self.assertRegex(text, r"passed|FAILED|skipped|runtime")
        self.assertIn("RUNTIME_SKIP", text)
        self.assertIn("CRITICAL_SKIP", text)
        # 禁止仅用静态位点当完成标准（静态可保留作参考，但关键 skip 必须拦门禁）
        self.assertIn("关键 skip", text)

    def test_offline_profile_wired(self):
        text = VERIFY.read_text(encoding="utf-8")
        self.assertIn("materialize_offline_fixtures", text)
        # e2e 步可单独 PROFILE=dev；禁止全局 export 污染单测临时 root
        self.assertIn("KANBAN_PROFILE=dev", text)
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#"):
                continue
            self.assertFalse(
                s.startswith("export KANBAN_PROFILE="),
                f"must not globally export KANBAN_PROFILE: {s}",
            )


class TestLiveManifestSchema(unittest.TestCase):
    REQUIRED = (
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

    def test_schema_file_exists(self):
        self.assertTrue(MANIFEST_SCHEMA.is_file(), MANIFEST_SCHEMA)

    def _load_lm(self):
        import importlib.util

        p = ROOT / "scripts" / "live_manifest.py"
        spec = importlib.util.spec_from_file_location("live_manifest_g0", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_incomplete_manifest_entry_fails_validator(self):
        lm = self._load_lm()
        bad = {
            "commit": "abc",
            "route": "/",
            # missing viewport/theme/fixture/steps/expected/actual/image
        }
        ok, errs = lm.validate_entry(bad)
        self.assertFalse(ok)
        self.assertTrue(errs)

    def test_complete_manifest_entry_passes(self):
        lm = self._load_lm()
        good = {
            "commit": "ef90dc4d43a42656f99b3411112a5737014c460b",
            "route": "/",
            "viewport": "1440x900",
            "theme": "neon",
            "fixture": "offline_seed",
            "steps": ["open /", "wait kpi"],
            "expected": "税前利润主卡可见",
            "actual": "pending capture",
            "image": "docs/验收证据/3_6_0/live/placeholder.png",
        }
        ok, errs = lm.validate_entry(good)
        self.assertTrue(ok, errs)
        self.assertEqual(errs, [])


class TestNoRealSecretsInSeed(unittest.TestCase):
    def test_seed_bytes_no_production_tokens(self):
        # 禁止生产真人账号 / 飞书通道痕迹；DEFAULT_PW 字面量 kanban2026 允许（与 server 测试约定对齐）
        banned = (b"lushasha", b"feishu", b"webhook")
        for p in SEED.rglob("*"):
            if not p.is_file() or p.suffix in {".xlsx", ".xls"}:
                continue
            if p.suffix.lower() not in {".json", ".md", ".txt", ".csv"}:
                continue
            raw = p.read_bytes().lower()
            for b in banned:
                self.assertNotIn(b, raw, f"{p} has {b!r}")


if __name__ == "__main__":
    unittest.main()
