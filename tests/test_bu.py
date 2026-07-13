#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代 14 BU 分页测试（v7.7）。跑：.venv/bin/python tests/test_bu.py

守卫点（收口清单要求，全用合成名——铁律5，真实人名绝不进 git）：
- 零配置兼容：无 BU配置.json → load 返回 None、build_bu_pages 返回 {}、/bu/* 一律 404、主页照旧
- 守恒红线：∑各 BU（收入/下单/回款）+ 未归属 == 全公司（同口径同期间）
- 账号制（v7.9）：/bu/{BU名} 未知名 404；页面严格隔离（登录鉴权详测见 test_auth.py）
- 严格保密：BU 页 HTML 不含其他 BU 的名字（BU名/负责人/销售）
- 公共费用恒 0 + 标注"暂不分摊"；手填项标注"待陆总手填"；BU 税前利润 = 毛利 − 附加税费
- 配置增改生效：改销售名单 → 数字随之变
- XSS：BU 名/销售名含 HTML 特殊字符必转义
- /api/bu_config：未登录 401；登录可读写
"""
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bu, core, db, loaders, profit, render, server  # noqa: E402

TODAY = datetime.date(2026, 7, 11)


def _seed(cfg, root):
    """四源合成数据：销售A/销售B 各归一个 BU，销售C 未归属。金额都取整好核对。"""
    conn = db.connect(cfg, root)
    proj = [  # (键, 订单号, 客户, 业务线, 销售, 交付日期, 交付额, 项目成本)
        ("P1", "SO1", "客户甲", "线1", "销售A", "2026-03-10", 1060.0, 300.0),
        ("P2", "SO2", "客户乙", "线1", "销售B", "2026-03-20", 2120.0, 500.0),
        ("P3", "SO3", "客户丙", "线2", "销售C", "2026-04-05", 530.0, 100.0),
    ]
    for k, so, cu, ln, sal, d, rev, cost in proj:
        conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)", (k, so, cu, ln, sal, d, rev, cost, d[:7], d, d[:7]))
    orders = [("O1", "SO1", "2026-03-01", 1000.0, "部门X", "销售A"),
              ("O2", "SO2", "2026-03-02", 2000.0, "部门Y", "销售B"),
              ("O3", "SO3", "2026-04-03", 400.0, "部门X", "销售C")]
    for k, so, d, a, dep, sal in orders:
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,0)", (k, so, d, a, dep, sal, d[:7], d[:7]))
    receipts = [("R1", "HK1", "2026-03-15", 800.0, "客户甲", "销售A"),
                ("R2", "HK2", "2026-03-25", 900.0, "客户乙", "销售B"),
                ("R3", "HK3", "2026-05-02", 100.0, "客户丙", "")]  # 销售空=未归属
    for k, rid, d, a, cu, sal in receipts:
        conn.execute(
            "INSERT INTO std_回款(定位键,回款ID,到账日期,到账金额,客户,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,0)", (k, rid, d, a, cu, sal, d[:7], d[:7]))
    inhouse = [("T1", "2026-03-12", 50.0, "IN-HOUSE", "销售A"),
               ("T2", "2026-03-18", 70.0, "IN-HOUSE", "销售B")]
    for k, d, a, t, sal in inhouse:
        conn.execute(
            "INSERT INTO std_内部译员(定位键,任务ID,任务提交日期,结算金额,译员类型,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,0)", (k, k, d, a, t, sal, d[:7], d[:7]))
    conn.commit()
    conn.close()


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


def _two_bus():
    return [
        {"name": "BU甲", "负责人": ["负责人甲"], "销售": ["销售A"], "分摊比例": None},
        {"name": "BU乙", "负责人": ["负责人乙"], "销售": ["销售B"], "分摊比例": None},
    ]


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.cfg = loaders.load_config()
        _seed(self.cfg, self.root)

    def _rows(self):
        conn = db.connect(self.cfg, self.root)
        try:
            return (db.load_project_detail(self.cfg, conn), db.load_orders(self.cfg, conn),
                    db.load_receipts(self.cfg, conn), db.load_inhouse(self.cfg, conn))
        finally:
            conn.close()

    def _pages(self):
        conn = db.connect(self.cfg, self.root)
        try:
            return core.build_bu_pages(self.cfg, conn, TODAY, "", self.root)
        finally:
            conn.close()


class TestBuConfig(_Base):
    def test_zero_config(self):
        """零配置兼容：无配置文件 → None / {}；主流程不受影响。"""
        self.assertIsNone(bu.load_bu_config(self.cfg, self.root))
        self.assertEqual(self._pages(), {})

    def test_invalid_entries_skipped(self):
        _write_bucfg(self.cfg, self.root, [
            {"name": "", "销售": ["销售A"]},            # 无名 → 跳过
            {"name": "整体", "销售": ["销售A"]},        # 与整体账号撞名 → 跳过
            {"name": "BU甲", "销售": ["销售A"]},
            {"name": "BU甲", "销售": ["销售B"]},        # 同名（账号必须唯一）→ 跳过后者
        ])
        cfgd = bu.load_bu_config(self.cfg, self.root)
        self.assertEqual([b["name"] for b in cfgd["bus"]], ["BU甲"])
        self.assertEqual(cfgd["bus"][0]["销售"], ["销售A"])

    def test_clean_names_accepts_string(self):
        _write_bucfg(self.cfg, self.root, [
            {"name": "BU甲", "销售": "销售A、销售B，销售C"}])
        cfgd = bu.load_bu_config(self.cfg, self.root)
        self.assertEqual(cfgd["bus"][0]["销售"], ["销售A", "销售B", "销售C"])

    def test_save_normalizes_ratio_and_drops_password(self):
        """保存：规范化落盘；比例全空=不分摊；有齐填且 100%=启用；密码字段废弃。"""
        _write_bucfg(self.cfg, self.root, _two_bus())
        # 全空 → 不分摊
        empty = bu.save_bu_config(self.cfg, self.root, [
            {"name": "BU甲", "销售": ["销售A"], "分摊比例": None, "密码hash": "自造hash"},
            {"name": "BU丙", "销售": ["销售C"]},
        ], 公共费用分摊启用=True)  # 开关被忽略，全空仍关
        self.assertFalse(empty["公共费用分摊启用"])
        self.assertIsNone(empty["bus"][0]["分摊比例"])
        self.assertNotIn("密码hash", empty["bus"][0])
        # 齐填 100% → 自动启用
        saved = bu.save_bu_config(self.cfg, self.root, [
            {"name": "BU甲", "销售": ["销售A"], "分摊比例": 40},
            {"name": "BU丙", "销售": ["销售C"], "分摊比例": 60},
        ], 公共费用分摊启用=False)
        by = {b["name"]: b for b in saved["bus"]}
        self.assertEqual(by["BU甲"]["分摊比例"], 40.0)
        self.assertEqual(by["BU丙"]["分摊比例"], 60.0)
        self.assertTrue(saved["公共费用分摊启用"])

    def test_alloc_enabled_requires_sum_100(self):
        """有填比例时合计须≈100%；只填部分 → 拒绝。"""
        with self.assertRaises(ValueError) as cm:
            bu.save_bu_config(self.cfg, self.root, [
                {"name": "BU甲", "销售": ["销售A"], "分摊比例": 30},
                {"name": "BU乙", "销售": ["销售B"], "分摊比例": 30},
            ])
        self.assertIn("100", str(cm.exception))
        with self.assertRaises(ValueError) as cm2:
            bu.save_bu_config(self.cfg, self.root, [
                {"name": "BU甲", "销售": ["销售A"], "分摊比例": 40},
                {"name": "BU乙", "销售": ["销售B"], "分摊比例": None},
            ])
        self.assertIn("全部留空", str(cm2.exception))
        saved = bu.save_bu_config(self.cfg, self.root, [
            {"name": "BU甲", "销售": ["销售A"], "分摊比例": 40},
            {"name": "BU乙", "销售": ["销售B"], "分摊比例": 60},
        ])
        self.assertTrue(saved["公共费用分摊启用"])
        self.assertEqual(sum(b["分摊比例"] for b in saved["bus"]), 100.0)


class TestBuConservation(_Base):
    def test_sum_bus_plus_unassigned_equals_company(self):
        """守恒红线：∑BU + 未归属(有名) + 销售空行 == 全公司（收入/下单/回款三口径，全年周期）。
        全公司=不过滤的 build_summary（空台账空手填，与 BU 同可比口径）；销售空行进不了任何 BU 页。"""
        proj, orders, receipts, inhouse = self._rows()
        yk = "2026年"
        full = profit.build_summary(self.cfg, proj, orders, receipts, inhouse,
                                    list(profit._BU_EMPTY_LEDGER_HEADER), [], TODAY.year, TODAY,
                                    manual_raw={})["periods"][yk]
        totals = {"revenue_net": 0.0, "orders": 0.0, "receipts": 0.0}
        for s in ({"销售A"}, {"销售B"}, {"销售C"}):   # 两个 BU + 未归属（有名）
            p = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, s)["periods"][yk]
            for k in totals:
                totals[k] += p[k]
        # 收入/下单：所有行都有销售名 → 严丝合缝
        self.assertAlmostEqual(totals["revenue_net"], full["revenue_net"], places=2)
        self.assertAlmostEqual(totals["orders"], full["orders"], places=2)
        # 回款：R3 销售为空（100 元）→ 差额恰等于空名行金额（未归属·不进任何 BU 页）
        self.assertAlmostEqual(full["receipts"] - totals["receipts"], 100.0, places=2)
        # 数值抽查：BU甲 全年下单 1000、回款 800
        pa = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售A"})["periods"][yk]
        self.assertAlmostEqual(pa["orders"], 1000.0, places=2)
        self.assertAlmostEqual(pa["receipts"], 800.0, places=2)

    def test_common_expense_zero_and_pretax_formula(self):
        """分摊关：公共费用恒 0；BU 税前利润 = 毛利 − 附加税费（手填/台账项都不混入）。"""
        proj, orders, receipts, inhouse = self._rows()
        p = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售A"})["periods"]["2026年"]
        self.assertEqual(p["expense"]["total"], 0.0)
        for v in p["ledger_expenses"].values():
            self.assertEqual(v, 0.0)
        self.assertEqual(p["other_pl"], 0.0)
        self.assertAlmostEqual(p["pretax_profit"], round(p["gross_profit"] - p["surtax"], 2), places=2)
        # 生产成本只含系统项：直接成本 300 − 内部译员 50（手填 6 项恒 0）
        self.assertAlmostEqual(p["production_cost"], 250.0, places=2)

    def test_alloc_conservation_and_pretax(self):
        """分摊开：ΣBU 公共费用 == 全公司台账公共；税前=毛利−分摊公共−附加税（真实 build_bu_summary）。"""
        proj, orders, receipts, inhouse = self._rows()
        yk = "2026年"
        # 全公司台账 5 类（合成）——与 expense_categories_included 一致
        led_year = {"市场费用": 1000.0, "管理费用": 2000.0, "固定运营费用": 500.0,
                    "技术服务费": 300.0, "财务费用": 200.0}
        company_total = sum(led_year.values())
        # 给所有周期同一套台账（守恒只验全年；各周期同样×比例）
        base = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售A"})
        company_led = {k: dict(led_year) for k in base["periods"]}
        sa = profit.build_bu_summary(
            self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售A"},
            company_ledger_by_period=company_led, alloc_ratio_pct=40, alloc_enabled=True)
        sb = profit.build_bu_summary(
            self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售B"},
            company_ledger_by_period=company_led, alloc_ratio_pct=60, alloc_enabled=True)
        pa, pb = sa["periods"][yk], sb["periods"][yk]
        self.assertAlmostEqual(pa["expense"]["total"] + pb["expense"]["total"], company_total, places=2)
        for cat, v in led_year.items():
            self.assertAlmostEqual(
                pa["ledger_expenses"].get(cat, 0) + pb["ledger_expenses"].get(cat, 0), v, places=2)
        self.assertAlmostEqual(
            pa["pretax_profit"],
            round(pa["gross_profit"] - pa["expense"]["total"] - pa["surtax"], 2), places=2)
        self.assertTrue(sa["meta"]["public_allocation"]["enabled"])
        self.assertEqual(sa["meta"]["public_allocation"]["ratio_disp"], "40%")
        # 关态与现状一致
        off = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售A"})
        self.assertFalse(off["meta"]["public_allocation"]["enabled"])
        self.assertEqual(off["periods"][yk]["expense"]["total"], 0.0)

    def test_config_change_takes_effect(self):
        """配置增改生效：把销售B 划入 BU甲 → 数字随之变。"""
        proj, orders, receipts, inhouse = self._rows()
        p1 = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售A"})["periods"]["2026年"]
        p2 = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, {"销售A", "销售B"})["periods"]["2026年"]
        self.assertAlmostEqual(p2["orders"] - p1["orders"], 2000.0, places=2)
        self.assertAlmostEqual(p2["receipts"] - p1["receipts"], 900.0, places=2)


class TestBuPages(_Base):
    def test_pages_secrecy(self):
        """严格保密：BU 页不含其他 BU 的 BU名/负责人/销售名。"""
        _write_bucfg(self.cfg, self.root, _two_bus())
        pages = self._pages()
        ha, hb = pages["BU甲"]["html"], pages["BU乙"]["html"]
        self.assertIn("BU甲", ha)
        for leak in ("BU乙", "负责人乙", "销售B", "客户乙"):
            self.assertNotIn(leak, ha, f"BU甲页泄漏了 {leak}")
        self.assertIn("BU乙", hb)
        for leak in ("BU甲", "负责人甲", "销售A", "客户甲"):
            self.assertNotIn(leak, hb, f"BU乙页泄漏了 {leak}")

    def test_page_labels(self):
        """分摊关：暂不分摊 / 待陆总手填；有返回整体 + 基本情况 KPI；不含全公司出口。"""
        _write_bucfg(self.cfg, self.root, _two_bus())
        h = self._pages()["BU甲"]["html"]
        self.assertIn("暂不分摊", h)
        self.assertIn("待陆总", h)
        self.assertIn("基本情况", h)  # 迭代18：BU 页也有基本情况
        self.assertIn("返回整体", h)
        self.assertIn('href="/"', h)
        self.assertNotIn("exportBtn", h)
        self.assertNotIn("dailyBtn", h)
        self.assertNotIn("dailyPanel", h)
        self.assertNotIn("/api/daily", h)
        self.assertNotIn("按40%分摊", h)  # 未开分摊不显示比例标注
        self.assertNotIn("按 40%", h)

    def test_page_alloc_on_shows_ratio_not_other_bu(self):
        """分摊开：本 BU 显示比例分摊标注；不泄漏他 BU 名与他 BU 比例。"""
        data = {"bus": [
            {"name": "BU甲", "负责人": ["负责人甲"], "销售": ["销售A"], "分摊比例": 40},
            {"name": "BU乙", "负责人": ["负责人乙"], "销售": ["销售B"], "分摊比例": 60},
        ], "公共费用分摊启用": True}
        p = bu.config_path(self.cfg, self.root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        h = self._pages()["BU甲"]["html"]
        self.assertIn("按40%分摊", h)
        self.assertIn("按 <b>40%</b>", h)  # faint 注记
        self.assertNotIn("BU乙", h)
        self.assertNotIn("按60%分摊", h)
        self.assertNotIn("按 <b>60%</b>", h)
        self.assertNotIn("/api/daily", h)

    def test_xss_escaped(self):
        """XSS：BU 名含 HTML 特殊字符必转义（铁律10）。"""
        evil = '<script>alert("x")</script>'
        _write_bucfg(self.cfg, self.root, [
            {"name": evil, "负责人": [], "销售": ['销售"A<b>']}])
        h = self._pages()[evil]["html"]
        self.assertNotIn("<script>alert", h)
        self.assertIn("&lt;script&gt;", h)

    def test_source_sales_xss_escaped_in_ranking(self):
        """来自智云的销售自由文本进排名卡时也必须转义，不能只保护配置字段。"""
        proj, orders, receipts, inhouse = self._rows()
        evil = '销售"<b>甲'
        orders[0]["销售"] = evil
        p = profit.build_bu_summary(self.cfg, proj, orders, receipts, inhouse, TODAY, {evil})
        h = render.render_bu_page("BU甲", p, self.cfg, "")
        self.assertNotIn(evil, h)
        self.assertIn("销售&quot;&lt;b&gt;甲", h)


class TestBuEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        _seed(cls.cfg, cls.root)
        _write_bucfg(cls.cfg, cls.root, _two_bus())
        conn = db.connect(cls.cfg, cls.root)
        server._state["user_html"] = "<html>USER-MAIN</html>"
        server._state["bu_pages"] = core.build_bu_pages(cls.cfg, conn, TODAY, "", cls.root)
        conn.close()
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)   # 未登录（不共享 cookie 罐）
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    def test_bu_page_by_name_admin_session(self):
        from urllib.parse import quote
        r = self.client.get(f"/bu/{quote('BU甲')}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("BU甲", r.text)
        self.assertNotIn("BU乙", r.text)

    def test_unknown_bu_404_no_hint(self):
        from urllib.parse import quote
        for t in ("不存在BU", "x", ""):
            r = self.client.get(f"/bu/{quote(t)}")
            self.assertIn(r.status_code, (404, 307))   # ""→ /bu/ 路由不存在
            if r.status_code == 404:
                self.assertNotIn("BU甲", r.text)

    def test_main_page_unchanged(self):
        r = self.client.get("/")
        self.assertEqual(r.text, "<html>USER-MAIN</html>")

    def test_api_requires_login(self):
        self.assertEqual(self.anon.get("/api/bu_config").status_code, 401)
        self.assertEqual(self.anon.post("/api/bu_config", json={"bus": []}).status_code, 401)

    def test_api_get_with_session(self):
        r = self.client.get("/api/bu_config", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 2)

    def test_api_post_validates(self):
        r = self.client.post("/api/bu_config", json={"bus": "不是列表"}, headers=self.hdr)
        self.assertEqual(r.status_code, 400)

    def test_api_post_saves_and_recomputes(self):
        """管理员修改销售归属后，服务端落盘并触发重算；匿名用户无写入口。"""
        from unittest.mock import patch
        payload = {"bus": [{"name": "BU丙", "负责人": "负责人丙", "销售": "销售C"}]}
        with patch.object(server, "recompute") as rec:
            r = self.client.post("/api/bu_config", json=payload, headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)
        self.assertNotIn("密码hash", r.json()["bus"][0])
        self.assertEqual(bu.load_bu_config(self.cfg, self.root)["bus"][0]["销售"], ["销售C"])
        rec.assert_called_once_with(self.cfg, self.root)

    def test_sales_pool_requires_login_and_lists_seed(self):
        self.assertEqual(self.anon.get("/api/sales_pool").status_code, 401)
        r = self.client.get("/api/sales_pool", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        names = {x["name"] for x in r.json()["sales"]}
        self.assertTrue({"销售A", "销售B", "销售C"} <= names)
        self.assertTrue(all("rows" in x and x["rows"] >= 1 for x in r.json()["sales"]
                            if x["name"] in ("销售A", "销售B", "销售C")))

    def test_one_sales_one_bu_on_save(self):
        """同一销售写进多个 BU → 只保留先出现的 BU。"""
        saved = bu.save_bu_config(self.cfg, self.root, [
            {"name": "BU甲", "销售": ["销售A", "销售X"]},
            {"name": "BU乙", "销售": ["销售A", "销售B"]},  # 销售A 重复
        ])
        by = {b["name"]: b["销售"] for b in saved["bus"]}
        self.assertEqual(by["BU甲"], ["销售A", "销售X"])
        self.assertEqual(by["BU乙"], ["销售B"])  # A 被先到的 BU甲 占走


class TestZeroConfigServer(unittest.TestCase):
    def test_bu_route_404_when_disabled(self):
        from fastapi.testclient import TestClient
        tmp = Path(tempfile.mkdtemp())
        cfg = loaders.load_config()
        _seed(cfg, tmp)
        server._state["bu_pages"] = {}
        server._state["user_html"] = "<html>USER-MAIN</html>"
        app = server.create_app(cfg, root=tmp)
        client = TestClient(app, follow_redirects=False)
        from urllib.parse import quote
        self.assertEqual(client.get(f"/bu/{quote('BU甲')}").status_code, 404)
        self.assertEqual(client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=1)
