#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""费用去税率（按类别·全局一套·陆总0714）测试。
跑：.venv/bin/python tests/test_detax.py

背景（陆总2026-07-14过盘原话）：台账费用多为含税，能抵进项的主要是房租/物业——留个空让陆总
按类别填增值税率%，看板按「不含税额 = 含税额 ÷ (1 + 税率%)」还原真实费用；大部分费用抵不了税留空即可。
**默认全空 = 不去税、页面数字一分不变（回归红线中性）**；全公司一套、常年沿用。

守卫点：
- db 写读：set/load 去税率；None/空/0=删行（默认不去税）；越界(0~100)拒
- list_detax_categories：只列期间费用白名单大类下的细类、按金额降序、排除空细类与白名单外
- detax_ledger_rows：率>0 按 ÷(1+率) 去税、空/None=恒等（同对象）、缺列安全、只改金额列不改行数
- 计算集成：去税后该细类费用缩小、其余不动；大类合计==细类合计（守恒·不出两处真相）
- 接口：仅管理员（匿名 401）；率越界拒（>100→400）；保存/回读/删行；C3 留痕类别「去税」
"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import columns  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import profit  # noqa: E402
import server  # noqa: E402

CFG = loaders.load_config()
START, END = datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)

HDR = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]
# 房租含税 109（率9%→不含税100）、办公用品含税 100（不去税）、白名单外一行（两不算）
ROWS = [
    ("2026年3月", "2026-03-05", 109.0, "语言", "固定运营费用", "房租", "运保"),
    ("2026年3月", "2026-03-08", 100.0, "数据", "管理费用", "办公用品", "运保"),
    ("2026年4月", "2026-04-03", 999.0, "语言", "生产成本-译费", "译费", "运保"),  # 白名单外
]


