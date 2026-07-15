#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：src/*.py 不得内嵌 HTML 标记（div/span/table/html/script）。
新 HTML 只能进 static/templates/。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# 验收与 OBJECTIVE 对齐的标签集合（注释行可豁免）
FORBIDDEN = re.compile(r"<(div|span|table|html|script)\b", re.I)


class TestNoHtmlInPy(unittest.TestCase):
    def test_no_forbidden_tags_in_src_py(self):
        hits = []
        for p in sorted(SRC.glob("*.py")):
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                # 文档字符串里的示例：整行若是纯注释式说明仍拦；仅 # 豁免
                if FORBIDDEN.search(line):
                    hits.append(f"{p.name}:{i}: {line.strip()[:120]}")
        self.assertEqual(hits, [], "src/*.py 含 HTML 标记：\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
