#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书36·A：GZipMiddleware 对 fragments JSON 生效；PNG 导出路径不被 gzip 破坏。

驱动真实 create_app + TestClient（不 mock 中间件）。
httpx/TestClient 会自动解压 body，但保留 content-encoding / content-length（压缩后长度）。
验收：头含 content-encoding:gzip；content-length < 明文 len；body 可 json.loads。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import bu  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402


def _big_fragments() -> dict:
    """构造 >1KB 的 fragments 桩，确保触发 GZipMiddleware.minimum_size。"""
    pad = "x" * 2500
    return {
        "title": "t",
        "particles": pad,
        "logo": "",
        "version": "v",
        "generated_at": "",
        "pw_modal": "",
        "period_bar": "",
        "kpi_views": pad,
        "trend_html": "",
        "donut_views": "",
        "pl_views": "",
        "profit_rank_views": "",
        "receipts_budget": "",
        "daily_html": "",
        "rank_views": "",
        "drawer": "",
    }


class TestGzipFragments(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        p = bu.config_path(self.cfg, self.tmp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"bus": [{"name": "BU甲", "销售": ["销售A"]}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": server.DEFAULT_PW},
                {"账号": "overall", "显示名": "整体", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        server._state["user_html"] = "<html><body>MAIN</body></html>"
        server._state["summary"] = {"meta": {"year": 2026, "year_key": "2026年"}, "periods": {}}
        server._state["fragments"] = _big_fragments()
        server._state["views"] = {"year_key": "2026年", "period_keys": ["2026年"], "rankings_view": {}}
        server._state["bu_pages"] = {}
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_middleware_registered(self):
        names = [getattr(m, "cls", type(None)).__name__ for m in self.app.user_middleware]
        self.assertIn("GZipMiddleware", names)
        self.assertEqual(server.GZIP_MINIMUM_SIZE, 1000)

    def test_fragments_content_encoding_gzip(self):
        c = self._client()
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        r = c.get(
            "/api/v1/cockpit/fragments",
            headers={"Accept-Encoding": "gzip", "Accept": "application/json"},
        )
        self.assertEqual(r.status_code, 200)
        enc = (r.headers.get("content-encoding") or "").lower()
        self.assertEqual(enc, "gzip", f"期望 content-encoding=gzip，实际 headers={dict(r.headers)}")
        # TestClient 已解压 body → 可直接 json.loads；content-length 仍是 wire 压缩长度
        plain_len = len(r.content)
        body = r.json()
        self.assertEqual(body.get("mode"), "fragments")
        self.assertIn("fragments", body)
        cl = r.headers.get("content-length")
        self.assertIsNotNone(cl)
        gzip_len = int(cl)
        self.assertLess(gzip_len, plain_len, f"压缩后 content-length={gzip_len} 应 < 明文 {plain_len}")
        self.assertGreater(plain_len, server.GZIP_MINIMUM_SIZE)
        print(f"[gzip-evidence] plain={plain_len} content-length(gzip)={gzip_len} ratio={gzip_len / plain_len:.2%}")

    def test_export_png_still_valid_png_bytes(self):
        """PNG 路径：响应仍是 image/png，body（客户端解压后）以 PNG 魔数开头。"""
        png_magic = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1200  # >1KB 可触发 gzip

        def _fake_shot(html, blk="", width=1440):
            return png_magic

        old = getattr(server, "_screenshot_png", None)
        server._screenshot_png = _fake_shot
        try:
            c = self._client()
            c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
            r = c.get("/export.png", headers={"Accept-Encoding": "gzip"})
            self.assertEqual(r.status_code, 200, getattr(r, "text", "")[:200])
            data = r.content
            self.assertTrue(
                data.startswith(b"\x89PNG\r\n\x1a\n"),
                f"PNG 魔数丢失 enc={r.headers.get('content-encoding')} head={data[:16]!r}",
            )
            self.assertEqual(r.headers.get("content-type", "").split(";")[0].strip(), "image/png")
        finally:
            if old is not None:
                server._screenshot_png = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
