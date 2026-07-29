#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.3.0 用户统计：action/bu_bucket 解析、聚合 KPI、API 鉴权、config_changes 默认去访问。"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sqlite3  # noqa: E402

import accounts  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import schema  # noqa: E402
import server  # noqa: E402
from db.access_stats import (  # noqa: E402
    aggregate_user_stats,
    list_access_events,
    parse_action,
    resolve_bu_bucket,
)


def _insert(conn, t: str, account: str, cat: str, summary: str) -> None:
    conn.execute(
        "INSERT INTO manual_配置变更(时间,操作账号,类别,摘要) VALUES(?,?,?,?)",
        (t, account, cat, summary),
    )


class TestParseActionAndBucket(unittest.TestCase):
    def test_parse_action_matrix(self):
        self.assertEqual(parse_action("访问", "登录成功：lushasha"), "login_ok")
        self.assertEqual(parse_action("登录", "管理员 form 登录成功"), "login_ok")
        self.assertEqual(parse_action("访问", "登录失败：x"), "login_fail")
        self.assertEqual(parse_action("访问", "管理端退出（会话版本+1）"), "logout")
        self.assertEqual(parse_action("访问", "导出：收入明细"), "export")
        self.assertEqual(parse_action("访问", "看端明细VM"), "detail_vm")
        self.assertEqual(parse_action("访问", "看端明细：费用明细"), "detail_vm")
        self.assertEqual(parse_action("访问", "其它未知"), "other_access")
        self.assertIsNone(parse_action("设置", "改了计划时间"))
        self.assertIsNone(parse_action("账号", "新增账号"))

    def test_bu_bucket_rules(self):
        self.assertEqual(resolve_bu_bucket(None), "未登记账号")
        self.assertEqual(resolve_bu_bucket({"权限": "管理员"}), "管理员")
        self.assertEqual(resolve_bu_bucket({"权限": "整体"}), "整体")
        self.assertEqual(resolve_bu_bucket({"权限": "游戏"}), "游戏")
        self.assertEqual(
            resolve_bu_bucket({"权限": "BU", "可见BU": ["游戏", "数据"]}),
            "游戏、数据",
        )
        self.assertEqual(resolve_bu_bucket({"权限": "BU", "可见BU": []}), "BU")
        self.assertEqual(resolve_bu_bucket({"权限": ""}), "其他")


