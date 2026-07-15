#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刀4 测试：管理员端写接口（明细编辑/手填/撤销/立即更新互斥）+ db 写函数 + 归档。
跑：.venv/bin/python tests/test_admin_edit.py  （需 fastapi/httpx，venv 里已装）

策略：把 server.recompute 换成轻量桩（只翻 built_at），隔离验证「HTTP→鉴权→写库→触发重算」
这条链，不跑重渲染；「改数真改结果」的端到端已由 test_adjust.py 覆盖。
"""

import datetime
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders
import money
import server
import db  # noqa: E402
from ingest import archive  # noqa: E402


def _seed(cfg, root):
    """在 endpoints 用的同一个库里种一行收入明细 + 一行费用明细（R1 新开放字段用）。金额单位：分。"""
    conn = db.connect(cfg, root)
    conn.execute(
        "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
        " VALUES('K1','SO1','客A','传统营销','2026-07-15',100000,30000,'2026-07','2026-07-15','2026-07',0)"
    )
    conn.execute(
        "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
        " VALUES('L1','2026-06','2026-06-15',10000,'语言','管理费用','办公费','市场部','2026-06','2026-06',0)"
    )
    conn.commit()
    conn.close()


class TestAdminWrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        _seed(cls.cfg, cls.root)
        # 轻量桩：只翻 built_at，避免测试跑重渲染/重管道
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "<html>ADMIN</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(
            cls.app, follow_redirects=False
        )  # 从不登录（TestClient 会存 cookie，需独立客户端测未授权）
        # 登录拿会话
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.cookie = r.cookies.get(server.COOKIE)
        cls.hdr = {"Cookie": f"{server.COOKIE}={cls.cookie}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def _conn(self):
        return db.connect(self.cfg, self.root)

    # ---- 鉴权：写接口一律要会话 ----
    def test_write_requires_login(self):
        for method, path in [
            ("post", "/api/adjust"),
            ("post", "/api/manual"),
            ("post", "/api/refresh"),
            ("get", "/api/adjust_fields"),
            ("get", "/api/adjustments"),
            ("post", "/api/adjust/1/revoke"),
        ]:
            r = getattr(self.anon, method)(path)  # 未登录：_require 在函数体首行先拦，body 走默认
            self.assertEqual(r.status_code, 401, f"{method} {path} 未登录应 401")

    # ---- 明细编辑：写调整 + 触发重算 + 台账+1，原值由服务端从库取 ----
    def test_adjust_records_and_recomputes(self):
        server._state["built_at"] = "OLD"
        r = self.client.post(
            "/api/adjust",
            headers=self.hdr,
            json={
                "目标表": "std_收入明细",
                "定位键": "K1",
                "字段": "交付额",
                "新值": 2000,
                "原因": "测试改值",
                "类型": "改值",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("adj_id", r.json())
        self.assertEqual(server._state["built_at"], "RECOMPUTED")  # 触发了秒级重算
        # 台账里能查到，且原值=服务端从库读的元文本（1000 元=100000 分；不是前端传的）
        adjs = self.client.get("/api/adjustments", headers=self.hdr).json()
        mine = [a for a in adjs if a["字段"] == "交付额" and a["定位键"] == "K1"]
        self.assertTrue(mine)
        self.assertEqual(str(mine[0]["原值"]), "100000")  # 分
        self.assertEqual(mine[0]["新值"], "2000")  # 管理端按元录入
        self.assertEqual(mine[0]["类型"], "改值")

    def test_adjust_bad_field_400(self):
        r = self.client.post(
            "/api/adjust",
            headers=self.hdr,
            json={"目标表": "std_收入明细", "定位键": "K1", "字段": "不存在的字段", "新值": "x", "类型": "改值"},
        )
        self.assertEqual(r.status_code, 400)

    def test_adjust_bad_table_400(self):
        r = self.client.post(
            "/api/adjust",
            headers=self.hdr,
            json={"目标表": "std_不存在", "定位键": "K1", "字段": "交付额", "新值": 1, "类型": "改值"},
        )
        self.assertEqual(r.status_code, 400)

    def test_remove_soft_delete_records(self):
        r = self.client.post(
            "/api/adjust",
            headers=self.hdr,
            json={"目标表": "std_收入明细", "定位键": "K1", "字段": "", "新值": "", "原因": "剔除", "类型": "剔除"},
        )
        self.assertEqual(r.status_code, 200, r.text)

    def test_revoke_adjustment(self):
        conn = self._conn()
        aid = db.add_adjustment(conn, "明昊", "std_收入明细", "K1", "交付额", "9999", "待撤", "改值")
        conn.close()
        r = self.client.post(f"/api/adjust/{aid}/revoke", headers=self.hdr, json={})
        self.assertEqual(r.status_code, 200, r.text)
        conn = self._conn()
        st = conn.execute("SELECT 状态 FROM adj_调整记录 WHERE id=?", (aid,)).fetchone()[0]
        conn.close()
        self.assertEqual(st, "已撤销")

    # ---- 手填：当月覆盖 + 留痕 manual_历史 ----
    def test_manual_write_and_history(self):
        r = self.client.post(
            "/api/manual", headers=self.hdr, json={"归属月": "2026-07", "项目": "营销人力成本", "金额": 5000}
        )
        self.assertEqual(r.status_code, 200, r.text)
        # 再写一次覆盖
        r2 = self.client.post(
            "/api/manual", headers=self.hdr, json={"归属月": "2026-07", "项目": "营销人力成本", "金额": 6000}
        )
        self.assertEqual(r2.status_code, 200)
        conn = self._conn()
        cur = conn.execute("SELECT 金额 FROM manual_手填 WHERE 归属月='2026-07' AND 项目='营销人力成本'").fetchone()
        hist = conn.execute("SELECT COUNT(*) FROM manual_历史 WHERE 项目='营销人力成本'").fetchone()[0]
        conn.close()
        self.assertEqual(int(cur[0]), 600000)  # 6000 元 = 600000 分
        self.assertGreaterEqual(hist, 2)  # 两次都留痕

    def test_manual_unknown_item_400(self):
        r = self.client.post(
            "/api/manual", headers=self.hdr, json={"归属月": "2026-07", "项目": "不在枚举里", "金额": 1}
        )
        self.assertEqual(r.status_code, 400)

    def test_manual_non_number_400(self):
        r = self.client.post(
            "/api/manual", headers=self.hdr, json={"归属月": "2026-07", "项目": "营销人力成本", "金额": "abc"}
        )
        self.assertEqual(r.status_code, 400)

    # ---- R1：字段下拉从服务端下发（全部可调列），新开放字段可写、黑名单字段 400 ----
    def test_adjust_fields_served_full_lists(self):
        r = self.client.get("/api/adjust_fields", headers=self.hdr)
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual(set(j), {"收入明细", "下单", "回款", "内部译员", "费用明细"})
        self.assertIn("预算归属部门", j["费用明细"])  # 新开放字段进了下拉
        self.assertIn("客户", j["收入明细"])
        for fields in j.values():  # 黑名单字段不下发
            for banned in ("id", "定位键", "归属月", "已删除"):
                self.assertNotIn(banned, fields)

    def test_adjust_new_open_field_ok(self):
        r = self.client.post(
            "/api/adjust",
            headers=self.hdr,
            json={
                "目标表": "std_费用明细",
                "定位键": "L1",
                "字段": "预算归属部门",
                "新值": "数据部",
                "原因": "测试R1",
                "类型": "改值",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)

    def test_adjust_blacklist_field_400(self):
        for banned in ("定位键", "归属月", "原值_归属月", "已删除"):
            r = self.client.post(
                "/api/adjust",
                headers=self.hdr,
                json={"目标表": "std_费用明细", "定位键": "L1", "字段": banned, "新值": "x", "类型": "改值"},
            )
            self.assertEqual(r.status_code, 400, f"{banned} 应 400")

    # ---- 更新数据：运行中互斥 → 409 ----
    def test_refresh_mutex_returns_409(self):
        self.assertTrue(server._LOCK.acquire(blocking=False))
        try:
            r = self.client.post("/api/refresh", headers=self.hdr, json={})
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.json().get("status"), "running")
        finally:
            server._LOCK.release()

    def test_console_says_update_data_not_immediate(self):
        """顶栏按钮文案=「更新数据」；导航「数据调整 / 人工填写」。"""
        html = server.admin_ui_source()
        self.assertIn(">更新数据</button>", html)
        self.assertNotIn(">立即更新</button>", html)
        self.assertIn("onclick=\"showGroup('edit')\">数据调整</div>", html)
        self.assertNotIn(">改数据</div>", html)
        self.assertIn('onclick="showManual()">人工填写</button>', html)
        self.assertIn("exportDetail", html)
        self.assertIn("导出 Excel", html)

    def test_detail_export_xlsx(self):
        """明细导出：真 xlsx、表头+行、管理员鉴权。"""
        import io
        import openpyxl

        # 无会话 → 401
        self.assertEqual(self.anon.get("/api/detail_export?table=收入明细").status_code, 401)
        # 有/无数据都返回合法 xlsx（至少表头）
        r = self.client.get("/api/detail_export?table=收入明细", headers=self.hdr)
        self.assertEqual(r.status_code, 200, r.text[:200])
        ctype = (r.headers.get("content-type") or r.headers.get("Content-Type") or "").lower()
        self.assertIn("spreadsheetml", ctype)
        cd = (r.headers.get("content-disposition") or r.headers.get("Content-Disposition") or "").lower()
        self.assertIn(".xlsx", cd)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb.active
        headers = [c.value for c in ws[1]]
        self.assertIn("定位键", headers)
        self.assertIn("交付额", headers)

    # ---- 更新数据：后台跑+状态轮询（_do_full 打桩，不跑真管道） ----
    def test_refresh_async_and_status(self):
        import time as _t

        orig = server._do_full
        server._do_full = lambda cfg, root, trigger: {"result": "绿"}
        try:
            r = self.client.post("/api/refresh", headers=self.hdr, json={})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json().get("status"), "started")
            for _ in range(50):  # 最多等 5s，后台线程应瞬间跑完
                s = self.client.get("/api/refresh_status", headers=self.hdr).json()
                if not s["running"]:
                    break
                _t.sleep(0.1)
            self.assertFalse(s["running"])
            self.assertEqual(s["last"]["status"], "ok")
            self.assertEqual(s["last"]["result"], "绿")
        finally:
            server._do_full = orig

    # ---- 设置：读/写/校验（config.json 写进临时 root，不碰真配置） ----
    def test_settings_roundtrip_and_validation(self):
        import json as _json
        import shutil as _sh

        _sh.copy2(ROOT / "config.json", self.root / "config.json")
        r = self.client.get("/api/settings", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        self.assertIn("schedule_time", r.json())
        # 非法值 → 400
        for bad in (
            {"schedule_time": "25:00"},
            {"schedule_time": "9点半"},
            {"backup_keep_days": 0},
            {"backup_keep_days": "abc"},
        ):
            r = self.client.post("/api/settings", headers=self.hdr, json=bad)
            self.assertEqual(r.status_code, 400, f"{bad} 应 400")
        # 合法保存 → cfg 即时生效 + 文件落盘
        r = self.client.post(
            "/api/settings",
            headers=self.hdr,
            json={"schedule_time": "08:45", "backup_keep_days": 7, "zhiyun_auto_fetch": False},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.cfg["schedule_time"], "08:45")
        self.assertEqual(self.cfg["backup_keep_days"], 7)
        # F-01 修复：落机器本地覆盖文件、**config.json 不被改动**（部署机 git 工作区不脏→一键更新可用）
        before_cfg = _json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        ov = _json.loads((self.root / "数据" / loaders.LOCAL_CONFIG_NAME).read_text(encoding="utf-8"))
        self.assertEqual(ov["schedule_time"], "08:45")
        self.assertEqual(ov["backup_keep_days"], 7)
        self.assertEqual(_json.loads((self.root / "config.json").read_text(encoding="utf-8")), before_cfg)

    def test_settings_zhiyun_creds(self):
        """智云账号：GET 可见 / 改了才写+清旧会话 / 空值 400 / 同值不动。"""
        import json as _json
        import shutil as _sh

        _sh.copy2(ROOT / "config.json", self.root / "config.json")
        zp = loaders.data_dir(self.cfg, self.root) / "智云配置.json"
        zp.parent.mkdir(parents=True, exist_ok=True)
        zp.write_text(
            _json.dumps(
                {
                    "username": "old.user",
                    "password": "oldpw",
                    "md_pss_id": "OLDTOKEN",
                    "account_id": "OLDACC",
                    "base_url": "http://x",
                }
            ),
            encoding="utf-8",
        )
        r = self.client.get("/api/settings", headers=self.hdr)
        self.assertEqual(r.json()["zhiyun_username"], "old.user")
        # 改账号 → 写入 + 清 md_pss_id/account_id（下次更新强制新账号重登、自动取新GUID）
        r = self.client.post(
            "/api/settings", headers=self.hdr, json={"zhiyun_username": "new.user", "zhiyun_password": "newpw"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("智云账号已更新", r.json()["note"])
        d = _json.loads(zp.read_text(encoding="utf-8"))
        self.assertEqual((d["username"], d["password"]), ("new.user", "newpw"))
        self.assertEqual((d["md_pss_id"], d["account_id"]), ("", ""))
        self.assertEqual(d["base_url"], "http://x")  # 其余键保留
        # 同值再存 → 不算变更（不清会话）
        r = self.client.post(
            "/api/settings", headers=self.hdr, json={"zhiyun_username": "new.user", "zhiyun_password": "newpw"}
        )
        self.assertNotIn("智云账号已更新", r.json()["note"])
        # 空密码 → 400
        r = self.client.post(
            "/api/settings", headers=self.hdr, json={"zhiyun_username": "new.user", "zhiyun_password": ""}
        )
        self.assertEqual(r.status_code, 400)

    def test_settings_zhiyun_conn(self):
        """智云连接配置（服务器/四表ID）：GET 返回生效默认值；改了写覆盖层+清会话；
        存回默认值=删除覆盖；config.json 始终不动（F-01）。"""
        import json as _json
        import shutil as _sh
        from ingest import fetch_zhiyun as fz

        _sh.copy2(ROOT / "config.json", self.root / "config.json")
        before_cfg = (self.root / "config.json").read_text(encoding="utf-8")
        # GET：无本地文件也返回内置默认（部署机开箱即用）
        r = self.client.get("/api/settings", headers=self.hdr)
        conn = r.json()["zhiyun_conn"]
        self.assertEqual(conn["base_url"], fz.ZHIYUN_DEFAULTS["base_url"])
        self.assertEqual(conn["tables"]["orders"], fz.ZHIYUN_DEFAULTS["tables"]["orders"]["worksheetId"])
        # 改服务器地址+一张表 → 写 智云配置.json 覆盖层 + 清旧会话
        zp = loaders.data_dir(self.cfg, self.root) / "智云配置.json"
        zp.parent.mkdir(parents=True, exist_ok=True)
        zp.write_text(_json.dumps({"md_pss_id": "OLDTOK"}), encoding="utf-8")
        tables = dict(conn["tables"])
        tables["orders"] = "my-custom-ws"
        r = self.client.post(
            "/api/settings", headers=self.hdr, json={"zhiyun_base_url": "http://new-host:9", "zhiyun_tables": tables}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("智云连接配置已更新", r.json()["note"])
        d = _json.loads(zp.read_text(encoding="utf-8"))
        self.assertEqual(d["base_url"], "http://new-host:9")
        self.assertEqual(d["tables"]["orders"]["worksheetId"], "my-custom-ws")
        self.assertNotIn("receipts", d.get("tables", {}))  # 未改动的表不写覆盖
        self.assertEqual(d["md_pss_id"], "")  # 换服务器清旧会话
        # 同值再存 → 无变更
        r = self.client.post(
            "/api/settings", headers=self.hdr, json={"zhiyun_base_url": "http://new-host:9", "zhiyun_tables": tables}
        )
        self.assertNotIn("智云连接配置已更新", r.json()["note"])
        # 存回内置默认 → 覆盖项被删除（文件精简、以后跟着代码默认走）
        r = self.client.post(
            "/api/settings",
            headers=self.hdr,
            json={
                "zhiyun_base_url": fz.ZHIYUN_DEFAULTS["base_url"],
                "zhiyun_tables": {s: fz.ZHIYUN_DEFAULTS["tables"][s]["worksheetId"] for s in fz.SOURCES},
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        d = _json.loads(zp.read_text(encoding="utf-8"))
        self.assertNotIn("base_url", d)
        self.assertNotIn("tables", d)
        # 空值 → 400
        r = self.client.post("/api/settings", headers=self.hdr, json={"zhiyun_base_url": "", "zhiyun_tables": tables})
        self.assertEqual(r.status_code, 400)
        # F-01：全程 config.json 一个字节没动
        self.assertEqual((self.root / "config.json").read_text(encoding="utf-8"), before_cfg)

    def test_bootstrap_page_when_no_data(self):
        """F-02 鸡生蛋修复：admin_html 未生成（空机器首次部署）→ 管理员登录后出引导页
        （可填智云账号+触发立即更新），而不是死板一句"数据尚未生成"；有 admin_html 则正常页。"""
        old = server._state["admin_html"]
        try:
            server._state["admin_html"] = ""  # 模拟首次部署：从未取数成功
            r = self.client.get("/admin", headers=self.hdr)
            self.assertEqual(r.status_code, 200)
            for anchor in ("首次取数", 'id="go"', "/api/settings", "/api/refresh"):
                self.assertIn(anchor, r.text, f"引导页缺锚点 {anchor}")
            self.assertNotIn("数据尚未生成", r.text)
            # 未登录仍是登录页，不给引导页（引导页会回显智云账号）
            r = self.anon.get("/admin")
            self.assertNotIn("首次取数", r.text)
        finally:
            server._state["admin_html"] = old
        r = self.client.get("/admin", headers=self.hdr)  # 有数据 → 正常管理端，不出引导页
        self.assertNotIn("首次取数", r.text)

    def test_settings_requires_login(self):
        self.assertEqual(self.anon.get("/api/settings").status_code, 401)
        self.assertEqual(self.anon.post("/api/settings", json={}).status_code, 401)
        self.assertEqual(self.anon.get("/api/refresh_status").status_code, 401)
        self.assertEqual(self.anon.get("/api/history").status_code, 401)
        self.assertEqual(self.anon.get("/api/history/20260710").status_code, 401)

    def test_export_png(self):
        """导出图片：截图函数打桩，验证 PNG 返回/文件名头/未知周期400。"""
        orig = server._screenshot_png
        server._screenshot_png = lambda html, blk="", width=1440: b"\x89PNGFAKE"
        orig_sum = server._state.get("summary")
        server._state["summary"] = {"periods": {"2026年": {}, "2026年3月": {}}, "meta": {"year_key": "2026年"}}
        try:
            r = self.client.get("/export.png")  # 用户端功能：无需登录
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.headers["content-type"], "image/png")
            self.assertIn("filename", r.headers["content-disposition"])
            self.assertEqual(r.content, b"\x89PNGFAKE")
            r = self.client.get("/export.png", params={"blk": "2026年3月"})
            self.assertEqual(r.status_code, 200)
            r = self.client.get("/export.png", params={"blk": "1999年"})
            self.assertEqual(r.status_code, 400)  # 未知周期
        finally:
            server._screenshot_png = orig
            server._state["summary"] = orig_sum

    def test_history_list_and_page(self):
        """历史快照：列表倒序 + 按天取页面 + 非法日期400 + 无档404。"""
        bdir = loaders.data_dir(self.cfg, self.root) / "备份"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "页面_20260709.html").write_text("<html>OLD</html>", encoding="utf-8")
        (bdir / "页面_20260710.html").write_text("<html>NEW</html>", encoding="utf-8")
        d = self.client.get("/api/history", headers=self.hdr).json()
        self.assertEqual([x["day"] for x in d][:2], ["20260710", "20260709"])  # 倒序
        self.assertEqual(d[0]["label"], "2026-07-10")
        r = self.client.get("/api/history/20260709", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        self.assertIn("OLD", r.text)
        self.assertEqual(self.client.get("/api/history/2026-7-9", headers=self.hdr).status_code, 400)
        self.assertEqual(self.client.get("/api/history/19990101", headers=self.hdr).status_code, 404)


class TestArchive(unittest.TestCase):
    """归档：db 每日滚动备份保留 N 份 + 月末快照判定。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.cfg = loaders.load_config()
        db.connect(self.cfg, self.root).close()  # 建出 看板.db

    def test_backup_db_rolling_keep(self):
        d0 = datetime.date(2026, 7, 1)
        for i in range(4):
            res = archive.backup_db(self.cfg, d0 + datetime.timedelta(days=i), self.root, keep=2)
            self.assertEqual(res["status"], "ok", res)
        bdir = loaders.data_dir(self.cfg, self.root) / "备份"
        kept = sorted(bdir.glob("看板_*.db"))
        self.assertEqual(len(kept), 2)  # 滚动只留最近 2 份
        self.assertTrue(kept[-1].name.endswith("20260704.db"))

    def test_backup_keep_reads_config(self):
        """keep 不传 → 用 config.backup_keep_days（设置页改的就是它）。"""
        import shutil as _sh

        tmp2 = Path(tempfile.mkdtemp())
        db.connect(self.cfg, tmp2).close()
        cfg = dict(self.cfg)
        cfg["backup_keep_days"] = 2
        d0 = datetime.date(2026, 7, 1)
        for i in range(4):
            archive.backup_db(cfg, d0 + datetime.timedelta(days=i), tmp2)
        kept = sorted((loaders.data_dir(cfg, tmp2) / "备份").glob("看板_*.db"))
        self.assertEqual(len(kept), 2)
        self.assertTrue(kept[-1].name.endswith("20260704.db"))
        _sh.rmtree(tmp2, ignore_errors=True)

    def test_snapshot_page_rolling_and_month_end(self):
        """页面快照：每天一份滚动保留 + 月末那份另存进快照存档（永久）。"""
        import shutil as _sh

        tmp2 = Path(tempfile.mkdtemp())
        cfg = dict(self.cfg)
        cfg["backup_keep_days"] = 2
        for i in range(3):  # 7/29、7/30、7/31(月末)
            d = datetime.date(2026, 7, 29) + datetime.timedelta(days=i)
            res = archive.snapshot_page(cfg, f"<html>{d}</html>", d, tmp2)
            self.assertEqual(res["status"], "ok")
        bdir = loaders.data_dir(cfg, tmp2) / "备份"
        kept = sorted(bdir.glob("页面_*.html"))
        self.assertEqual([p.name for p in kept], ["页面_20260730.html", "页面_20260731.html"])
        snap = loaders.data_dir(cfg, tmp2) / "快照存档" / "2026-07" / "页面_20260731.html"
        self.assertTrue(snap.exists())  # 月末页面永久留档
        # 同天再存 = 覆盖（留当天最后一次），份数不变
        archive.snapshot_page(cfg, "<html>v2</html>", datetime.date(2026, 7, 31), tmp2)
        self.assertEqual(len(list(bdir.glob("页面_*.html"))), 2)
        self.assertIn("v2", (bdir / "页面_20260731.html").read_text(encoding="utf-8"))
        _sh.rmtree(tmp2, ignore_errors=True)

    def test_is_month_end(self):
        self.assertTrue(archive.is_month_end(datetime.date(2026, 2, 28)))
        self.assertFalse(archive.is_month_end(datetime.date(2026, 7, 15)))

    def test_snapshot_skips_non_month_end(self):
        res = archive.snapshot_if_month_end(self.cfg, datetime.date(2026, 7, 15), self.root)
        self.assertEqual(res["status"], "skip")


