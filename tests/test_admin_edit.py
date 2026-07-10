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

import loaders, server, db  # noqa: E402
from ingest import archive  # noqa: E402


def _seed(cfg, root):
    """在 endpoints 用的同一个库里种一行收入明细 + 一行费用明细（R1 新开放字段用）。"""
    conn = db.connect(cfg, root)
    conn.execute(
        "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
        " VALUES('K1','SO1','客A','传统营销','2026-07-15',1000,300,'2026-07','2026-07-15','2026-07',0)")
    conn.execute(
        "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
        " VALUES('L1','2026-06','2026-06-15',100,'语言','管理费用','办公费','市场部','2026-06','2026-06',0)")
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
        cls.anon = TestClient(cls.app, follow_redirects=False)   # 从不登录（TestClient 会存 cookie，需独立客户端测未授权）
        # 登录拿会话
        r = cls.client.post("/admin/login", data={"identity": "明昊", "password": server.DEFAULT_PW})
        cls.cookie = r.cookies.get(server.COOKIE)
        cls.hdr = {"Cookie": f"{server.COOKIE}={cls.cookie}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def _conn(self):
        return db.connect(self.cfg, self.root)

    # ---- 鉴权：写接口一律要会话 ----
    def test_write_requires_login(self):
        for method, path in [("post", "/api/adjust"), ("post", "/api/manual"),
                             ("post", "/api/refresh"), ("get", "/api/adjust_fields"),
                             ("get", "/api/adjustments"), ("post", "/api/adjust/1/revoke")]:
            r = getattr(self.anon, method)(path)   # 未登录：_require 在函数体首行先拦，body 走默认
            self.assertEqual(r.status_code, 401, f"{method} {path} 未登录应 401")

    # ---- 明细编辑：写调整 + 触发重算 + 台账+1，原值由服务端从库取 ----
    def test_adjust_records_and_recomputes(self):
        server._state["built_at"] = "OLD"
        r = self.client.post("/api/adjust", headers=self.hdr, json={
            "目标表": "std_收入明细", "定位键": "K1", "字段": "交付额",
            "新值": 2000, "原因": "测试改值", "类型": "改值"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("adj_id", r.json())
        self.assertEqual(server._state["built_at"], "RECOMPUTED")   # 触发了秒级重算
        # 台账里能查到，且原值=服务端从库读的 1000.0（不是前端传的）
        adjs = self.client.get("/api/adjustments", headers=self.hdr).json()
        mine = [a for a in adjs if a["字段"] == "交付额" and a["定位键"] == "K1"]
        self.assertTrue(mine)
        self.assertEqual(str(mine[0]["原值"]), "1000.0")
        self.assertEqual(mine[0]["新值"], "2000")
        self.assertEqual(mine[0]["类型"], "改值")

    def test_adjust_bad_field_400(self):
        r = self.client.post("/api/adjust", headers=self.hdr, json={
            "目标表": "std_收入明细", "定位键": "K1", "字段": "不存在的字段",
            "新值": "x", "类型": "改值"})
        self.assertEqual(r.status_code, 400)

    def test_adjust_bad_table_400(self):
        r = self.client.post("/api/adjust", headers=self.hdr, json={
            "目标表": "std_不存在", "定位键": "K1", "字段": "交付额", "新值": 1, "类型": "改值"})
        self.assertEqual(r.status_code, 400)

    def test_remove_soft_delete_records(self):
        r = self.client.post("/api/adjust", headers=self.hdr, json={
            "目标表": "std_收入明细", "定位键": "K1", "字段": "", "新值": "", "原因": "剔除", "类型": "剔除"})
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
        r = self.client.post("/api/manual", headers=self.hdr,
                             json={"归属月": "2026-07", "项目": "营销人力成本", "金额": 5000})
        self.assertEqual(r.status_code, 200, r.text)
        # 再写一次覆盖
        r2 = self.client.post("/api/manual", headers=self.hdr,
                              json={"归属月": "2026-07", "项目": "营销人力成本", "金额": 6000})
        self.assertEqual(r2.status_code, 200)
        conn = self._conn()
        cur = conn.execute("SELECT 金额 FROM manual_手填 WHERE 归属月='2026-07' AND 项目='营销人力成本'").fetchone()
        hist = conn.execute("SELECT COUNT(*) FROM manual_历史 WHERE 项目='营销人力成本'").fetchone()[0]
        conn.close()
        self.assertEqual(cur[0], 6000.0)          # 当月覆盖
        self.assertGreaterEqual(hist, 2)          # 两次都留痕

    def test_manual_unknown_item_400(self):
        r = self.client.post("/api/manual", headers=self.hdr,
                             json={"归属月": "2026-07", "项目": "不在枚举里", "金额": 1})
        self.assertEqual(r.status_code, 400)

    def test_manual_non_number_400(self):
        r = self.client.post("/api/manual", headers=self.hdr,
                             json={"归属月": "2026-07", "项目": "营销人力成本", "金额": "abc"})
        self.assertEqual(r.status_code, 400)

    # ---- R1：字段下拉从服务端下发（全部可调列），新开放字段可写、黑名单字段 400 ----
    def test_adjust_fields_served_full_lists(self):
        r = self.client.get("/api/adjust_fields", headers=self.hdr)
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual(set(j), {"收入明细", "下单", "回款", "内部译员", "费用明细"})
        self.assertIn("预算归属部门", j["费用明细"])       # 新开放字段进了下拉
        self.assertIn("客户", j["收入明细"])
        for fields in j.values():                          # 黑名单字段不下发
            for banned in ("id", "定位键", "归属月", "已删除"):
                self.assertNotIn(banned, fields)

    def test_adjust_new_open_field_ok(self):
        r = self.client.post("/api/adjust", headers=self.hdr, json={
            "目标表": "std_费用明细", "定位键": "L1", "字段": "预算归属部门",
            "新值": "数据部", "原因": "测试R1", "类型": "改值"})
        self.assertEqual(r.status_code, 200, r.text)

    def test_adjust_blacklist_field_400(self):
        for banned in ("定位键", "归属月", "原值_归属月", "已删除"):
            r = self.client.post("/api/adjust", headers=self.hdr, json={
                "目标表": "std_费用明细", "定位键": "L1", "字段": banned,
                "新值": "x", "类型": "改值"})
            self.assertEqual(r.status_code, 400, f"{banned} 应 400")

    # ---- 立即更新：运行中互斥 → 409 ----
    def test_refresh_mutex_returns_409(self):
        self.assertTrue(server._LOCK.acquire(blocking=False))
        try:
            r = self.client.post("/api/refresh", headers=self.hdr, json={})
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.json().get("status"), "running")
        finally:
            server._LOCK.release()

    # ---- 立即更新：后台跑+状态轮询（_do_full 打桩，不跑真管道） ----
    def test_refresh_async_and_status(self):
        import time as _t
        orig = server._do_full
        server._do_full = lambda cfg, root, trigger: {"result": "绿"}
        try:
            r = self.client.post("/api/refresh", headers=self.hdr, json={})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json().get("status"), "started")
            for _ in range(50):                     # 最多等 5s，后台线程应瞬间跑完
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
        import json as _json, shutil as _sh
        _sh.copy2(ROOT / "config.json", self.root / "config.json")
        r = self.client.get("/api/settings", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        self.assertIn("schedule_time", r.json())
        # 非法值 → 400
        for bad in ({"schedule_time": "25:00"}, {"schedule_time": "9点半"},
                    {"backup_keep_days": 0}, {"backup_keep_days": "abc"}):
            r = self.client.post("/api/settings", headers=self.hdr, json=bad)
            self.assertEqual(r.status_code, 400, f"{bad} 应 400")
        # 合法保存 → cfg 即时生效 + 文件落盘
        r = self.client.post("/api/settings", headers=self.hdr, json={
            "schedule_time": "08:45", "backup_keep_days": 7, "zhiyun_auto_fetch": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.cfg["schedule_time"], "08:45")
        self.assertEqual(self.cfg["backup_keep_days"], 7)
        raw = _json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["schedule_time"], "08:45")
        self.assertEqual(raw["backup_keep_days"], 7)

    def test_settings_zhiyun_creds(self):
        """智云账号：GET 可见 / 改了才写+清旧会话 / 空值 400 / 同值不动。"""
        import json as _json, shutil as _sh
        _sh.copy2(ROOT / "config.json", self.root / "config.json")
        zp = loaders.data_dir(self.cfg, self.root) / "智云配置.json"
        zp.parent.mkdir(parents=True, exist_ok=True)
        zp.write_text(_json.dumps({"username": "old.user", "password": "oldpw",
                                   "md_pss_id": "OLDTOKEN", "account_id": "OLDACC",
                                   "base_url": "http://x"}), encoding="utf-8")
        r = self.client.get("/api/settings", headers=self.hdr)
        self.assertEqual(r.json()["zhiyun_username"], "old.user")
        # 改账号 → 写入 + 清 md_pss_id/account_id（下次更新强制新账号重登、自动取新GUID）
        r = self.client.post("/api/settings", headers=self.hdr, json={
            "zhiyun_username": "new.user", "zhiyun_password": "newpw"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("智云账号已更新", r.json()["note"])
        d = _json.loads(zp.read_text(encoding="utf-8"))
        self.assertEqual((d["username"], d["password"]), ("new.user", "newpw"))
        self.assertEqual((d["md_pss_id"], d["account_id"]), ("", ""))
        self.assertEqual(d["base_url"], "http://x")        # 其余键保留
        # 同值再存 → 不算变更（不清会话）
        r = self.client.post("/api/settings", headers=self.hdr, json={
            "zhiyun_username": "new.user", "zhiyun_password": "newpw"})
        self.assertNotIn("智云账号已更新", r.json()["note"])
        # 空密码 → 400
        r = self.client.post("/api/settings", headers=self.hdr, json={
            "zhiyun_username": "new.user", "zhiyun_password": ""})
        self.assertEqual(r.status_code, 400)

    def test_settings_requires_login(self):
        self.assertEqual(self.anon.get("/api/settings").status_code, 401)
        self.assertEqual(self.anon.post("/api/settings", json={}).status_code, 401)
        self.assertEqual(self.anon.get("/api/refresh_status").status_code, 401)


class TestArchive(unittest.TestCase):
    """归档：db 每日滚动备份保留 N 份 + 月末快照判定。"""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.cfg = loaders.load_config()
        db.connect(self.cfg, self.root).close()   # 建出 看板.db

    def test_backup_db_rolling_keep(self):
        d0 = datetime.date(2026, 7, 1)
        for i in range(4):
            res = archive.backup_db(self.cfg, d0 + datetime.timedelta(days=i), self.root, keep=2)
            self.assertEqual(res["status"], "ok", res)
        bdir = loaders.data_dir(self.cfg, self.root) / "备份"
        kept = sorted(bdir.glob("看板_*.db"))
        self.assertEqual(len(kept), 2)            # 滚动只留最近 2 份
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

    def test_is_month_end(self):
        self.assertTrue(archive.is_month_end(datetime.date(2026, 2, 28)))
        self.assertFalse(archive.is_month_end(datetime.date(2026, 7, 15)))

    def test_snapshot_skips_non_month_end(self):
        res = archive.snapshot_if_month_end(self.cfg, datetime.date(2026, 7, 15), self.root)
        self.assertEqual(res["status"], "skip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
