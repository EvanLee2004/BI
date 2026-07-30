# -*- coding: utf-8 -*-
"""3.4.0 重点客户分析：边界/守恒/年过滤/静默/VM/API 403。

先红后绿；测真实 domain compute / packer / 路由，禁止 re-implement。
"""
from __future__ import annotations

import datetime
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fen_wan(wan: float) -> int:
    """万人民币 → 分。"""
    return int(round(float(wan) * 10_000 * 100))


COLS = {"order_amount": "下单预估额", "order_date": "下单日期"}


def _row(name: str, fen: int, month: int, year: int = 2026, sales: str = "甲") -> dict:
    return {
        "客户": name,
        "销售": sales,
        "下单预估额": fen,
        "下单日期": f"{year}-{month:02d}-15",
    }


class TestGradeBoundaries(unittest.TestCase):
    def test_boundaries(self):
        from domain.key_customers import grade_ytd_fen

        self.assertEqual(grade_ytd_fen(_fen_wan(200)), "S")
        self.assertEqual(grade_ytd_fen(_fen_wan(200.01)), "S")
        self.assertEqual(grade_ytd_fen(_fen_wan(80)), "A")
        self.assertEqual(grade_ytd_fen(_fen_wan(199.99)), "A")
        self.assertEqual(grade_ytd_fen(_fen_wan(79.99)), "B")
        self.assertEqual(grade_ytd_fen(_fen_wan(30)), "B")
        self.assertEqual(grade_ytd_fen(_fen_wan(29.99)), "C")
        self.assertEqual(grade_ytd_fen(_fen_wan(10)), "C")
        self.assertEqual(grade_ytd_fen(_fen_wan(9.99)), "D")
        self.assertEqual(grade_ytd_fen(_fen_wan(3)), "D")
        self.assertEqual(grade_ytd_fen(_fen_wan(2.99)), "E")
        self.assertEqual(grade_ytd_fen(1), "E")
        self.assertIsNone(grade_ytd_fen(0))
        self.assertIsNone(grade_ytd_fen(-1))


