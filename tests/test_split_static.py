#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书36·F：前后端分离能力证明（CI 级）。

边界（如实写清）：
- 本测只证明 static/ 可在**另一端口**独立伺服，shell/JS 无硬编码 API 主机；
- 登录会话 cookie 同源限制属预期——真跨域双端口生产需 HTTPS + SameSite=None（见部署形态 MADR），
  不在本测范围；生产默认仍同端口 FastAPI 挂 /static。
"""

from __future__ import annotations

import re
import sys
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

# 硬编码绝对 API 源（host:port 或 http(s)://…/api）——壳/JS 禁止
_ABS_API = re.compile(
    r"""https?://[^\s"'`]+(?:/api|/login)|"""
    r"""(?<![\w.-])(?:localhost|127\.0\.0\.1):\d{2,5}(?:/api)?""",
    re.I,
)


class TestStaticNoHardcodedApiOrigin(unittest.TestCase):
    def test_js_and_shell_use_relative_api(self):
        hits = []
        for p in list(STATIC.rglob("*.js")) + list(STATIC.rglob("*.html")):
            text = p.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                # 用户提示文案里的「http://服务器:端口/」不算 API 源硬编码
                if "服务器" in line and "端口" in line:
                    continue
                if "file:" in line and "alert" in line:
                    continue
                if _ABS_API.search(line):
                    hits.append(f"{p.relative_to(ROOT)}:{i}:{line.strip()[:120]}")
        self.assertEqual(hits, [], "static 出现硬编码 API 源：\n" + "\n".join(hits))


class TestStaticServableOnOtherPort(unittest.TestCase):
    """static/ 用 stdlib http.server 起在随机端口，断言 shell + 关键 JS 可 GET 200。"""

    def test_shell_and_js_from_independent_static_server(self):
        self.assertTrue(STATIC.is_dir())

        class _Handler(SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=str(STATIC), **k)

            def log_message(self, *args):  # 安静
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            base = f"http://127.0.0.1:{port}"
            for path in ("/shell.html", "/shell-bu.html", "/js/assemble/page.js", "/js/cockpit.js"):
                with urlopen(base + path, timeout=5) as r:  # noqa: S310 本机测试
                    self.assertEqual(r.status, 200, path)
                    body = r.read()
                    self.assertGreater(len(body), 50, path)
            # shell 里 fragments 仍是相对路径
            with urlopen(base + "/shell.html", timeout=5) as r:  # noqa: S310
                html = r.read().decode("utf-8", errors="replace")
            self.assertIn("/api/v1/cockpit/fragments", html)
            self.assertNotIn("http://127.0.0.1:8018", html)
            self.assertNotIn("localhost:8018", html)
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
