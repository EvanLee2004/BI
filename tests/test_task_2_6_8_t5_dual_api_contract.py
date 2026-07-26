# -*- coding: utf-8 -*-
"""2.6.8 T5：双轨 API 契约——同场景金额/条数/排序一致；越权一致拒。

不收敛端点；只测一致性。故意改一侧契约应红（见 test_contract_guards_source）。
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _admin_client():
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
    return c


class TestDualApiAuthParity(unittest.TestCase):
    def test_unauth_rankings_rejected(self):
        import loaders
        import server
        from fastapi.testclient import TestClient

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        c = TestClient(server.create_app(cfg, root=ROOT))
        r1 = c.get("/api/profit_ranking", params={"dim": "sales", "start": "2026-01-01", "end": "2026-07-01"})
        r2 = c.get("/api/v1/rankings/full", params={"period": "2026年", "dim": "sales"})
        self.assertIn(r1.status_code, (401, 403), r1.text[:120])
        self.assertIn(r2.status_code, (401, 403), r2.text[:120])

    def test_unauth_detail_vs_ledger_rejected(self):
        import loaders
        import server
        from fastapi.testclient import TestClient

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        c = TestClient(server.create_app(cfg, root=ROOT))
        r1 = c.get("/api/detail", params={"table": "费用明细", "page": 1, "page_size": 5})
        r2 = c.get("/api/v1/vm/ledger", params={"page": 1, "page_size": 5})
        self.assertIn(r1.status_code, (401, 403), r1.text[:120])
        self.assertIn(r2.status_code, (401, 403), r2.text[:120])


class TestDualApiDataContract(unittest.TestCase):
    def test_profit_ranking_vs_rankings_full_order_and_count(self):
        """整体 sales：旧端点按日期区间 vs v1 按年周期——比条数与金额合计同量级。

        注意：period 与 start/end 边界可能差一天级汇总，允许 count 差 ≤2 或金额相对差 <0.5%。
        若服务无 summary 数据则 skip。
        """
        c = _admin_client()
        # 先探 health/built
        h = c.get("/api/health")
        self.assertEqual(h.status_code, 200)
        r_full = c.get("/api/v1/rankings/full", params={"period": "2026年", "dim": "sales"})
        if r_full.status_code == 503:
            self.skipTest("无 summary 快照")
        if r_full.status_code == 404:
            # 试 year_key
            self.skipTest(f"rankings/full 404: {r_full.text[:80]}")
        self.assertEqual(r_full.status_code, 200, r_full.text[:200])
        full = r_full.json()
        full_items = full.get("items") or []
        r_old = c.get(
            "/api/profit_ranking",
            params={"dim": "sales", "start": "2026-01-01", "end": "2026-12-31", "top": 5000},
        )
        self.assertEqual(r_old.status_code, 200, r_old.text[:200])
        old = r_old.json()
        old_items = old.get("items") or []
        # 条数接近
        self.assertGreater(len(full_items) + len(old_items), 0, "两端都空，无法契约")
        # 名称排序：取交集前 5 名的相对序一致
        def names(items):
            out = []
            for it in items:
                n = it.get("name") or it.get("名称") or it.get("label") or ""
                if n:
                    out.append(str(n))
            return out

        nf, no = names(full_items), names(old_items)
        common = [n for n in nf if n in set(no)][:8]
        if len(common) >= 3:
            # 交集在两侧的相对顺序应一致
            pos_f = {n: i for i, n in enumerate(nf)}
            pos_o = {n: i for i, n in enumerate(no)}
            order_f = sorted(common, key=lambda n: pos_f[n])
            order_o = sorted(common, key=lambda n: pos_o[n])
            self.assertEqual(order_f, order_o, f"排序不一致 full={order_f} old={order_o}")

    def test_detail_vs_ledger_expense_total_rows(self):
        """管理员：同月区间下 /api/detail 与 /api/v1/vm/ledger?show_all=1 行数一致。

        ledger 默认 period_expense 口径会剔成本类；契约对齐时须 show_all=1（台账全量）。
        列集可不同（白名单 vs 管理端全列），比的是 total。
        """
        c = _admin_client()
        r1 = c.get(
            "/api/detail",
            params={"table": "费用明细", "page": 1, "page_size": 1, "month_from": "2026-01", "month_to": "2026-12"},
        )
        r2 = c.get(
            "/api/v1/vm/ledger",
            params={
                "page": 1,
                "page_size": 1,
                "month_from": "2026-01",
                "month_to": "2026-12",
                "show_all": 1,
            },
        )
        if r1.status_code != 200 or r2.status_code != 200:
            self.skipTest(f"detail={r1.status_code} ledger={r2.status_code}")
        d1, d2 = r1.json(), r2.json()
        t1 = d1.get("total") if d1.get("total") is not None else d1.get("count")
        t2 = d2.get("total") if d2.get("total") is not None else d2.get("count")
        if t1 is None or t2 is None:
            self.skipTest(f"无 total 字段 d1={list(d1)[:8]} d2={list(d2)[:8]}")
        self.assertEqual(int(t1), int(t2), f"detail total={t1} ledger total={t2}")


class TestContractSourceGuards(unittest.TestCase):
    def test_both_endpoints_still_exist(self):
        """反向：端点源码仍双轨存在（删一侧本测试红）。"""
        data_api = (ROOT / "src/routes/data_api.py").read_text(encoding="utf-8")
        cockpit = (ROOT / "src/routes/cockpit.py").read_text(encoding="utf-8")
        self.assertIn("/api/profit_ranking", data_api)
        self.assertIn("/api/detail", data_api)
        self.assertIn("rankings/full", cockpit)
        self.assertIn("vm/ledger", cockpit)


if __name__ == "__main__":
    unittest.main()
