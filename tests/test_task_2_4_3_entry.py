#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书 2.4.3：BU 根路径入口加固 — nginx 文本锁 + 前端 helper 真路径 + 源码接线。"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _extract_location_exact_root(conf: str) -> str:
    """取出 location = / { ... } 块（不含 location /）。"""
    m = re.search(
        r"location\s+=\s+/\s*\{(.*?)\n\s*\}",
        conf,
        flags=re.DOTALL,
    )
    if not m:
        raise AssertionError("nginx conf 缺少 location = / 块")
    return m.group(1)


class TestNginxRootProxiesBackend(unittest.TestCase):
    def test_location_exact_root_proxy_no_try_files_index(self):
        p = ROOT / "deploy" / "linux" / "nginx-kanban.conf"
        self.assertTrue(p.is_file(), p)
        t = p.read_text(encoding="utf-8")
        body = _extract_location_exact_root(t)
        self.assertIn("proxy_pass", body)
        self.assertIn("kanban_api", body)
        self.assertNotIn("try_files", body)
        self.assertNotIn("index.html", body)
        # 其它 SPA 路由仍可 try_files（location / 非 =）
        self.assertRegex(t, r"location\s+/\s*\{[^}]*try_files", re.DOTALL)


class TestBuEntryRedirectHelperShipped(unittest.TestCase):
    """驱动仓库内真实 helper 源文件（esbuild 打包后 node 执行），禁止在测试里重写算法。"""

    def test_helper_file_exports_and_behavior(self):
        src = ROOT / "frontend" / "src" / "utils" / "buEntryRedirect.ts"
        self.assertTrue(src.is_file(), src)
        text = src.read_text(encoding="utf-8")
        for name in (
            "shouldRedirectRootToBu",
            "buPathFromSession",
            "isOverallForbiddenError",
            "isPureBuSession",
            "firstBuName",
        ):
            self.assertIn(f"export function {name}", text)

        # 用 esbuild 把真源码打成 CJS，再在 node 里 assert（无则 skip 结构测已覆盖 export）
        esbuild = ROOT / "frontend" / "node_modules" / "esbuild" / "bin" / "esbuild"
        node = subprocess.run(["which", "node"], capture_output=True, text=True)
        if node.returncode != 0 or not esbuild.is_file():
            self.skipTest("本机无 node/esbuild，helper 行为测跳过（export 与接线测仍执行）")

        out = ROOT / "frontend" / "node_modules" / ".cache_bu_entry_2_4_3.cjs"
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [
                str(esbuild),
                str(src),
                "--bundle",
                "--platform=node",
                "--format=cjs",
                f"--outfile={out}",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT / "frontend"),
        )
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)

        script = r"""
const m = require(%r);
const assert = require('assert');
// pure BU on /
let p = m.shouldRedirectRootToBu('/', { can_main: false, is_admin: false, bus: ['多语营销'] });
assert.strictEqual(p, '/bu/' + encodeURIComponent('多语营销'));
// admin / overall → null
assert.strictEqual(m.shouldRedirectRootToBu('/', { can_main: true, bus: ['多语营销'] }), null);
assert.strictEqual(m.shouldRedirectRootToBu('/', { is_admin: true, bus: [] }), null);
// already on bu path
assert.strictEqual(m.shouldRedirectRootToBu('/bu/x', { bus: ['多语营销'] }), null);
// 403 overall error
assert.strictEqual(m.isOverallForbiddenError(new Error('无整体驾驶舱权限')), true);
assert.strictEqual(m.isOverallForbiddenError(new Error('network')), false);
assert.strictEqual(m.buPathFromSession({ bus: ['数据'], can_main: false }), '/bu/' + encodeURIComponent('数据'));
console.log('buEntryRedirect_ok');
""" % str(out)
        r2 = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(r2.returncode, 0, r2.stderr or r2.stdout)
        self.assertIn("buEntryRedirect_ok", r2.stdout)


class TestFrontendWiring(unittest.TestCase):
    def test_app_and_store_use_helper(self):
        app = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        store = (ROOT / "frontend" / "src" / "stores" / "cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("buEntryRedirect", app)
        self.assertIn("shouldRedirectRootToBu", app)
        self.assertIn("fetchSession", app)
        self.assertIn("buEntryRedirect", store)
        self.assertIn("isOverallForbiddenError", store)
        self.assertIn("buPathFromSession", store)
        # logout path consistency in auth
        auth = (ROOT / "src" / "routes" / "auth.py").read_text(encoding="utf-8")
        self.assertIn('delete_cookie(COOKIE, path="/"', auth)
        self.assertIn('delete_cookie(VCOOKIE, path="/"', auth)


if __name__ == "__main__":
    unittest.main(verbosity=2)
