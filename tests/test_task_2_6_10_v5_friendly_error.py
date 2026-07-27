# -*- coding: utf-8 -*-
"""2.6.10 V-5：驱动真实 TS friendlyError + 源码路径不得把 HTTP 串写给用户。"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
TSX_MOD = FE / "src" / "utils" / "friendlyError.ts"
SCRATCH = Path(
    "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-e22137297bc1/implementer"
)


def _tsx_eval(expr: str) -> str:
    """用 npx tsx 真 import 源码模块（非 Python 镜像）。"""
    script = f"""
import {{ friendlyFromStatus, friendlyError, friendlyMessage, hasTechLeak }} from {json.dumps(str(TSX_MOD))};
const out = {expr};
process.stdout.write(typeof out === 'string' ? out : JSON.stringify(out));
"""
    r = subprocess.run(
        ["npx", "--yes", "tsx", "-e", script],
        cwd=str(FE),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise AssertionError(f"tsx failed: {r.stderr or r.stdout}")
    return r.stdout


class TestRealFriendlyErrorTs(unittest.TestCase):
    def test_status_map_no_http_digits(self):
        for code in (401, 403, 404, 409, 500, 502, 503, 504):
            msg = _tsx_eval(f"friendlyFromStatus({code})")
            self.assertNotRegex(msg, r"HTTP\s*\d", msg)
            self.assertFalse(
                re.search(r"TypeError|Traceback|Exception", msg, re.I), msg
            )

    def test_http_string_scrubbed(self):
        self.assertEqual(_tsx_eval("hasTechLeak('HTTP 500')"), "true")
        msg = _tsx_eval("friendlyMessage('HTTP 500')")
        self.assertNotRegex(msg, r"HTTP\s*\d")
        self.assertIn("暂时", msg)

    def test_api_error_like_object(self):
        msg = _tsx_eval("friendlyError({ status: 403 })")
        self.assertIn("权限", msg)
        self.assertNotRegex(msg, r"HTTP")

    def test_network_message(self):
        msg = _tsx_eval("friendlyMessage('Failed to fetch')")
        self.assertIn("服务", msg)
        self.assertNotRegex(msg, r"HTTP|fetch", re.I)


class TestCockpitNoHttpLeakInSource(unittest.TestCase):
    """看端组件：禁止把 `HTTP ${status}` / detail 原样写进用户可见状态。"""

    FORBIDDEN = re.compile(
        r"""(\.detail\s*\|\|\s*['\"]HTTP|['\"]HTTP\s*['\"]?\s*\+\s*r\.status|`HTTP\s*\$\{)"""
    )

    def test_daily_query_uses_friendly(self):
        src = (FE / "src/components/DailyQuery.vue").read_text(encoding="utf-8")
        self.assertIn("friendlyError", src)
        self.assertIn("ApiError", src)
        self.assertNotRegex(src, self.FORBIDDEN)

    def test_ledger_uses_friendly(self):
        src = (FE / "src/components/LedgerTable.vue").read_text(encoding="utf-8")
        self.assertIn("friendlyError", src)
        self.assertIn("ApiError", src)
        self.assertNotRegex(src, self.FORBIDDEN)

    def test_client_api_error(self):
        src = (FE / "src/api/client.ts").read_text(encoding="utf-8")
        self.assertIn("class ApiError", src)
        self.assertIn("friendlyFromStatus", src)
        # 不得用 HTTP ${status} 作为用户 message 兜底
        self.assertNotIn("`HTTP ${r.status}`", src)

    def test_app_auth_required(self):
        app = (FE / "src/App.vue").read_text(encoding="utf-8")
        self.assertIn("authRequired", app)
        self.assertNotIn("error.includes('未登录')", app)
        self.assertIn("ErrorState", app)


class TestFriendlyRedGreenLog(unittest.TestCase):
    def test_red_then_green_logged(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        log = SCRATCH / "v5_error_mapping_red_green.log"
        # 红：旧串 hasTechLeak
        red = _tsx_eval("hasTechLeak('HTTP 500')")
        self.assertEqual(red, "true")
        # 绿：映射后
        green_msg = _tsx_eval("friendlyMessage('HTTP 500')")
        green = _tsx_eval(f"hasTechLeak({json.dumps(green_msg)})")
        self.assertEqual(green, "false")
        log.write_text(
            f"RED hasTechLeak(HTTP 500)={red}\n"
            f"GREEN friendlyMessage={green_msg!r} hasTechLeak={green}\n"
            f"403={_tsx_eval('friendlyFromStatus(403)')!r}\n",
            encoding="utf-8",
        )
        # 副本到证据目录
        evid = ROOT / "docs" / "验收证据" / "2_6_10" / "v5_error_mapping_red_green.log"
        evid.parent.mkdir(parents=True, exist_ok=True)
        evid.write_text(log.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
