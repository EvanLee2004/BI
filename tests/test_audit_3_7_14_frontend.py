# -*- coding: utf-8 -*-
"""3.7.14 前端：010 世代/abort · 017 session 单飞 · H20 文案结构守卫。

直驱 shipped 纯函数（node strip-types 或内嵌 mjs 同源模块）；禁止在测试中重写业务逻辑。
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class Test010GenerationAndAbort(unittest.TestCase):
    def test_fetch_race_pure_module_stale_discard(self):
        """乱序：旧世代不得 apply。"""
        mod = FE / "utils" / "fetchRace.ts"
        self.assertTrue(mod.is_file(), "frontend/src/utils/fetchRace.ts 必须存在")
        # 直驱 shipped 纯函数
        script = f"""
import {{ isStaleGeneration, bumpGeneration }} from '{mod.as_posix()}';
let g = 0;
const a = bumpGeneration(() => {{ g += 1; return g; }});
const b = bumpGeneration(() => {{ g += 1; return g; }});
if (a === b) throw new Error('gens equal');
if (!isStaleGeneration(b, a)) throw new Error('old gen should be stale');
if (isStaleGeneration(b, b)) throw new Error('current should not be stale');
console.log('ok');
"""
        r = subprocess.run(
            ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=30,
        )
        if r.returncode != 0 and "experimental-strip-types" in (r.stderr or ""):
            # fallback：用同目录 .mjs 镜像（由实现同步）
            mjs = FE / "utils" / "fetchRace.mjs"
            self.assertTrue(mjs.is_file(), f"node strip-types failed and no mjs: {r.stderr}")
            script2 = script.replace(mod.as_posix(), mjs.as_posix())
            r = subprocess.run(
                ["node", "--input-type=module", "-e", script2],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
                timeout=30,
            )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok", r.stdout)

    def test_api_client_supports_signal(self):
        src = (FE / "api" / "client.ts").read_text(encoding="utf-8")
        self.assertIn("signal", src)
        self.assertRegex(src, r"apiGet\s*<|function apiGet|export async function apiGet")
        # AbortSignal 接入 fetch
        self.assertTrue(
            "signal" in src and "fetch(" in src,
            "apiGet 须把 signal 传给 fetch",
        )

    def test_cockpit_store_aborts_or_generations_on_reload(self):
        src = (FE / "stores" / "cockpit.ts").read_text(encoding="utf-8")
        self.assertTrue(
            "AbortController" in src
            or "loadGen" in src
            or "fetchGeneration" in src
            or "isStaleGeneration" in src
            or "createGenerationGate" in src
            or "vmLoadGate" in src
            or "isStale" in src,
            "cockpit store 须 abort 或世代号丢弃过期响应",
        )


class Test017SessionSingleflight(unittest.TestCase):
    def test_session_singleflight_module(self):
        mod = FE / "utils" / "sessionSingleflight.ts"
        alt = FE / "api" / "client.ts"
        # 单飞可在 client 或独立模块
        blob = ""
        if mod.is_file():
            blob = mod.read_text(encoding="utf-8")
        blob += "\n" + alt.read_text(encoding="utf-8")
        self.assertTrue(
            "inflight" in blob.lower() or "singleflight" in blob.lower() or "sessionInflight" in blob
            or "inFlight" in blob,
            "session 拉取须单飞/去重",
        )
        self.assertTrue(
            "invalidate" in blob.lower() or "clearSession" in blob or "sessionInflight = null" in blob
            or "inflight = null" in blob.lower(),
            "登出/登录成功须能失效 session 缓存",
        )

    def test_session_singleflight_behavior_node(self):
        mod = FE / "utils" / "sessionSingleflight.ts"
        mjs = FE / "utils" / "sessionSingleflight.mjs"
        target = mod if mod.is_file() else mjs
        self.assertTrue(target.is_file(), "sessionSingleflight 模块须存在")
        script = f"""
import {{ createSessionSingleflight }} from '{target.as_posix()}';
let calls = 0;
const sf = createSessionSingleflight(async () => {{
  calls += 1;
  await new Promise(r => setTimeout(r, 30));
  return {{ n: calls }};
}});
const [a, b] = await Promise.all([sf.get(), sf.get()]);
if (calls !== 1) throw new Error('expected 1 call got ' + calls);
if (a.n !== b.n) throw new Error('results diverge');
sf.invalidate();
const c = await sf.get();
if (calls !== 2) throw new Error('after invalidate expected 2 got ' + calls);
if (c.n !== 2) throw new Error('bad result');
console.log('ok');
"""
        r = subprocess.run(
            ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=30,
        )
        if r.returncode != 0:
            if mjs.is_file():
                script2 = script.replace(mod.as_posix(), mjs.as_posix()) if mod.is_file() else script
                r = subprocess.run(
                    ["node", "--input-type=module", "-e", script2],
                    capture_output=True,
                    text=True,
                    cwd=str(ROOT),
                    timeout=30,
                )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok", r.stdout)


class TestH20ExpenseCopy(unittest.TestCase):
    def test_expense_or_ledger_copy_distinguishes_caliber(self):
        exp = (FE / "components" / "ExpenseSection.vue").read_text(encoding="utf-8")
        led = (FE / "components" / "LedgerTable.vue").read_text(encoding="utf-8")
        blob = exp + "\n" + led
        # 须出现业务BU/原始行 与 分摊/图表 口径区分之一组清晰中文
        has_raw = "业务BU" in blob and ("原始" in blob or "台账行" in blob or "明细" in blob)
        has_alloc = "分摊" in blob or "图表" in blob or "饼" in blob or "期间费用" in blob
        self.assertTrue(has_raw and has_alloc, "H20 费用区文案须区分饼/分摊与明细业务BU 原始行")


if __name__ == "__main__":
    unittest.main()
