#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书52：F-1 CSS 源码守卫 + F-3 logout 会话作废 + F-4 面积轴/裁月 + F-5 密码出库 + F-6 ledger/SHA。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import render  # noqa: E402
import server  # noqa: E402
import viewmodels  # noqa: E402

FAKE = ROOT / "_golden_data"
THEME = ROOT / "static" / "css" / "theme.css"


class TestF1ModalCss(unittest.TestCase):
    def test_theme_has_rkm_mask_fixed(self):
        css = THEME.read_text(encoding="utf-8")
        self.assertIn(".rkm-mask", css)
        # 同一规则块含 fixed + inset + flex 居中
        m = re.search(r"\.rkm-mask\s*\{([^}]+)\}", css, re.S)
        self.assertTrue(m, ".rkm-mask rule missing")
        block = m.group(1)
        self.assertIn("position:fixed", block.replace(" ", ""))
        self.assertIn("inset:0", block.replace(" ", ""))
        self.assertIn("display:flex", block.replace(" ", ""))
        self.assertIn("align-items:center", block.replace(" ", ""))

    def test_vue_teleport_body(self):
        for name in ("RankingsDual.vue", "ProfitStructure.vue"):
            src = (ROOT / "frontend" / "src" / "components" / name).read_text(encoding="utf-8")
            self.assertIn('Teleport to="body"', src)
            self.assertIn("rkm-mask", src)

    def test_pl_table_grid_not_14px_name(self):
        """Vue .pl-table 行不得用 14px 色点列当名列（否则 pl-name≈14px 竖排）。"""
        css = THEME.read_text(encoding="utf-8")
        self.assertIn(".pl-table .pl-row", css)
        self.assertIn("minmax(140px,1fr)", css.replace(" ", ""))


