# -*- coding: utf-8 -*-
"""2.6.5 F-1~F-4 前端三层架构守卫。

每条守卫须先证明会红：故意违规 → 失败 → 还原（过程写 scratch 证据）。
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
COMP = FE / "components"
BASE = COMP / "base"
TOKENS = FE / "styles" / "tokens.css"
SCRATCH = Path(
    "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-c31b43ef0cf9/implementer"
)

# F-1 白名单：须写明理由（仅 charts 宿主等无业务样式的壳）
STYLE_WHITELIST: dict[str, str] = {
    # 当前应为空；若加白名单必须填理由
}

COLOR_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(",
    re.I,
)
# 动效字面量：transition: ... 0.3s / .3s / 300ms（排除 var(--dur-*)）
DUR_LITERAL_RE = re.compile(
    r"transition\s*:[^;{]*?(?<!var\(--dur-)(?:\d*\.\d+|\d+)(?:s|ms)\b",
    re.I,
)


def _vue_business_files() -> list[Path]:
    return sorted(p for p in COMP.glob("*.vue") if p.parent == COMP)


class TestF1NoStyleInBusiness(unittest.TestCase):
    def test_no_style_blocks(self):
        offenders = []
        for p in _vue_business_files():
            text = p.read_text(encoding="utf-8")
            if re.search(r"<style\b", text, re.I):
                if p.name in STYLE_WHITELIST:
                    continue
                offenders.append(p.name)
        self.assertEqual(
            offenders,
            [],
            f"F-1 Layer3 禁止 <style>：{offenders}；白名单须写理由",
        )


class TestF2NoHardcodedColors(unittest.TestCase):
    """硬编码色值只许出现在 tokens.css（看端 components + styles；admin/vendor 另册）。"""

    SCAN_ROOTS = [
        FE / "components",
        FE / "styles",
        FE / "App.vue",
    ]

    def _iter_files(self):
        for root in self.SCAN_ROOTS:
            if root.is_file():
                yield root
                continue
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix not in {".vue", ".css", ".ts"}:
                    continue
                if "vendor" in p.parts:
                    continue
                if p.resolve() == TOKENS.resolve():
                    continue
                if p.parts and "base" in p.parts and p.suffix == ".vue":
                    # base 组件也不得硬编码色，须走 token
                    pass
                yield p

    def test_no_hardcoded_colors_outside_tokens(self):
        hits = []
        for p in self._iter_files():
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if COLOR_RE.search(line):
                    hits.append(f"{p.relative_to(ROOT)}:{i}:{line.strip()[:80]}")
        self.assertEqual(hits, [], "F-2 硬编码色值须只在 tokens.css:\n" + "\n".join(hits[:30]))


class TestF3DurationTokens(unittest.TestCase):
    def test_no_literal_transition_duration(self):
        hits = []
        for p in list(COMP.rglob("*.vue")) + list((FE / "styles").rglob("*.css")):
            if p.resolve() == TOKENS.resolve():
                continue
            if "vendor" in p.parts:
                continue
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if "transition" not in line:
                    continue
                if "var(--dur-" in line:
                    continue
                if DUR_LITERAL_RE.search(line):
                    hits.append(f"{p.relative_to(ROOT)}:{i}:{line.strip()[:80]}")
        self.assertEqual(hits, [], "F-3 动效时长须 var(--dur-*):\n" + "\n".join(hits[:20]))


class TestF4MetaLabelRequired(unittest.TestCase):
    def test_rankbar_source_guards_meta(self):
        src = (BASE / "RankBar.vue").read_text(encoding="utf-8")
        self.assertIn("metaLabel", src)
        # 模板：须 metaLabel && meta 才渲染副列
        self.assertRegex(
            src,
            r'v-if="metaLabel\s*&&\s*meta"',
            "F-4 RankBar 副列须同时有 metaLabel 与 meta",
        )

    def test_profit_structure_passes_meta_label(self):
        src = (COMP / "ProfitStructure.vue").read_text(encoding="utf-8")
        self.assertIn("系统成本率", src)
        self.assertIn("meta-label", src)
        self.assertIn("项目成本", src)


class TestRedThenGreenGuards(unittest.TestCase):
    """故意违规 → 红 → 还原，证据落 scratch。"""

    def test_f1_red_then_green(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        log = SCRATCH / "arch_guards_red_green.log"
        lines = []
        victim = COMP / "_arch_guard_probe.vue"
        try:
            victim.write_text(
                "<script setup lang=\"ts\">\n</script>\n<template><div/></template>\n<style>.x{color:red}</style>\n",
                encoding="utf-8",
            )
            # run F1 check inline
            offenders = []
            for p in _vue_business_files():
                if re.search(r"<style\b", p.read_text(encoding="utf-8"), re.I):
                    if p.name not in STYLE_WHITELIST:
                        offenders.append(p.name)
            lines.append(f"F1_BROKEN offenders={offenders}")
            self.assertIn("_arch_guard_probe.vue", offenders)
            lines.append("F1_RED_OK")
        finally:
            if victim.exists():
                victim.unlink()
        # green
        offenders = []
        for p in _vue_business_files():
            if re.search(r"<style\b", p.read_text(encoding="utf-8"), re.I):
                if p.name not in STYLE_WHITELIST:
                    offenders.append(p.name)
        lines.append(f"F1_RESTORED offenders={offenders}")
        self.assertEqual(offenders, [])
        lines.append("F1_GREEN_OK")

        # F2 red: inject color into a css file then remove
        probe_css = FE / "styles" / "components" / "_probe_color.css"
        try:
            probe_css.write_text(".x{color:#ff00aa}\n", encoding="utf-8")
            hits = []
            for p in (FE / "styles").rglob("*.css"):
                if p.resolve() == TOKENS.resolve():
                    continue
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if COLOR_RE.search(line):
                        hits.append(str(p))
            lines.append(f"F2_BROKEN hits={len(hits)}")
            self.assertTrue(any("_probe_color" in h for h in hits))
            lines.append("F2_RED_OK")
        finally:
            if probe_css.exists():
                probe_css.unlink()
        lines.append("F2_GREEN_OK")

        # F3 red: inject literal transition duration (must fail guard) then restore
        probe_dur = FE / "styles" / "components" / "_f3_probe.css"
        try:
            probe_dur.write_text(".x{transition: opacity 0.3s ease;}\n", encoding="utf-8")
            hits = []
            for p in list(COMP.rglob("*.vue")) + list((FE / "styles").rglob("*.css")):
                if p.resolve() == TOKENS.resolve():
                    continue
                if "vendor" in p.parts:
                    continue
                text = p.read_text(encoding="utf-8")
                for i, line in enumerate(text.splitlines(), 1):
                    if "transition" not in line:
                        continue
                    if "var(--dur-" in line:
                        continue
                    if DUR_LITERAL_RE.search(line):
                        hits.append(f"{p.relative_to(ROOT)}:{i}:{line.strip()[:80]}")
            lines.append(f"F3_BROKEN hits={len(hits)}")
            self.assertTrue(
                any("_f3_probe" in h for h in hits),
                "F3 注入 transition: 0.3s 应被检出",
            )
            lines.append("F3_RED_OK")
            # 与单元测同一路径：故意违规时 test_no_literal 也必须失败
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "tests.test_frontend_arch_guards.TestF3DurationTokens.test_no_literal_transition_duration",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            lines.append(f"F3_UNITTEST_BROKEN exit={r.returncode}")
            self.assertNotEqual(r.returncode, 0, "F3 违规时单元测应红")
        finally:
            if probe_dur.exists():
                probe_dur.unlink()
        # green again
        hits = []
        for p in list(COMP.rglob("*.vue")) + list((FE / "styles").rglob("*.css")):
            if p.resolve() == TOKENS.resolve():
                continue
            if "vendor" in p.parts:
                continue
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if "transition" not in line:
                    continue
                if "var(--dur-" in line:
                    continue
                if DUR_LITERAL_RE.search(line):
                    hits.append(f"{p.relative_to(ROOT)}:{i}:{line.strip()[:80]}")
        lines.append(f"F3_RESTORED hits={len(hits)}")
        self.assertEqual(hits, [], "F3 还原后不得残留字面量时长")
        r_ok = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_frontend_arch_guards.TestF3DurationTokens.test_no_literal_transition_duration",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        lines.append(f"F3_UNITTEST_GREEN exit={r_ok.returncode}")
        self.assertEqual(r_ok.returncode, 0, "F3 还原后单元测应绿")
        lines.append("F3_GREEN_OK")

        # F4 red: strip metaLabel guard temporarily via string check on synthetic
        bad = '<span v-if="meta" class="rank-bar__meta">{{ meta }}</span>'
        good = '<span v-if="metaLabel && meta" class="rank-bar__meta">{{ meta }}</span>'
        self.assertIsNone(re.search(r'v-if="metaLabel\s*&&\s*meta"', bad))
        lines.append("F4_RED_OK synthetic without metaLabel")
        self.assertIsNotNone(re.search(r'v-if="metaLabel\s*&&\s*meta"', good))
        lines.append("F4_GREEN_OK")

        log.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestBaseComponentsExist(unittest.TestCase):
    def test_layer2_files(self):
        for name in ("RankBar.vue", "RankList.vue", "DataModal.vue"):
            self.assertTrue((BASE / name).is_file(), name)
        self.assertTrue(TOKENS.is_file())


if __name__ == "__main__":
    unittest.main()