class TestDbDetax(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = db.connect(CFG, Path(self.tmp))

    def tearDown(self):
        self.conn.close()

    def test_set_load_delete(self):
        db.set_detax_rate(self.conn, "房租", 9, "t")
        db.set_detax_rate(self.conn, "物业费", 6.005, "t")  # 四舍五入到 0.01
        self.assertEqual(db.load_detax_rates(self.conn), {"房租": 9.0, "物业费": 6.0})
        db.set_detax_rate(self.conn, "房租", None, "t")  # None=删行
        self.assertEqual(db.load_detax_rates(self.conn), {"物业费": 6.0})
        db.set_detax_rate(self.conn, "物业费", 0, "t")  # 0=删行（默认不去税）
        self.assertEqual(db.load_detax_rates(self.conn), {})
        db.set_detax_rate(self.conn, "房租", "", "t")  # 空串=删行（幂等）
        self.assertEqual(db.load_detax_rates(self.conn), {})

    def test_range_and_empty_guard(self):
        with self.assertRaises(ValueError):
            db.set_detax_rate(self.conn, "房租", 120, "t")
        with self.assertRaises(ValueError):
            db.set_detax_rate(self.conn, "房租", -1, "t")
        with self.assertRaises(ValueError):
            db.set_detax_rate(self.conn, "", 9, "t")

    def test_load_empty_no_table(self):
        # 无数据/中性：默认空字典（回归红线中性）
        self.assertEqual(db.load_detax_rates(self.conn), {})

    def test_list_categories(self):
        import money

        for r in ROWS:
            self.conn.execute(
                "INSERT INTO std_费用明细(含税金额,对应报表大类,预算明细费用类型,已删除) VALUES(?,?,?,0)",
                (money.yuan_to_fen(r[2]), r[4], r[5]),
            )
        # 空细类行（白名单大类但细类空）不应出现在清单里
        self.conn.execute(
            "INSERT INTO std_费用明细(含税金额,对应报表大类,预算明细费用类型,已删除) VALUES(?,?,?,0)",
            (money.yuan_to_fen(50), "管理费用", ""),
        )
        self.conn.commit()
        cats = db.list_detax_categories(self.conn, CFG)
        names = [c["category"] for c in cats]
        self.assertIn("房租", names)
        self.assertIn("办公用品", names)
        self.assertNotIn("译费", names)  # 白名单外大类
        self.assertNotIn("", names)  # 空细类不列
        # 按金额降序：房租(109) 在 办公用品(100) 前
        self.assertLess(names.index("房租"), names.index("办公用品"))
        self.assertAlmostEqual(dict((c["category"], c["amount"]) for c in cats)["房租"], 109.0, places=2)


class TestDetaxLedgerRows(unittest.TestCase):
    def test_rate_divides(self):
        out = profit.detax_ledger_rows(HDR, ROWS, {"房租": 9})
        lcols = columns.resolve_ledger_columns(HDR)
        ci = lcols["含税金额"]
        self.assertAlmostEqual(out[0][ci], 100.0, places=6)  # 109 ÷ 1.09
        self.assertAlmostEqual(out[1][ci], 100.0, places=6)  # 办公用品未填率=不动
        self.assertAlmostEqual(out[2][ci], 999.0, places=6)  # 白名单外行也不动（率没配到）
        self.assertEqual(len(out), len(ROWS))  # 行数不变

    def test_empty_is_identity(self):
        self.assertIs(profit.detax_ledger_rows(HDR, ROWS, {}), ROWS)
        self.assertIs(profit.detax_ledger_rows(HDR, ROWS, None), ROWS)
        self.assertIs(profit.detax_ledger_rows([], ROWS, {"房租": 9}), ROWS)  # 无表头

    def test_short_row_safe(self):
        # 行比列数短（被截断）→ 跳过不改、不崩（len(row)>c_amt 守卫）
        rows = [("2026年3月",)]
        out = profit.detax_ledger_rows(HDR, rows, {"房租": 9})
        self.assertEqual(out, rows)

    def test_zero_rate_no_change(self):
        out = profit.detax_ledger_rows(HDR, ROWS, {"房租": 0})
        lcols = columns.resolve_ledger_columns(HDR)
        self.assertAlmostEqual(out[0][lcols["含税金额"]], 109.0, places=6)


class TestDetaxComputeIntegration(unittest.TestCase):
    """去税后走真实计算：该细类缩小、其余不动、大类合计==细类合计（守恒）。"""

    def _l(self):
        return columns.resolve_ledger_columns(HDR)

    def test_detax_shrinks_and_conserves(self):
        lcols = self._l()
        base_fine = profit.compute_expenses_by_fine_type(ROWS, 2026, START, END, CFG, lcols)
        self.assertAlmostEqual(dict(base_fine["固定运营费用"])["房租"], 109.0, places=2)

        dtx = profit.detax_ledger_rows(HDR, ROWS, {"房租": 9})
        by_cat, _ = profit.compute_ledger_expenses(dtx, 2026, START, END, CFG, lcols)
        fine = profit.compute_expenses_by_fine_type(dtx, 2026, START, END, CFG, lcols)
        # 房租去税后 100；办公用品不动 100（compute_*_fine_type 返回 {大类:[(细类,金额),...]}）
        self.assertAlmostEqual(dict(fine["固定运营费用"])["房租"], 100.0, places=2)
        self.assertAlmostEqual(dict(fine["管理费用"])["办公用品"], 100.0, places=2)
        # 守恒：每个大类合计 == 该大类下细类合计（源头统一去税、无两处真相）
        for cat, fines in fine.items():
            self.assertAlmostEqual(by_cat.get(cat, 0.0), sum(v for _, v in fines), places=2, msg=cat)


class TestDetaxApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "<html>ADMIN</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        # 种入真实台账细类：GET 才走 categories+amount_disp（fmt_wan）路径——
        # 空库 categories=[] 会漏掉 fmt_wan（曾漏 server.py 缺 import charts 的 500，见 test_get_categories_populated）
        conn = db.connect(cls.cfg, cls.root)
        try:
            import money

            for big, fine, amt in [
                ("固定运营费用", "房租", 1090000.0),
                ("管理费用", "办公用品", 100000.0),
                ("生产成本-译费", "译费", 999.0),
            ]:  # 白名单外；amt 元 → 分
                conn.execute(
                    "INSERT INTO std_费用明细(含税金额,对应报表大类,预算明细费用类型,已删除) VALUES(?,?,?,0)",
                    (money.yuan_to_fen(amt), big, fine),
                )
            conn.commit()
        finally:
            conn.close()
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def test_get_categories_populated(self):
        # 非空台账 → categories 带金额串（fmt_wan）·降序·排除白名单外（回归 server.py 缺 import charts 的 500）
        g = self.client.get("/api/detax_rates", headers=self.hdr)
        self.assertEqual(g.status_code, 200, g.text)
        cats = g.json()["categories"]
        names = [c["category"] for c in cats]
        self.assertIn("房租", names)
        self.assertIn("办公用品", names)
        self.assertNotIn("译费", names)  # 白名单外
        self.assertLess(names.index("房租"), names.index("办公用品"))  # 金额降序
        self.assertTrue(cats[0]["amount_disp"].endswith("万"))  # 金额串格式化成功

    def test_no_duplicate_element_ids_in_console(self):
        # 回归：detax 表 id 曾用 dTbl 与既有明细表 dTbl 撞车 → getElementById 命中错表、去税表空白不渲染。
        # 全控制台静态 id 不得重复（这类"页面看着空但 DOM 有数据"的坑，单测/接口都抓不到，只有整页扫 id 能防）。
        import re
        import collections

        ids = re.findall(r'id="([A-Za-z][\w-]*)"', server.admin_ui_source())
        dups = [i for i, n in collections.Counter(ids).items() if n > 1]
        self.assertEqual(dups, [], f"控制台存在重复 element id：{dups}")
        self.assertIn("dxTbl", ids)  # 去税表 id 存在且唯一

    def test_requires_login(self):
        self.assertEqual(self.anon.get("/api/detax_rates").status_code, 401)
        self.assertEqual(self.anon.post("/api/detax_rates", json={"rates": {"房租": 9}}).status_code, 401)

    def test_reject_out_of_range(self):
        r = self.client.post("/api/detax_rates", headers=self.hdr, json={"rates": {"房租": 120}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("0~100", r.json()["detail"])
        r2 = self.client.post("/api/detax_rates", headers=self.hdr, json={"rates": {}})
        self.assertEqual(r2.status_code, 400)  # 空 rates 拒

    def test_save_readback_delete_and_audit(self):
        r = self.client.post("/api/detax_rates", headers=self.hdr, json={"rates": {"房租": 9, "物业费": 6}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["rates"], {"房租": 9.0, "物业费": 6.0})
        g = self.client.get("/api/detax_rates", headers=self.hdr).json()
        self.assertEqual(g["rates"], {"房租": 9.0, "物业费": 6.0})
        self.assertIn("categories", g)  # 类别清单字段在（空库=[]）
        # None=删行
        r2 = self.client.post("/api/detax_rates", headers=self.hdr, json={"rates": {"物业费": None}})
        self.assertEqual(r2.json()["rates"], {"房租": 9.0})
        # C3 留痕类别「去税」
        conn = db.connect(self.cfg, self.root)
        try:
            rows = conn.execute("SELECT 摘要 FROM manual_配置变更 WHERE 类别='去税'").fetchall()
        finally:
            conn.close()
        self.assertTrue(rows, "去税配置变更应留痕")


if __name__ == "__main__":
    unittest.main(verbosity=2)