class TestF3LogoutInvalidates(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = loaders.load_config(ROOT)
        self.cfg = dict(cfg)
        self.cfg["data_dir"] = str(self.tmp / "数据")
        (self.tmp / "数据").mkdir(parents=True)
        accounts.seed_defaults(self.cfg, self.tmp)
        conn = db.connect(self.cfg, self.tmp)
        conn.close()
        self.app = server.create_app(self.cfg, self.tmp)
        from fastapi.testclient import TestClient

        self.client = TestClient(self.app)

    def test_view_logout_old_cookie_401(self):
        r = self.client.post(
            "/api/v1/login",
            json={"account": "overall", "password": accounts.DEFAULT_VIEW_PW},
        )
        self.assertEqual(r.status_code, 200, r.text[:200])
        # 保 cookie
        jar = dict(self.client.cookies)
        self.assertTrue(jar, "login 应下发 cookie")
        r2 = self.client.get("/api/v1/session")
        self.assertEqual(r2.status_code, 200, f"登录后 session 应 200，得 {r2.status_code} {r2.text[:120]}")
        r3 = self.client.post("/api/v1/logout")
        self.assertEqual(r3.status_code, 200)
        # 重放 logout 前 cookie（TestClient 可能已清 cookie，手动塞回）
        from starlette.testclient import TestClient as TC

        c2 = TC(self.app)
        for k, v in jar.items():
            c2.cookies.set(k, v)
        r4 = c2.get("/api/v1/session")
        self.assertEqual(r4.status_code, 401, f"旧 cookie 重放应 401，得 {r4.status_code} {r4.text[:120]}")

    def test_admin_logout_old_cookie_401(self):
        r = self.client.post(
            "/api/v1/login",
            json={"account": accounts.MASTER_ACCOUNT, "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertEqual(r.status_code, 200)
        jar = dict(self.client.cookies)
        r2 = self.client.get("/api/v1/session")
        self.assertEqual(r2.status_code, 200, f"管理员 session 应 200，得 {r2.status_code}")
        # 管理端 GET logout
        r3 = self.client.get("/admin/logout", follow_redirects=False)
        self.assertIn(r3.status_code, (302, 303, 200))
        from starlette.testclient import TestClient as TC

        c2 = TC(self.app)
        for k, v in jar.items():
            c2.cookies.set(k, v)
        r4 = c2.get("/api/v1/session")
        self.assertEqual(r4.status_code, 401, f"管理端退出后旧 cookie 应 401，得 {r4.status_code}")


class TestF4AreaAxisTrim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            cls.summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        cls.cfg = cfg
        os.environ["KANBAN_FRONTEND"] = "vue"
        cls.vm = viewmodels.build_cockpit_vm(cls.summary, cfg)

    def test_area_y_axis_ticks_have_wan(self):
        ticks = self.vm.expense.area_y_axis_ticks or []
        self.assertTrue(ticks, "area_y_axis_ticks 应下发")
        labs = [t.get("label") for t in ticks]
        # 至少非零刻度带「万」
        non_zero = [x for x in labs if x and x != "0"]
        self.assertTrue(non_zero, labs)
        self.assertTrue(any("万" in str(x) for x in non_zero), non_zero)
        self.assertGreaterEqual(self.vm.expense.area_y_axis_max, self.vm.expense.area_y_axis_min)

    def test_area_labels_trimmed(self):
        labs = self.vm.expense.area_labels or []
        self.assertTrue(labs)
        self.assertLessEqual(len(labs), 12)
        # 系列长度与 labels 对齐
        for s in self.vm.expense.area_series or []:
            self.assertEqual(len(s.get("data") or []), len(labs))

    def test_expense_trend_vue_uses_tick_label(self):
        src = (ROOT / "frontend" / "src" / "components" / "ExpenseTrend.vue").read_text(encoding="utf-8")
        self.assertIn("tickLabel", src)
        self.assertIn("area_y_axis_ticks", src)
        self.assertNotIn("String(v)", src)


class TestF5PasswordOutOfGit(unittest.TestCase):
    def test_docs_no_active_passwords(self):
        """docs/ 全文不得出现 数据/看板账号.json 中现役明文密码（本机有账号文件时跑）。"""
        acc_path = ROOT / "数据" / "看板账号.json"
        if not acc_path.is_file():
            self.skipTest("无本机 数据/看板账号.json（不上云，守卫仅本机）")
        data = json.loads(acc_path.read_text(encoding="utf-8"))
        rows = data.get("accounts") if isinstance(data, dict) else data
        # 只查「现役轮换账号」的非默认口令（默认 8888 会误伤样例/手册）
        watch = {"lushasha", "123", "zhengrui"}
        default_pws = {accounts.DEFAULT_VIEW_PW, accounts.DEFAULT_ADMIN_PW, "8888", "kanban2026"}
        pws = []
        for a in rows or []:
            if not isinstance(a, dict):
                continue
            if str(a.get("账号") or "") not in watch:
                continue
            pw = str(a.get("密码") or "").strip()
            if pw and pw not in default_pws and len(pw) >= 8:
                pws.append(pw)
        if not pws:
            self.skipTest("三账号仍为默认口令或未轮换——跳过 docs 交叉比对")
        docs = ROOT / "docs"
        hits = []
        for p in docs.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".md", ".txt", ".html", ".json"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pw in pws:
                if pw in text:
                    hits.append(f"{p.relative_to(ROOT)} contains active rotated password")
        self.assertEqual(hits, [], "docs 泄漏现役密码: " + "; ".join(hits[:5]))

    def test_task50_report_no_password_table(self):
        """50 交付报告不得含密码表；现役明文只许在本机账号文件。"""
        p = ROOT / "docs" / "历史批次" / "20260717_任务书50交付报告.md"
        # 产品仓瘦身（4c87bf3）已将历史批次迁出 git；无文件=产品仓无泄漏面，守卫仍扫残留副本
        if not p.is_file():
            self.skipTest("任务书50交付报告已迁出产品仓（施工归档），无本地副本")
        t = p.read_text(encoding="utf-8")
        self.assertIn("看板账号.json", t)
        # 不得再出现「账号 | 明文密码」表格头/行（任务书52·F-5 出库）
        self.assertNotRegex(t, r"\| *账号 *\| *新明文密码 *\|")
        self.assertNotIn("哈希迁移账号新明文（请明昊转告相关人）", t)
        # 动态：当前账号文件中三账号口令不得出现在本报告（账号文件缺失则跳过）
        acc_path = ROOT / "数据" / "看板账号.json"
        if not acc_path.is_file():
            return
        data = json.loads(acc_path.read_text(encoding="utf-8"))
        watch = {"lushasha", "123", "zhengrui"}
        for a in data.get("accounts") or []:
            if str(a.get("账号") or "") not in watch:
                continue
            pw = str(a.get("密码") or "").strip()
            if pw and len(pw) >= 8:
                self.assertNotIn(pw, t, "任务书50报告泄漏现役密码")


class TestF6LedgerAndPlSha(unittest.TestCase):
    def test_ledger_json_no_forbidden_meta(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = str(tmp / "数据")
        (tmp / "数据").mkdir(parents=True)
        accounts.seed_defaults(cfg, tmp)
        db.connect(cfg, tmp).close()
        app = server.create_app(cfg, tmp)
        from fastapi.testclient import TestClient

        c = TestClient(app)
        c.post(
            "/api/v1/login",
            json={"account": accounts.MASTER_ACCOUNT, "password": accounts.DEFAULT_ADMIN_PW},
        )
        r = c.get("/api/v1/vm/ledger?page=1&page_size=5")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertNotIn("forbidden", j)
        self.assertNotIn("forbidden_columns", j)

    def test_render_pl_table_sha_golden(self):
        """B2 逐字节基线：golden 数据下全年 PL HTML SHA 固化。"""
        if not FAKE.exists():
            self.skipTest("缺 _golden_data")
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            s = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        yk = s["meta"]["year_key"]
        FT = s.get("expense_fine_type") or {}
        unc = (s.get("meta") or {}).get("unclassified") or {}
        unc_amt = float((unc.get("expense") or {}).get("amount") or 0)
        html = render.render_pl_table(
            s["periods"][yk],
            FT.get(yk, {}),
            unclassified_amt=unc_amt if unc_amt else None,
        )
        full = hashlib.sha256(html.encode("utf-8")).hexdigest()
        expected_path = ROOT / "tests" / "fixtures" / "pl_table_year_sha.txt"
        self.assertTrue(expected_path.is_file(), "缺 tests/fixtures/pl_table_year_sha.txt")
        exp = expected_path.read_text(encoding="utf-8").strip()
        self.assertEqual(full, exp, "render_pl_table SHA 与固化基线不符——PL 结构漂移")


if __name__ == "__main__":
    unittest.main()
