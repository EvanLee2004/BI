# -*- coding: utf-8 -*-
"""S7 / stage_2_6_9_s7: theme.css 与 components+tokens 不得同名 class。

守卫驱动磁盘上真实 CSS 文件；提取逻辑与 scripts/css_class_dup.py 共用。
红→绿：临时注入同名 class 必须失败，还原后必须通过。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import css_class_dup  # noqa: E402

SCRATCH = Path(
    "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-d67e79681e6e/implementer"
)


class TestNoDupClassesThemeVsComponents(unittest.TestCase):
    def test_intersection_empty(self):
        inter = sorted(css_class_dup.intersection_classes())
        self.assertEqual(
            inter,
            [],
            "theme.css 与 components/*.css+tokens.css 不得同名 class，冲突: "
            + ", ".join(f".{c}" for c in inter),
        )

    def test_extractor_sees_known_pre_fix_names_in_components(self):
        """回归：提取器仍能看到 SPA 侧关键 dual-source 类名（防提取器被掏空）。"""
        spa = css_class_dup.spa_classes()
        for name in (
            "bu-nav",
            "bu-nav-a",
            "ledger-scroll",
            "rc-bud-bar",
            "rc-bud-h",
            "tb-today",
        ):
            self.assertIn(name, spa, f"SPA styles must still define .{name}")

    def test_red_then_green(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        red_log = SCRATCH / "css_dup_guard_red.txt"
        green_log = SCRATCH / "css_dup_guard_green.txt"
        probe = css_class_dup.COMPONENTS_DIR / "_s7_dup_probe.css"
        lines_red: list[str] = []
        try:
            theme_cls = css_class_dup.theme_classes()
            self.assertTrue(theme_cls, "theme.css must define some classes")
            candidate = None
            spa = css_class_dup.spa_classes()
            for name in sorted(theme_cls):
                if name not in spa and re_match_simple(name):
                    candidate = name
                    break
            self.assertIsNotNone(candidate, "need a theme-only class to inject")
            probe.write_text(
                f"/* s7 probe */\n.{candidate} {{ outline: 1px solid transparent; }}\n",
                encoding="utf-8",
            )
            inter = sorted(css_class_dup.intersection_classes())
            lines_red.append(f"injected=.{candidate}")
            lines_red.append(f"intersection={inter}")
            self.assertIn(candidate, inter, "injected shared class must be detected")
            lines_red.append("RED_OK")
            red_log.write_text("\n".join(lines_red) + "\n", encoding="utf-8")
        finally:
            if probe.exists():
                probe.unlink()

        inter_ok = sorted(css_class_dup.intersection_classes())
        green_log.write_text(
            f"intersection_after_restore={inter_ok}\nGREEN_OK\n",
            encoding="utf-8",
        )
        self.assertEqual(inter_ok, [], "after restore intersection must be empty")


def re_match_simple(name: str) -> bool:
    """Avoid weird tokens; prefer plain identifiers."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name)) and len(name) >= 3


if __name__ == "__main__":
    unittest.main()
