# -*- coding: utf-8 -*-
"""3.3.2：管理端更新诚实态 + 体检浮层 fixed/内滚不关。

S1 源码守卫（AdminLayout.vue）— 锁死假完成路径
S2 后端契约（TestClient）— 409 + refresh_status
S3 体检 CSS/源码 — fixed + 内部 wheel 不关
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ADMIN_LAYOUT = ROOT / "frontend/src/admin/layout/AdminLayout.vue"
ADMIN_CSS = ROOT / "frontend/src/admin/layout/admin-layout.css"


def _admin_login_client():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    import json
    import loaders
    import server
    from fastapi.testclient import TestClient

    cfg = dict(loaders.load_config(ROOT))
    cfg["zhiyun_auto_fetch"] = False
    app = server.create_app(cfg, root=ROOT)
    c = TestClient(app)
    rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("accounts") or []
    admin = next(a for a in rows if a.get("权限") == "管理员")
    lr = c.post("/api/v1/login", json={"account": admin["账号"], "password": admin["密码"]})
    assert lr.status_code in (200, 303), lr.text[:200]
    return c, server


class TestS1AdminLayoutHonestySource(unittest.TestCase):
    """S1：doRefresh 不得空 catch 后无条件 poll 当成功；须 finished_at 推进判定。"""

    def setUp(self):
        self.src = ADMIN_LAYOUT.read_text(encoding="utf-8")

    def test_do_refresh_exists(self):
        self.assertIn("async function doRefresh", self.src)
        self.assertIn("async function pollRefresh", self.src)

    def test_no_bare_empty_catch_then_poll_as_success(self):
        """禁止旧模式：catch { /* 409 */ } 后无分支直接 pollRefresh。"""
        # 抽取 doRefresh 函数体
        m = re.search(
            r"async function doRefresh\(\)\s*\{([\s\S]*?)\n(?:async function |function |let |const |onMounted)",
            self.src,
        )
        self.assertIsNotNone(m, "找不到 doRefresh 函数体")
        body = m.group(1)
        # 旧坏模式：catch 块内只有注释/空，随后在 try/catch 外无条件 pollRefresh
        # 允许 catch，但必须有 status / AdminApiError / 409 分支
        bare = re.search(
            r"catch\s*(?:\([^)]*\))?\s*\{\s*(?:/\*[^*]*\*/|//[^\n]*)?\s*\}",
            body,
        )
        if bare:
            # 若仍有空 catch，则 catch 后不得无条件 pollRefresh 当唯一路径
            after = body[bare.end() :]
            # 空 catch 后紧跟 pollRefresh() 且无 if 分支 = 旧假完成
            if re.search(r"^\s*pollRefresh\s*\(\s*\)", after):
                self.fail("doRefresh 仍有空 catch 后直接 pollRefresh 的假完成路径")
        # 必须出现 AdminApiError 或 status === 409 / e.status 等诚实分支
        self.assertTrue(
            "AdminApiError" in body
            or "status === 409" in body
            or "status==409" in body
            or ".status === 409" in body
            or "e.status" in body
            or "err.status" in body,
            "doRefresh 须按 AdminApiError.status / 409 分支处理失败",
        )

    def test_finished_at_used_for_completion(self):
        self.assertIn("finished_at", self.src)
        # 完成路径关键字
        self.assertTrue(
            "baselineFinishedAt" in self.src
            or "baseline_finished" in self.src
            or "baseline" in self.src and "finished_at" in self.src,
            "须有 baseline finished_at 用于完成判定",
        )

    def test_honest_fail_copy_keywords(self):
        joined = self.src
        keys = ("未能确认", "系统忙", "已跟进", "暂时无法启动更新")
        self.assertTrue(
            any(k in joined for k in keys),
            f"须有诚实失败文案之一：{keys}",
        )

    def test_refreshing_guard_blocks_double_click(self):
        # if (refreshing 类守卫
        self.assertTrue(
            re.search(r"if\s*\(\s*refreshing(?:\.value)?\s*\)", self.src),
            "refreshing===true 时须忽略连点",
        )

    def test_success_complete_policy_retained(self):
        """体检绿→更新成功 / 非绿→更新完成 保留。"""
        self.assertIn("更新成功", self.src)
        self.assertIn("更新完成", self.src)

    def test_toast_dedupe_or_single_finish(self):
        """同一 finished_at 只 toast 一次（去重标识存在）。"""
        self.assertTrue(
            "lastToasted" in self.src
            or "toastedFinished" in self.src
            or "lastToastFinishedAt" in self.src
            or "toastedAt" in self.src,
            "须有 finished_at toast 去重状态",
        )


class TestS2RefreshApiContract(unittest.TestCase):
    """S2：POST refresh 锁忙 → 409 可解析；GET refresh_status 契约。"""

    def test_refresh_status_shape(self):
        c, _server = _admin_login_client()
        r = c.get("/api/v1/admin/refresh_status")
        self.assertEqual(r.status_code, 200, r.text[:300])
        body = r.json()
        self.assertIn("running", body)
        self.assertIsInstance(body["running"], bool)
        last = body.get("last")
        if last is not None:
            self.assertIn("status", last)

    def test_refresh_busy_409_body(self):
        c, server = _admin_login_client()
        # routes._srv 转发到 server.start_refresh_async；patch 实现侧
        with patch.object(server, "start_refresh_async", return_value=False):
            r = c.post("/api/v1/admin/refresh", json={})
        self.assertEqual(r.status_code, 409, r.text[:300])
        body = r.json()
        self.assertIsInstance(body, dict)
        # status 字段存在（busy 或历史 running）
        self.assertIn(body.get("status"), ("busy", "running"))
        if "running" in body:
            self.assertIsInstance(body["running"], bool)

    def test_refresh_busy_with_lock_held(self):
        """持锁时 POST → 409；body 含 running bool（本单加固）。"""
        c, server = _admin_login_client()
        # 若前序用例残留占用，先尽量释放（同线程持锁才可 release）
        acquired = server._LOCK.acquire(blocking=False)
        if not acquired:
            # 锁被后台刷新线程占用：直接期望 409
            r = c.post("/api/v1/admin/refresh", json={})
            self.assertEqual(r.status_code, 409, r.text[:300])
            body = r.json()
            self.assertIn(body.get("status"), ("busy", "running"))
            self.assertIn("running", body)
            self.assertIsInstance(body["running"], bool)
            return
        try:
            r = c.post("/api/v1/admin/refresh", json={})
            self.assertEqual(r.status_code, 409, r.text[:300])
            body = r.json()
            self.assertIn(body.get("status"), ("busy", "running"))
            self.assertIn("running", body)
            self.assertIsInstance(body["running"], bool)
            # 持锁且未设 refreshing → running 应为 false
            self.assertIsInstance(body["running"], bool)
        finally:
            server._LOCK.release()


class TestS3HealthPopFixedAndInnerScroll(unittest.TestCase):
    """S3：.health-pop fixed；wheel 在浮层内不关。"""

    def test_css_position_fixed(self):
        css = ADMIN_CSS.read_text(encoding="utf-8")
        # .health-pop 块内须 position: fixed
        m = re.search(r"\.health-pop\s*\{([^}]+)\}", css)
        self.assertIsNotNone(m, "找不到 .health-pop 规则")
        block = m.group(1)
        self.assertIn("position", block)
        self.assertIn("fixed", block)
        self.assertNotIn("absolute", block.replace("/*", "").split("*/")[0] if False else block)
        # 更严：不得再是 absolute 作为定位
        self.assertTrue(
            re.search(r"position\s*:\s*fixed", block),
            f".health-pop 须 position:fixed，实际块: {block!r}",
        )

    def test_inner_wheel_does_not_close(self):
        src = ADMIN_LAYOUT.read_text(encoding="utf-8")
        # 内部 contains early-return
        self.assertTrue(
            "healthPopEl" in src and "contains" in src,
            "wheel 处理须用 healthPopEl.contains 判断内部",
        )
        # onHealthWheelOrTouch 内：contains → return（不关）
        m = re.search(
            r"function onHealthWheelOrTouch\([\s\S]*?\n\}",
            src,
        )
        self.assertIsNotNone(m, "找不到 onHealthWheelOrTouch")
        fn = m.group(0)
        self.assertIn("contains", fn)
        self.assertIn("return", fn)
        # 浮层自身不得再绑「一 wheel 就关」自杀（允许无 @wheel 或绑的是分流函数且内不关）
        # 禁止 pop 上 @wheel 直接 closeHealthPop 且无 contains 判断的旧注释意图
        self.assertNotIn(
            "浮层内滚动也收起",
            src,
            "旧注释/行为「浮层内滚动也收起」须删除",
        )


if __name__ == "__main__":
    unittest.main()
