#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代 16 测试：销售归属自助（A1）+ 未归属显式提示（A3）+ 配置变更留痕（C3）。
跑：.venv/bin/python tests/test_iter16.py

守卫点（收口清单要求，全用合成名——铁律5）：
- A1 销售名扫描与规范化一致性：库四源列出的名 == 直接喂 filter_rows_by_sales 能过滤到（同一把尺）
- A1 sales_pool：当年下单笔数/金额参考串 + 未归属计数/金额；未归属分组正确
- A3 未归属：meta 仍挂人数+每周期金额（管理端/体检用）；看端整体页/BU 页均不展示文案
- A3 体检：未归属人数>0 → /api/health 判黄 + 顶栏短原因
- C3 留痕：销售归属/BU/账号/设置/密码逐类写入；不含密码明文；操作记录接口鉴权
"""

import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bu
import core
import db
import loaders
import profit
import server  # noqa: E402

TODAY = datetime.date(2026, 7, 11)


def _seed(cfg, root):
    """四源合成数据。下单：A=100万(03)、B=200万(03)、C=40万(04)、销售空=10万(05)。金额元→分。"""
    import money

    conn = db.connect(cfg, root)
    proj = [
        ("P1", "SO1", "客户甲", "线1", "销售A", "2026-03-10", 1060000.0, 300000.0),
        ("P2", "SO2", "客户乙", "线1", "销售B", "2026-03-20", 2120000.0, 500000.0),
        ("P3", "SO3", "客户丙", "线2", "销售C", "2026-04-05", 530000.0, 100000.0),
    ]
    for k, so, cu, ln, sal, d, rev, cost in proj:
        conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
            (k, so, cu, ln, sal, d, money.yuan_to_fen(rev), money.yuan_to_fen(cost), d[:7], d, d[:7]),
        )
    orders = [
        ("O1", "SO1", "2026-03-01", 1000000.0, "部门X", "销售A"),
        ("O2", "SO2", "2026-03-02", 2000000.0, "部门Y", "销售B"),
        ("O3", "SO3", "2026-04-03", 400000.0, "部门X", "销售C"),
        ("O4", "SO4", "2026-05-08", 100000.0, "部门X", ""),
    ]  # 销售空=未填=进不了任何 BU
    for k, so, d, a, dep, sal in orders:
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,0)",
            (k, so, d, money.yuan_to_fen(a), dep, sal, d[:7], d[:7]),
        )
    receipts = [
        ("R1", "HK1", "2026-03-15", 800000.0, "客户甲", "销售A"),
        ("R2", "HK2", "2026-03-25", 900000.0, "客户乙", "销售B"),
    ]
    for k, rid, d, a, cu, sal in receipts:
        conn.execute(
            "INSERT INTO std_回款(定位键,回款ID,到账日期,到账金额,客户,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,0)",
            (k, rid, d, money.yuan_to_fen(a), cu, sal, d[:7], d[:7]),
        )
    inhouse = [("T1", "2026-03-12", 50000.0, "IN-HOUSE", "销售A")]
    for k, d, a, t, sal in inhouse:
        conn.execute(
            "INSERT INTO std_内部译员(定位键,任务ID,任务提交日期,结算金额,译员类型,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,0)",
            (k, k, d, money.yuan_to_fen(a), t, sal, d[:7], d[:7]),
        )
    conn.commit()
    conn.close()


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class _Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _seed(self.cfg, self.root)

    def _summary(self):
        conn = db.connect(self.cfg, self.root)
        try:
            s = core.summary_from_conn(self.cfg, conn, TODAY)
            core.attach_unassigned(self.cfg, conn, TODAY, s, self.root)
            return s
        finally:
            conn.close()


# ---------------- A1：销售名扫描与规范化一致性 ----------------
class TestSalesScanConsistency(_Base):
    def test_pool_names_match_filter(self):
        """界面列出=过滤生效：list_salespeople 列出的每个名，直接当 BU 名单喂 filter_rows_by_sales
        必须能过滤到它的行（同一把 .strip() 尺子，绝不出现"界面显示已归属但过滤没生效")。"""
        conn = db.connect(self.cfg, self.root)
        try:
            names = [x["name"] for x in db.list_salespeople(conn)]
            orders = db.load_orders(self.cfg, conn)
        finally:
            conn.close()
        self.assertEqual(set(names), {"销售A", "销售B", "销售C"})  # 销售空不入池
        for n in names:
            got = profit.filter_rows_by_sales(orders, {n})
            self.assertTrue(got, f"池里列出 {n} 却过滤不到——两套规范化不一致")
            self.assertTrue(all(str(r.get("销售")).strip() == n for r in got))

    def test_order_stats_by_sales(self):
        conn = db.connect(self.cfg, self.root)
        try:
            st = db.order_stats_by_sales(conn, 2026)
        finally:
            conn.close()
        self.assertEqual(st["销售A"], {"count": 1, "amount": 100000000})  # 100万=1e8 分
        self.assertEqual(st["销售B"]["amount"], 200000000)
        self.assertNotIn("", st)  # 空销售不计


# ---------------- A1：sales_pool 接口（参考串 + 未归属快照） ----------------
class TestSalesPoolEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.root = Path(tempfile.mkdtemp())
        cls.cfg = loaders.load_config()
        _seed(cls.cfg, cls.root)
        _write_bucfg(cls.cfg, cls.root, [{"name": "BU甲", "负责人": ["负责人甲"], "销售": ["销售A"]}])
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    def test_requires_login(self):
        self.assertEqual(self.anon.get("/api/sales_pool").status_code, 401)

    def test_ref_disp_and_unassigned(self):
        d = self.client.get("/api/sales_pool", headers=self.hdr).json()
        by = {x["name"]: x for x in d["sales"]}
        self.assertIn("1 笔", by["销售A"]["ref_disp"])  # 参考=当年下单笔数
        self.assertIn("100.0万", by["销售A"]["ref_disp"])  # 100 万
        # 未归属：B、C 两人（A 已归 BU甲），当年未归属下单额=200+40+10（空）=250 万
        self.assertEqual(d["unassigned_count"], 2)
        self.assertIn("250.0万", d["unassigned_orders_disp"])


# ---------------- A3：未归属提示（人数/金额随周期、N=0 不渲染、BU 页无泄漏） ----------------
class TestUnassignedHint(_Base):
    def test_attach_counts_and_amounts(self):
        _write_bucfg(self.cfg, self.root, [{"name": "BU甲", "销售": ["销售A"]}])
        un = self._summary()["meta"]["unassigned"]
        self.assertEqual(un["count"], 2)  # B、C
        self.assertIn("250.0万", un["by_period"]["2026年"])  # 全年未归属下单=B200+C40+空10=250万
        self.assertIn("200.0万", un["by_period"]["2026年3月"])  # 3月未归属=销售B 200万（A已归、C在4月、空在5月）
        self.assertIn("40.0万", un["by_period"]["2026年4月"])  # 4月未归属=销售C 40万

    def test_n_zero_no_render(self):
        """全部有名销售归属 → N=0，整体页不渲染提示行（空销售残差不触发提示）。"""
        _write_bucfg(self.cfg, self.root, [{"name": "BU甲", "销售": ["销售A", "销售B", "销售C"]}])
        un = self._summary()["meta"]["unassigned"]
        self.assertEqual(un["count"], 0)

    def test_no_bu_config_no_nag(self):
        """未配任何 BU（分页关闭）→ count=0 不判黄、整体页无入口条也无提示（体检不被无意义拉黄）。"""
        un = self._summary()["meta"]["unassigned"]  # 无 BU配置.json
        self.assertEqual(un["count"], 0)
        self.assertEqual(un["by_period"], {})

    def test_main_page_has_hint_bu_page_never(self):
        from fastapi.testclient import TestClient

        _write_bucfg(self.cfg, self.root, [{"name": "BU甲", "负责人": ["负责人甲"], "销售": ["销售A"]}])
        conn = db.connect(self.cfg, self.root)
        s = core.summary_from_conn(self.cfg, conn, TODAY)
        core.attach_unassigned(self.cfg, conn, TODAY, s, self.root)
        server._state["summary"] = s
        server._state["user_html"] = '<html><div class="wrap">MAIN</div></html>'
        import render as _render

        server._state["fragments"] = _render.build_dashboard_fragments(s, self.cfg, "")
        server._state["bu_pages"] = core.build_bu_pages(self.cfg, conn, TODAY, "", self.root)
        conn.close()
        app = server.create_app(self.cfg, root=self.root)
        client = TestClient(app, follow_redirects=False)
        r = client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}
        main = client.get("/", headers=hdr).text
        # shell 不含业务文案；看 chrome/fragments
        self.assertIn("经营看板", main)
        fr = client.get("/api/v1/cockpit/fragments", headers=hdr).json()
        chrome = fr.get("chrome_prefix") or ""
        body = fr["fragments"].get("kpi_views") or ""
        # 看端整体页：不展示未归属提示（只留 BU 分页入口；配置仍走管理端）
        self.assertNotIn("未归属 BU 的业务", chrome + body)
        self.assertNotIn("名销售待配置归属", chrome + body)
        self.assertNotIn("bu-unassigned", chrome + body)
        self.assertIn("业务 BU 分页", chrome)
        # BU 页同样无未归属文案，也不泄漏其他 BU/未归属人名
        from urllib.parse import quote

        bupage = client.get(f"/bu/{quote('BU甲')}", headers=hdr).text
        self.assertIn("经营看板", bupage)
        bfr = client.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments", headers=hdr).json()
        bhtml = (bfr.get("chrome_prefix") or "") + str(bfr.get("fragments") or {})
        self.assertNotIn("未归属 BU 的业务", bhtml)
        self.assertNotIn("名销售待配置归属", bhtml)
        self.assertNotIn("销售B", bhtml)
        self.assertNotIn("销售C", bhtml)

    def test_health_yellow_with_reason(self):
        from fastapi.testclient import TestClient

        _write_bucfg(self.cfg, self.root, [{"name": "BU甲", "销售": ["销售A"]}])
        conn = db.connect(self.cfg, self.root)
        s = core.summary_from_conn(self.cfg, conn, TODAY)
        core.attach_unassigned(self.cfg, conn, TODAY, s, self.root)
        conn.close()
        server._state["summary"] = s
        app = server.create_app(self.cfg, root=self.root)
        client = TestClient(app, follow_redirects=False)
        h = client.get("/api/health").json()
        self.assertEqual(h["result"], "黄")
        self.assertTrue(any("销售未归属 BU" in r for r in h["run_reasons"]))


# ---------------- C3：配置变更留痕 ----------------
class TestAuditTrail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil
        from fastapi.testclient import TestClient

        cls.root = Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "config.json", cls.root / "config.json")  # /api/settings 写 root/config.json
        cls.cfg = loaders.load_config()
        _seed(cls.cfg, cls.root)
        _write_bucfg(cls.cfg, cls.root, [{"name": "BU甲", "负责人": ["负责人甲"], "销售": ["销售A"]}])
        conn = db.connect(cls.cfg, cls.root)
        server._state["user_html"] = '<html><div class="wrap">M</div></html>'
        server._state["bu_pages"] = core.build_bu_pages(cls.cfg, conn, TODAY, "", cls.root)
        conn.close()
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    def _changes(self, category=None):
        u = "/api/config_changes" + (f"?category={category}" if category else "")
        return self.client.get(u, headers=self.hdr).json()["changes"]

    def test_endpoint_auth(self):
        self.assertEqual(self.anon.get("/api/config_changes").status_code, 401)
        self.assertEqual(self.client.get("/api/config_changes", headers=self.hdr).status_code, 200)

    def test_bu_config_change_logged(self):
        """销售归属改动 → 「销售归属」类记录；新增 BU → 「BU配置」类记录。"""
        from unittest.mock import patch

        with patch.object(server, "recompute"):
            self.client.post(
                "/api/bu_config",
                headers=self.hdr,
                json={
                    "bus": [
                        {"name": "BU甲", "负责人": "负责人甲", "销售": "销售A、销售B"},  # 加销售B
                        {"name": "BU乙", "负责人": "负责人乙", "销售": "销售C"},
                    ]
                },
            )  # 新增 BU乙
        sales = self._changes("销售归属")
        buc = self._changes("BU配置")
        self.assertTrue(any("销售B" in c["摘要"] and "未归属→BU甲" in c["摘要"] for c in sales))
        self.assertTrue(any("新增 BU BU乙" in c["摘要"] for c in buc))

    def test_accounts_change_logged_no_plaintext(self):
        """账号改密码 → 只记「改密码」，绝不含密码明文。"""
        from unittest.mock import patch
        import accounts

        accs = accounts.load_accounts(self.cfg, self.root)
        for a in accs:
            if a["权限"] == accounts.PERM_MAIN:
                a["密码"] = "TOPSECRET_9182"
        with patch.object(server, "recompute"):
            self.client.post("/api/accounts", headers=self.hdr, json={"accounts": accs})
        recs = self._changes("账号")
        self.assertTrue(recs, "账号改动应留痕")
        self.assertTrue(any("改密码" in c["摘要"] for c in recs))
        # 全表任何摘要都不得出现密码明文
        all_summaries = " ".join(c["摘要"] for c in self._changes())
        self.assertNotIn("TOPSECRET_9182", all_summaries)

    def test_my_passwd_logged_no_plaintext(self):
        """看的人自改密码 → 「密码」类记录，不含明文。自带独立环境（不受别的用例改密码影响）。"""
        from fastapi.testclient import TestClient

        root = Path(tempfile.mkdtemp())
        cfg = loaders.load_config()
        _seed(cfg, root)
        app = server.create_app(cfg, root=root)
        vc = TestClient(app, follow_redirects=False)  # 自带 cookie 罐，登录后自动带 VCOOKIE
        r = vc.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r.status_code, 303)
        rr = vc.post("/api/my_passwd", json={"old": server.DEFAULT_VIEW_PW, "new": "NEWPW_5566"})
        self.assertEqual(rr.status_code, 200)
        ac = TestClient(app, follow_redirects=False)
        ar = ac.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        hdr = {"Cookie": f"{server.COOKIE}={ar.cookies.get(server.COOKIE)}"}
        allc = ac.get("/api/config_changes", headers=hdr).json()["changes"]
        pwc = [c for c in allc if c["类别"] == "密码"]
        self.assertTrue(any("overall" in c["摘要"] and "改密码" in c["摘要"] for c in pwc))
        self.assertNotIn("NEWPW_5566", " ".join(c["摘要"] for c in allc))

    def test_settings_change_logged(self):
        from unittest.mock import patch

        with patch.object(server, "recompute"):
            self.client.post("/api/settings", headers=self.hdr, json={"backup_keep_days": 99})
        recs = self._changes("设置")
        self.assertTrue(any("备份保留" in c["摘要"] and "99" in c["摘要"] for c in recs))


if __name__ == "__main__":
    unittest.main(verbosity=1)