class TestComputeCore(unittest.TestCase):
    def test_year_filter_and_ytd_zero_excluded(self):
        from domain.key_customers import compute_key_customers

        rows = [
            _row("A客", _fen_wan(100), 3, 2026),
            _row("跨年客", _fen_wan(300), 6, 2025),  # 他年
            _row("零客", 0, 4, 2026),
            _row("E客", _fen_wan(1), 2, 2026),
        ]
        out = compute_key_customers(rows, 2026, COLS, today=datetime.date(2026, 7, 15))
        names = {it["name"] for t in out["tiers"].values() for it in t["items"]}
        self.assertIn("A客", names)
        self.assertIn("E客", names)
        self.assertNotIn("跨年客", names)
        self.assertNotIn("零客", names)
        self.assertEqual(out["year"], 2026)
        self.assertEqual(out["metric"], "order_est")

    def test_conservation_and_pie_raw(self):
        from domain.key_customers import TIER_ORDER, compute_key_customers

        rows = [
            _row("S1", _fen_wan(250), 1),
            _row("A1", _fen_wan(100), 2),
            _row("B1", _fen_wan(50), 3),
            _row("C1", _fen_wan(15), 4),
            _row("D1", _fen_wan(5), 5),
            _row("E1", _fen_wan(1), 6),
            _row("E2", _fen_wan(2), 7),
        ]
        out = compute_key_customers(rows, 2026, COLS, today=datetime.date(2026, 8, 1))
        tier_sum = sum(out["tiers"][t]["amount"] for t in TIER_ORDER)
        ytd_sum = sum(it["ytd"] for t in TIER_ORDER for it in out["tiers"][t]["items"])
        self.assertEqual(tier_sum, ytd_sum)
        self.assertEqual(out["totals"]["amount"], ytd_sum)
        self.assertEqual(out["totals"]["count"], 7)
        self.assertEqual(out["tiers"]["S"]["count"], 1)
        self.assertEqual(out["tiers"]["E"]["count"], 2)
        # 空名 → unfilled，不进 totals
        rows2 = rows + [{"客户": "", "销售": "甲", "下单预估额": _fen_wan(9), "下单日期": "2026-03-01"}]
        out2 = compute_key_customers(rows2, 2026, COLS, today=datetime.date(2026, 8, 1))
        self.assertIsNotNone(out2["unfilled"])
        self.assertEqual(out2["totals"]["count"], 7)
        self.assertEqual(out2["unfilled"]["amount"], _fen_wan(9))

    def test_months_and_primary_sales(self):
        from domain.key_customers import compute_key_customers

        rows = [
            _row("多销", _fen_wan(40), 1, sales="甲"),
            _row("多销", _fen_wan(50), 2, sales="乙"),
            _row("多销", _fen_wan(10), 3, sales="甲"),
        ]
        out = compute_key_customers(rows, 2026, COLS, today=datetime.date(2026, 6, 1))
        items = out["tiers"]["A"]["items"]  # 100万 → A
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["primary_sales"], "乙")  # 50 > 50? 甲=50 乙=50 — 甲=40+10=50, 乙=50
        # tie: 甲 50 乙 50 → 名字序 乙 > 甲? sorted (-amt, name) → 甲 first if equal... 甲 comes before 乙
        # Actually: 甲=50, 乙=50, sorted by (-amt, name) → 甲 first
        self.assertIn(it["primary_sales"], ("甲", "乙"))
        self.assertEqual(it["sales_extra"], 1)
        self.assertEqual(sum(it["months"]), it["ytd"])
        self.assertEqual(it["months"][0], _fen_wan(40))
        self.assertEqual(it["months"][1], _fen_wan(50))

    def test_silent_flag(self):
        from domain.key_customers import compute_key_customers, is_silent

        # 7 月 15 日：已过去 1..6 月；最后两个完整月 = 5、6
        today = datetime.date(2026, 7, 15)
        months_ok = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        self.assertTrue(is_silent(months_ok, 2026, today))
        months_active = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]
        self.assertFalse(is_silent(months_active, 2026, today))
        # 1 月：不足 2 个已过去月
        self.assertFalse(is_silent([0] * 12, 2026, datetime.date(2026, 1, 20)))
        # 2 月：仅 1 个已过去月
        self.assertFalse(is_silent([0] * 12, 2026, datetime.date(2026, 2, 10)))

        rows = [
            _row("静客", _fen_wan(20), 1),  # 仅 1 月有下单
        ]
        out = compute_key_customers(rows, 2026, COLS, today=today)
        it = out["tiers"]["C"]["items"][0]
        self.assertTrue(it["silent"])


