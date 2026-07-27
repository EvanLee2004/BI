# -*- coding: utf-8 -*-
"""2.6.10 V-4：看端原生 alert/confirm/prompt 零命中。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = [
    ROOT / "frontend/src/components",
    ROOT / "frontend/src/App.vue",
    ROOT / "frontend/src/stores",
]
# 管理端除外
SKIP_PARTS = ("/admin/",)


class TestNoNativeAlert(unittest.TestCase):
    def test_zero_native_dialogs_in_cockpit(self):
        pat = re.compile(r"\b(alert|confirm|prompt)\s*\(")
        hits = []
        files = []
        for base in SCAN:
            if base.is_file():
                files.append(base)
            else:
                files.extend(base.rglob("*.{vue,ts,js}".replace("{vue,ts,js}", "*")))
                files = [f for f in files if f.suffix in (".vue", ".ts", ".js")]
        for f in files:
            sp = str(f).replace("\\", "/")
            if any(s in sp for s in SKIP_PARTS):
                continue
            text = f.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if pat.search(line) and "showToast" not in line:
                    # 允许注释
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                        continue
                    hits.append(f"{f.relative_to(ROOT)}:{i}:{line.strip()}")
        self.assertEqual(hits, [], "原生 dialog 残留:\n" + "\n".join(hits))

    def test_toast_helper_exists(self):
        self.assertTrue((ROOT / "frontend/src/utils/toast.ts").is_file())
        self.assertTrue((ROOT / "frontend/src/components/base/Toast.vue").is_file())


if __name__ == "__main__":
    unittest.main()
