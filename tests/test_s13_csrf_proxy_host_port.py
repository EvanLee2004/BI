# -*- coding: utf-8 -*-
"""S-13：CSRF 与公网 :8001 反代 Host 口径（红→绿）。

生产复现：Origin=http://dash.besteasy.com:8001，nginx $host 丢端口 → Host 无 :8001
→ origin_mismatch 403，更新数据未启动。

本测驱动 shipped csrf_guard + nginx 模板；禁止 re-implement 判据。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NGINX = ROOT / "deploy" / "linux" / "nginx-kanban.conf"


class TestCsrfPublicPort8001(unittest.TestCase):
    """后端规范化同源：scheme + hostname + effective port。"""

    def test_dash_8001_origin_matches_host_with_port(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://dash.besteasy.com:8001",
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="127.0.0.1",  # 经本机 nginx
        )
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "origin_ok")

    def test_dash_8001_origin_vs_host_without_port_is_mismatch_unless_forwarded(self):
        """仅 Host=无端口（旧 $host）且无受控转发 → 仍 mismatch（不静默放宽）。"""
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://dash.besteasy.com:8001",
            referer=None,
            host="dash.besteasy.com",
            client_host="203.0.113.9",  # 非 loopback，不可信 XFH
            forwarded_host="dash.besteasy.com:8001",
            forwarded_proto="http",
        )
        self.assertFalse(ok)
        self.assertIn("origin", reason)

    def test_loopback_nginx_forwards_host_with_port(self):
        """本机 nginx：信任 X-Forwarded-Host 含 :8001，与 Origin 对齐。"""
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://dash.besteasy.com:8001",
            referer=None,
            host="dash.besteasy.com",  # 旧 $host 丢端口
            client_host="127.0.0.1",
            forwarded_host="dash.besteasy.com:8001",
            forwarded_proto="http",
        )
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "origin_ok")

    def test_lan_no_port_same_origin(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://192.168.30.46",
            referer=None,
            host="192.168.30.46",
            client_host="127.0.0.1",
            forwarded_host="192.168.30.46",
            forwarded_proto="http",
        )
        self.assertTrue(ok, reason)

    def test_default_http_port_equivalence(self):
        """http://host 与 Host: host:80 等价。"""
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://192.168.30.46",
            referer=None,
            host="192.168.30.46:80",
            client_host="10.0.0.2",
        )
        self.assertTrue(ok, reason)

    def test_evil_domain_403(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://evil.example",
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="127.0.0.1",
            forwarded_host="dash.besteasy.com:8001",
            forwarded_proto="http",
        )
        self.assertFalse(ok)
        self.assertIn("origin", reason)

    def test_suffix_lookalike_domain_403(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://dash.besteasy.com.evil.com:8001",
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="127.0.0.1",
            forwarded_host="dash.besteasy.com:8001",
            forwarded_proto="http",
        )
        self.assertFalse(ok)

    def test_wrong_port_403(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://dash.besteasy.com:8002",
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="127.0.0.1",
            forwarded_host="dash.besteasy.com:8001",
            forwarded_proto="http",
        )
        self.assertFalse(ok)

    def test_wrong_scheme_403(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="https://dash.besteasy.com:8001",
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="127.0.0.1",
            forwarded_host="dash.besteasy.com:8001",
            forwarded_proto="http",
        )
        self.assertFalse(ok)

    def test_missing_origin_still_fail_closed(self):
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin=None,
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="203.0.113.9",
        )
        self.assertFalse(ok)
        self.assertIn("missing_origin", reason)

    def test_ops_loopback_still_allowlisted(self):
        from csrf_guard import OPS_HEADER_VALUE, csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin=None,
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="127.0.0.1",
            ops_header=OPS_HEADER_VALUE,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "allowlisted")

    def test_untrusted_client_cannot_forge_forwarded_host(self):
        """外部客户端伪造 X-Forwarded-Host 不得放行。"""
        from csrf_guard import csrf_ok

        ok, reason = csrf_ok(
            method="POST",
            origin="http://evil.example:8001",
            referer=None,
            host="dash.besteasy.com:8001",
            client_host="198.51.100.7",
            forwarded_host="evil.example:8001",
            forwarded_proto="http",
        )
        self.assertFalse(ok)


class TestNginxPreservesExternalPort(unittest.TestCase):
    """nginx 模板：所有反代 location 保留 $http_host（含非默认端口）。"""

    def test_all_proxy_locations_use_http_host_not_bare_host(self):
        text = NGINX.read_text(encoding="utf-8")
        # 每个含真实 proxy_pass 指令的 location（忽略注释里的 proxy_pass 字样）
        blocks = re.split(r"\n\s*location\s+", text)
        proxy_blocks = []
        for b in blocks:
            lines = [
                ln
                for ln in b.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            body = "\n".join(lines)
            if re.search(r"\bproxy_pass\b", body):
                proxy_blocks.append(body)
        self.assertGreaterEqual(len(proxy_blocks), 4, "应有多处反代 location")
        for b in proxy_blocks:
            self.assertIn(
                "proxy_set_header Host $http_host",
                b,
                f"反代块必须用 $http_host 保留端口:\n{b[:200]}",
            )
            self.assertNotIn(
                "proxy_set_header Host $host;",
                b,
                "$host 会丢非默认端口，禁止",
            )
            self.assertIn(
                "proxy_set_header X-Forwarded-Host $http_host",
                b,
                "须显式传 X-Forwarded-Host 供后端受控信任",
            )

    def test_no_global_host_dollar_host_proxy(self):
        text = NGINX.read_text(encoding="utf-8")
        self.assertNotIn("proxy_set_header Host $host;", text)
        self.assertGreaterEqual(text.count("proxy_set_header Host $http_host"), 4)


if __name__ == "__main__":
    unittest.main()