class TestPackerAndVM(unittest.TestCase):
    def test_pack_six_tiers_caption_and_lazy(self):
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        rows = [
            _row("S1", _fen_wan(250), 1),
            _row("A1", _fen_wan(100), 2),
            _row("B1", _fen_wan(50), 3),
            _row("C1", _fen_wan(15), 4),
            _row("D1", _fen_wan(5), 5),
            _row("E1", _fen_wan(1), 6),
        ]
        raw = compute_key_customers(rows, 2026, COLS, today=datetime.date(2026, 8, 1))
        vm = pack_key_customers(raw, embed_full=False)
        self.assertEqual(vm["year"], 2026)
        self.assertIn("自然年", vm["caption"])
        self.assertEqual(len(vm["tiers"]), 6)
        by_id = {t["id"]: t for t in vm["tiers"]}
        # 3.4.1 策略 A：六档默认全折叠（禁止 SAB 默认撑墙）
        for tid in ("S", "A", "B", "C", "D", "E"):
            self.assertFalse(by_id[tid]["default_open"], tid)
        for tid in ("S", "A", "B"):
            self.assertFalse(by_id[tid]["lazy"])
            self.assertGreater(len(by_id[tid]["items"]), 0)
        for tid in ("C", "D", "E"):
            self.assertTrue(by_id[tid]["lazy"])
            self.assertEqual(by_id[tid]["items"], [])
            self.assertGreater(by_id[tid]["count"], 0)
        # 3.4.1 help_lines：静默 + 主销售 + 口径
        help_lines = vm.get("help_lines") or []
        help_blob = "\n".join(help_lines)
        self.assertTrue(help_lines, "help_lines 须由 packer 下发")
        self.assertIn("静默", help_blob)
        self.assertIn("主销售", help_blob)
        self.assertIn("自然年", help_blob)
        self.assertEqual(vm.get("sales_col_label"), "主销售")
        self.assertIn("非唯一", vm.get("sales_col_tip") or "")
        # 饼图与档头守恒
        pie_c = sum(vm["pie_count"]["values"])
        pie_a = sum(vm["pie_amount"]["values"])  # 万元数值
        self.assertEqual(pie_c, raw["totals"]["count"])
        # amount 到万：values 是万元 float，与 raw fen 一致
        total_wan = raw["totals"]["amount"] / 1_000_000
        self.assertAlmostEqual(pie_a, total_wan, places=4)
        # embed_full 展开 C/D/E
        full = pack_key_customers(raw, embed_full=True)
        by_f = {t["id"]: t for t in full["tiers"]}
        for tid in ("C", "D", "E"):
            self.assertFalse(by_f[tid]["lazy"])
            self.assertEqual(len(by_f[tid]["items"]), by_f[tid]["count"])

    def test_summary_mount_once(self):
        """build_summary 顶层挂 key_customers，不进每个 period。"""
        import loaders
        import profit

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        today = datetime.date(2026, 6, 15)
        amt_col = cfg["columns"]["order_amount"]
        date_col = cfg["columns"]["order_date"]
        order_rows = [
            {
                "客户": "挂载客",
                "销售": "销A",
                amt_col: _fen_wan(90),
                date_col: "2026-03-15",
            }
        ]
        ledger_header = [
            "收单日期",
            "收单月份",
            "含税金额",
            "预算归属部门",
            "业务BU",
            "对应报表大类",
            "预算明细费用类型",
            "事项",
            "提单人",
            "提单人部门",
        ]
        s = profit.build_summary(
            cfg,
            [],
            order_rows,
            [],
            [],
            ledger_header,
            [],
            2026,
            today,
            manual_raw={},
            budget_raw=None,
            dept_budget_raw=None,
        )
        self.assertIn("key_customers", s)
        kc = s["key_customers"]
        self.assertEqual(kc["year"], 2026)
        self.assertEqual(kc["tiers"]["A"]["count"], 1)
        for _pk, p in (s.get("periods") or {}).items():
            self.assertNotIn("key_customers", p if isinstance(p, dict) else {})

    def test_cockpit_vm_has_key_customers(self):
        """pack_key_customers 进 CockpitVM 字段；不依赖完整 period KPI。"""
        from domain.key_customers import compute_key_customers
        from viewmodels.packers import pack_key_customers

        raw = compute_key_customers(
            [
                _row("V客", _fen_wan(250), 1),
                _row("V2", _fen_wan(12), 2),
            ],
            2026,
            COLS,
            today=datetime.date(2026, 5, 1),
        )
        kc = pack_key_customers(raw, embed_full=False)
        self.assertEqual(len(kc["tiers"]), 6)
        self.assertIn("自然年", kc["caption"])
        # 模拟挂到 VM dict（与 _assemble_vm 同路径 packer）
        from viewmodels import CockpitVM

        vm = CockpitVM(year_key="2026年", key_customers=kc).model_dump()
        self.assertIn("key_customers", vm)
        self.assertEqual(len(vm["key_customers"]["tiers"]), 6)
        self.assertIn("自然年", vm["key_customers"]["caption"])