class TestExpiredBatch(unittest.TestCase):
    """过期疑似批量处理（2026-07-11）：一键听源头新值（批量撤销）+ 逐条「坚持我的数」（rearm）。
    设计不对称：批量只给"听源头"方向；坚持只能逐条（批量坚持会废掉报警机制）。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        conn = db.connect(cls.cfg, cls.root)
        conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
            " VALUES('E1','SO9','客B','传统营销','2026-07-01',200000,50000,'2026-07','2026-07-01','2026-07',0)"
        )
        conn.commit()
        conn.close()
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "<html>ADMIN</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def _conn(self):
        return db.connect(self.cfg, self.root)

    def _add_adj(self, conn, 状态, 类型="改值", 定位键="E1", 字段="交付额", 原值="1888", 新值="2333"):
        cur = conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
            " VALUES('2026-07-11 09:00:00','明昊','std_收入明细',?,?,?,?,'测试',?,?)",
            (定位键, 字段, 原值, 新值, 类型, 状态),
        )
        conn.commit()
        return cur.lastrowid

    def test_endpoints_require_login(self):
        for method, path in [("post", "/api/adjust/expired/revoke_all"), ("post", "/api/adjust/1/rearm")]:
            r = getattr(self.anon, method)(path)
            self.assertEqual(r.status_code, 401, f"{method} {path} 未登录应 401")

    def test_revoke_all_only_touches_expired(self):
        conn = self._conn()
        a1 = self._add_adj(conn, "过期疑似")
        a2 = self._add_adj(conn, "过期疑似")
        a3 = self._add_adj(conn, "生效")
        conn.close()
        r = self.client.post("/api/adjust/expired/revoke_all", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["revoked"], 2)
        conn = self._conn()
        states = dict(conn.execute("SELECT id,状态 FROM adj_调整记录 WHERE id IN (?,?,?)", (a1, a2, a3)).fetchall())
        conn.close()
        self.assertEqual(states[a1], "已撤销")
        self.assertEqual(states[a2], "已撤销")
        self.assertEqual(states[a3], "生效")  # 生效的绝不能被批量误伤
        # 再点一次：无过期疑似 → revoked=0 幂等
        r2 = self.client.post("/api/adjust/expired/revoke_all", headers=self.hdr)
        self.assertEqual(r2.json()["revoked"], 0)

    def test_rearm_refreshes_origin_and_reapplies(self):
        conn = self._conn()
        aid = self._add_adj(conn, "过期疑似", 原值="1888", 新值="2333")  # 原值1888已过期（源头现值2000元=200000分）
        conn.close()
        r = self.client.post(f"/api/adjust/{aid}/rearm", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        conn = self._conn()
        原值, 状态 = conn.execute("SELECT 原值,状态 FROM adj_调整记录 WHERE id=?", (aid,)).fetchone()
        self.assertEqual(状态, "生效")
        self.assertEqual(str(原值), "200000")  # 原值刷成源头现值（分）
        from ingest import adjust as adj_mod

        rep = adj_mod.apply_adjustments(conn, "2026-07-11 10:00:00")
        self.assertEqual(rep["expired"], 0)
        val = conn.execute("SELECT 交付额 FROM std_收入明细 WHERE 定位键='E1'").fetchone()[0]
        conn.execute("UPDATE adj_调整记录 SET 状态='已撤销' WHERE id=?", (aid,))  # 清场防影响他例
        conn.execute("UPDATE std_收入明细 SET 交付额=200000 WHERE 定位键='E1'")  # 恢复 2000 元
        conn.commit()
        conn.close()
        self.assertEqual(int(val), 233300)  # 2333 元 = 233300 分

    def test_rearm_rejects_wrong_states(self):
        conn = self._conn()
        active = self._add_adj(conn, "生效")
        removed = self._add_adj(conn, "过期疑似", 类型="剔除", 字段="", 新值="")
        ghost = self._add_adj(conn, "过期疑似", 定位键="不存在的键")
        conn.close()
        for aid, why in [
            (active, "生效不可坚持"),
            (removed, "剔除类不可坚持"),
            (ghost, "源头行不存在不可坚持"),
            (999999, "id不存在"),
        ]:
            r = self.client.post(f"/api/adjust/{aid}/rearm", headers=self.hdr)
            self.assertEqual(r.status_code, 400, why)
        conn = self._conn()
        conn.execute("UPDATE adj_调整记录 SET 状态='已撤销' WHERE id IN (?,?,?)", (active, removed, ghost))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