class TestAggregatePure(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "t.db"
        self.conn = sqlite3.connect(self.db_path)
        schema.create_all(self.conn)
        self.now = datetime(2026, 7, 29, 15, 0, 0)
        self.accs = [
            {"账号": "lushasha", "显示名": "管理员", "权限": "管理员"},
            {"账号": "overall", "显示名": "整体", "权限": "整体"},
            {"账号": "bu_game", "显示名": "游戏号", "权限": "游戏"},
            {"账号": "multi", "显示名": "多BU", "权限": "BU", "可见BU": ["游戏", "数据"]},
        ]

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_kpi_login_ok_excludes_detail(self):
        base = self.now.strftime("%Y-%m-%d %H:%M:%S")
        # 3 login_ok
        for i in range(3):
            _insert(self.conn, base, "lushasha", "访问", f"登录成功：lushasha#{i}")
        # 2 login_fail
        for i in range(2):
            _insert(self.conn, base, "ghost", "访问", f"登录失败：ghost#{i}")
        # 5 detail_vm
        for i in range(5):
            _insert(self.conn, base, "overall", "访问", f"看端明细VM#{i}")
        self.conn.commit()

        out = aggregate_user_stats(self.conn, self.accs, days=30, now=self.now)
        self.assertEqual(out["kpi"]["login_ok"], 3)
        self.assertEqual(out["kpi"]["login_fail"], 2)
        self.assertEqual(out["kpi"]["detail_vm"], 5)
        self.assertEqual(out["kpi"]["active_accounts"], 1)
        actions = {a["action"]: a["count"] for a in out["by_action"]}
        self.assertEqual(actions.get("login_ok"), 3)
        self.assertEqual(actions.get("detail_vm"), 5)
        # detail 不得并入 login_ok
        self.assertNotEqual(out["kpi"]["login_ok"], out["kpi"]["login_ok"] + out["kpi"]["detail_vm"])

        keys = set(out.keys())
        for k in (
            "days",
            "window_start",
            "window_end",
            "kpi",
            "by_account",
            "by_bu",
            "by_action",
            "daily_login_ok",
            "note",
        ):
            self.assertIn(k, keys)

    def test_bu_bucket_admin_and_overall(self):
        t = self.now.strftime("%Y-%m-%d %H:%M:%S")
        _insert(self.conn, t, "lushasha", "访问", "登录成功：lushasha")
        _insert(self.conn, t, "overall", "访问", "登录成功：overall")
        _insert(self.conn, t, "bu_game", "访问", "登录成功：bu_game")
        _insert(self.conn, t, "multi", "访问", "登录成功：multi")
        _insert(self.conn, t, "unknown_x", "访问", "登录成功：unknown_x")
        self.conn.commit()
        out = aggregate_user_stats(self.conn, self.accs, days=30, now=self.now)
        by_acc = {r["account"]: r for r in out["by_account"]}
        self.assertEqual(by_acc["lushasha"]["bu_bucket"], "管理员")
        self.assertEqual(by_acc["overall"]["bu_bucket"], "整体")
        self.assertEqual(by_acc["bu_game"]["bu_bucket"], "游戏")
        self.assertEqual(by_acc["multi"]["bu_bucket"], "游戏、数据")
        self.assertEqual(by_acc["unknown_x"]["bu_bucket"], "未登记账号")
        # 多 BU 不拆行：by_bu 只有一条拼接桶，login_ok=1
        multi_bu = [b for b in out["by_bu"] if b["bu_bucket"] == "游戏、数据"]
        self.assertEqual(len(multi_bu), 1)
        self.assertEqual(multi_bu[0]["login_ok"], 1)

    def test_days_window_excludes_outside(self):
        inside = (self.now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        outside = (self.now - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
        _insert(self.conn, inside, "lushasha", "访问", "登录成功：in")
        _insert(self.conn, outside, "lushasha", "访问", "登录成功：out")
        self.conn.commit()
        out7 = aggregate_user_stats(self.conn, self.accs, days=7, now=self.now)
        self.assertEqual(out7["kpi"]["login_ok"], 1)
        out30 = aggregate_user_stats(self.conn, self.accs, days=30, now=self.now)
        self.assertEqual(out30["kpi"]["login_ok"], 1)
        out0 = aggregate_user_stats(self.conn, self.accs, days=0, now=self.now)
        self.assertEqual(out0["kpi"]["login_ok"], 2)

    def test_events_filter_and_page(self):
        t = self.now.strftime("%Y-%m-%d %H:%M:%S")
        _insert(self.conn, t, "lushasha", "访问", "登录成功：a")
        _insert(self.conn, t, "lushasha", "访问", "登录失败：b")
        _insert(self.conn, t, "overall", "访问", "看端明细VM")
        self.conn.commit()
        all_ev = list_access_events(self.conn, self.accs, days=30, now=self.now)
        self.assertEqual(all_ev["total"], 3)
        fail = list_access_events(
            self.conn, self.accs, days=30, action="login_fail", now=self.now
        )
        self.assertEqual(fail["total"], 1)
        self.assertEqual(fail["items"][0]["action"], "login_fail")
        self.assertIn("label", fail["items"][0])
        self.assertIn("bu_bucket", fail["items"][0])


class TestConfigChangesDefaultExcludeAccess(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "t.db"
        self.conn = sqlite3.connect(self.db_path)
        schema.create_all(self.conn)
        t = "2026-07-29 12:00:00"
        _insert(self.conn, t, "a", "访问", "登录成功：a")
        _insert(self.conn, t, "a", "访问", "看端明细VM")
        _insert(self.conn, t, "a", "设置", "更新时间改为 09:30")
        _insert(self.conn, t, "a", "账号", "新增账号 x")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_excludes_access(self):
        rows = db.list_config_changes(self.conn, None, 200)
        cats = {r["类别"] for r in rows}
        self.assertNotIn("访问", cats)
        self.assertIn("设置", cats)
        self.assertIn("账号", cats)

    def test_explicit_category_access_still_works(self):
        rows = db.list_config_changes(self.conn, "访问", 200)
        self.assertTrue(rows)
        self.assertTrue(all(r["类别"] == "访问" for r in rows))


class TestUserStatsHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "数据").mkdir()
        shutil.copy2(ROOT / "config.json", cls.tmp / "config.json")
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            cls.cfg,
            cls.tmp,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管理员",
                    "权限": "管理员",
                    "密码": server.DEFAULT_PW,
                },
                {
                    "账号": "overall",
                    "显示名": "整体",
                    "权限": "整体",
                    "密码": server.DEFAULT_VIEW_PW,
                },
            ],
        )
        # 建库并插入合成访问行
        conn = db.connect(cls.cfg, cls.tmp)
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for i in range(3):
                _insert(conn, now, "lushasha", "访问", f"登录成功：lushasha#{i}")
            for i in range(2):
                _insert(conn, now, "x", "访问", f"登录失败：x#{i}")
            for i in range(5):
                _insert(conn, now, "overall", "访问", f"看端明细VM#{i}")
            _insert(conn, now, "lushasha", "设置", "改了备份天数")
            conn.commit()
        finally:
            conn.close()

        server._state["has_data"] = True
        server._state["admin_html"] = "x"
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.TC = TestClient

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _admin(self):
        c = self.TC(self.app, follow_redirects=False)
        r = c.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": server.DEFAULT_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return c

    def _viewer(self):
        c = self.TC(self.app, follow_redirects=False)
        r = c.post(
            "/api/v1/login",
            json={"account": "overall", "password": server.DEFAULT_VIEW_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return c

    def test_admin_user_stats_200_and_keys(self):
        c = self._admin()
        r = c.get("/api/v1/admin/user_stats?days=30")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        for k in (
            "days",
            "window_start",
            "window_end",
            "kpi",
            "by_account",
            "by_bu",
            "by_action",
            "daily_login_ok",
            "note",
        ):
            self.assertIn(k, d)
        # 预置 3 login_ok + 登录 API 自身再写 1 条「登录成功」审计 → ≥3
        self.assertGreaterEqual(d["kpi"]["login_ok"], 3)
        self.assertEqual(d["kpi"]["login_fail"], 2)
        self.assertEqual(d["kpi"]["detail_vm"], 5)
        # 看端明细不得并入登录成功
        self.assertNotEqual(d["kpi"]["login_ok"], d["kpi"]["detail_vm"])
        actions = {a["action"]: a["count"] for a in d["by_action"]}
        self.assertEqual(actions.get("detail_vm"), 5)
        self.assertGreaterEqual(actions.get("login_ok", 0), 3)

        re = c.get("/api/v1/admin/user_stats/events?days=30&limit=50")
        self.assertEqual(re.status_code, 200, re.text)
        ed = re.json()
        self.assertIn("total", ed)
        self.assertIn("items", ed)
        self.assertGreaterEqual(ed["total"], 10)
        item = ed["items"][0]
        for k in ("id", "time", "account", "action", "label", "summary", "bu_bucket"):
            self.assertIn(k, item)

    def test_unauth_401(self):
        c = self.TC(self.app, follow_redirects=False)
        r = c.get("/api/v1/admin/user_stats?days=30")
        self.assertEqual(r.status_code, 401)
        r2 = c.get("/api/v1/admin/user_stats/events")
        self.assertEqual(r2.status_code, 401)

    def test_viewer_not_200(self):
        c = self._viewer()
        r = c.get("/api/v1/admin/user_stats?days=30")
        self.assertNotEqual(r.status_code, 200, r.text)
        self.assertIn(r.status_code, (401, 403))

    def test_config_changes_default_no_access(self):
        c = self._admin()
        r = c.get("/api/v1/admin/config_changes")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d.get("excluded_access_by_default"))
        for row in d.get("changes") or []:
            self.assertNotEqual(row.get("类别"), "访问", row)

    def test_config_changes_explicit_access(self):
        c = self._admin()
        r = c.get("/api/v1/admin/config_changes?category=" + "访问")
        self.assertEqual(r.status_code, 200, r.text)
        rows = r.json().get("changes") or []
        self.assertTrue(any(x.get("类别") == "访问" for x in rows))


class TestFrontendStructure(unittest.TestCase):
    def test_nav_and_route_and_page(self):
        layout = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(encoding="utf-8")
        # 顺序：展示 → 数据调整 → 异常处理 → 用户统计 → 设置
        i_see = layout.index(">展示</div>")
        i_edit = layout.index(">数据调整</div>")
        i_rev = layout.index(">异常处理</div>")
        i_users = layout.index(">用户统计</div>")
        i_cfg = layout.index(">设置</div>")
        self.assertLess(i_see, i_edit)
        self.assertLess(i_edit, i_rev)
        self.assertLess(i_rev, i_users)
        self.assertLess(i_users, i_cfg)
        self.assertIn("showGroup('users')", layout)
        self.assertIn("group === 'users'", layout)

        router = (ROOT / "frontend/src/admin/router.ts").read_text(encoding="utf-8")
        self.assertIn("path: 'users'", router)
        self.assertIn("group: 'users'", router)
        self.assertIn("UserStatsView", router)

        page = (ROOT / "frontend/src/admin/views/UserStatsView.vue").read_text(encoding="utf-8")
        self.assertIn("user-stats-page", page)
        self.assertIn("login_ok", page)
        self.assertIn("看端明细不计入登录次数", page)
        self.assertIn("loadEcharts", page)
        self.assertNotIn("from 'echarts'", page)
        self.assertNotIn('from "echarts"', page)

        audit = (ROOT / "frontend/src/admin/views/AuditView.vue").read_text(encoding="utf-8")
        self.assertIn("用户统计", audit)

    def test_version_file(self):
        v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(v, "3.3.0")


if __name__ == "__main__":
    unittest.main()