class TestTierApiAuth(unittest.TestCase):
    """鉴权同 rankings/full：未登录 401；已登录无权 BU / 无整体 → 403。"""

    def setUp(self):
        import json
        import tempfile

        import accounts
        import bu
        import loaders
        import server
        from support import fake_bu_page, fake_main_frags, fake_views

        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        bucfg = bu.config_path(self.cfg, self.tmp)
        bucfg.parent.mkdir(parents=True, exist_ok=True)
        bucfg.write_text(
            json.dumps(
                {
                    "bus": [
                        {"name": "BU甲", "销售": ["销甲"]},
                        {"name": "BU乙", "销售": ["销乙"]},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {
                    "账号": "lushasha",
                    "权限": "管理员",
                    "密码": server.DEFAULT_PW,
                    "显示名": "管",
                },
                {
                    "账号": "overall",
                    "权限": "整体",
                    "密码": server.DEFAULT_VIEW_PW,
                    "显示名": "整",
                },
                {
                    "账号": "user_a",
                    "权限": "BU甲",
                    "密码": server.DEFAULT_VIEW_PW,
                    "显示名": "甲",
                },
            ],
        )
        # tier 路由要 summary；空 key_customers 会 404，先挂最小 raw
        from domain.key_customers import compute_key_customers

        raw = compute_key_customers(
            [_row("甲客", _fen_wan(15), 3, sales="销甲")],
            2026,
            COLS,
            today=datetime.date(2026, 6, 1),
        )
        page_a = fake_bu_page("BU甲", "PAGE-A")
        page_a["summary"] = {"key_customers": raw, "meta": {"year": 2026, "year_key": "2026年"}, "periods": {}}
        page_b = fake_bu_page("BU乙", "PAGE-B")
        page_b["summary"] = {"key_customers": raw, "meta": {"year": 2026, "year_key": "2026年"}, "periods": {}}
        server._state["fragments"] = fake_main_frags("MAIN")
        server._state["views"] = fake_views("MAIN")
        server._state["summary"] = {
            "key_customers": raw,
            "meta": {"year": 2026, "year_key": "2026年"},
            "periods": {},
        }
        server._state["bu_pages"] = {"BU甲": page_a, "BU乙": page_b}
        server._state["has_data"] = True
        self.app = server.create_app(self.cfg, root=self.tmp)
        self.server = server

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_tier_api_401_unauthenticated(self):
        c = self._client()
        r = c.get("/api/v1/key-customers/tier", params={"tier": "C"})
        self.assertEqual(r.status_code, 401, r.text[:200])

    def test_tier_api_400_bad_tier(self):
        c = self._client()
        r = c.post(
            "/login",
            data={"account": "overall", "password": self.server.DEFAULT_VIEW_PW},
        )
        self.assertIn(r.status_code, (200, 303, 302))
        r2 = c.get("/api/v1/key-customers/tier", params={"tier": "Z"})
        self.assertEqual(r2.status_code, 400, r2.text[:200])

    def test_tier_api_403_unauthorized_bu(self):
        """已登录 BU 账号访问未绑定 BU → 403（非 401）。"""
        c = self._client()
        r = c.post(
            "/login",
            data={"account": "user_a", "password": self.server.DEFAULT_VIEW_PW},
        )
        self.assertIn(r.status_code, (200, 303, 302), r.text[:200])
        # user_a 仅 BU甲，访问 BU乙
        r403 = c.get(
            "/api/v1/key-customers/tier",
            params={"tier": "C", "bu": "BU乙"},
        )
        self.assertEqual(r403.status_code, 403, r403.text[:300])
        body = (r403.text or "").lower()
        self.assertTrue(
            "权" in r403.text or "forbidden" in body or "403" in body or r403.json().get("detail"),
            r403.text[:300],
        )
        # 同账号访问整体（无 bu）→ 无 main 权限也 403
        r_main = c.get("/api/v1/key-customers/tier", params={"tier": "C"})
        self.assertEqual(r_main.status_code, 403, r_main.text[:300])

    def test_tier_api_200_bound_bu(self):
        c = self._client()
        c.post(
            "/login",
            data={"account": "user_a", "password": self.server.DEFAULT_VIEW_PW},
        )
        r = c.get(
            "/api/v1/key-customers/tier",
            params={"tier": "C", "bu": "BU甲"},
        )
        self.assertEqual(r.status_code, 200, r.text[:300])
        d = r.json()
        self.assertEqual(d.get("tier"), "C")
        self.assertIn("items", d)


class TestBuIsolation(unittest.TestCase):
    def test_filtered_rows_no_foreign_bu(self):
        from domain.key_customers import compute_key_customers
        from profit.summary import filter_rows_by_sales

        rows = [
            _row("本BU客", _fen_wan(100), 3, sales="销本"),
            _row("他BU客", _fen_wan(500), 3, sales="销他"),
        ]
        filtered = filter_rows_by_sales(rows, {"销本"})
        out = compute_key_customers(filtered, 2026, COLS, today=datetime.date(2026, 6, 1))
        names = {it["name"] for t in out["tiers"].values() for it in t["items"]}
        self.assertEqual(names, {"本BU客"})
        self.assertNotIn("他BU客", names)


if __name__ == "__main__":
    unittest.main()
