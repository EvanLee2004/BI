# -*- coding: utf-8 -*-
"""3.7.21：看端口径脚注全员不渲染。直驱 shipped Vue / dist / 后端路由源码，禁止在测试里重写业务逻辑。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
DIST_ASSETS = ROOT / "frontend" / "dist" / "assets"
COCKPIT = ROOT / "src" / "routes" / "cockpit.py"

FORBIDDEN_PHRASES = (
    "已剔成本/非利润表",
    "无行≠上方无费用",
    "无明细行不等于上方无费用",
)
FORBIDDEN_MARKERS = (
    'data-testid="exp-caliber-note"',
    'data-testid="ledger-caliber-note"',
    'class="exp-caliber-note"',
    'class="ledger-caliber-note"',
)


def _vue_blob() -> str:
    exp = (FE / "components" / "ExpenseSection.vue").read_text(encoding="utf-8")
    led = (FE / "components" / "LedgerTable.vue").read_text(encoding="utf-8")
    return exp + "\n" + led


class TestCaliberNotesHidden3721(unittest.TestCase):
    def test_t1_viewer_vue_does_not_render_caliber_notes(self):
        blob = _vue_blob()
        for needle in FORBIDDEN_MARKERS + FORBIDDEN_PHRASES:
            self.assertNotIn(needle, blob, f"看端 Vue 仍含口径脚注: {needle}")
        led = (FE / "components" / "LedgerTable.vue").read_text(encoding="utf-8")
        self.assertIn("显示全部台账记录", led)

    def test_t2_dist_js_omits_footnote_phrases(self):
        self.assertTrue(DIST_ASSETS.is_dir(), "frontend/dist/assets 必须存在")
        files = list(DIST_ASSETS.glob("*.js"))
        self.assertTrue(files, "dist/assets 下应有 js")
        hits: list[str] = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for needle in FORBIDDEN_PHRASES:
                if needle in text:
                    hits.append(f"{path.name}:{needle}")
        self.assertEqual(hits, [], f"committed dist 仍含口径脚注: {hits}")

    def test_t3_backend_caliber_note_still_present(self):
        src = COCKPIT.read_text(encoding="utf-8")
        self.assertIn("caliber_note", src)
        self.assertIn("业务BU", src)


if __name__ == "__main__":
    unittest.main()
