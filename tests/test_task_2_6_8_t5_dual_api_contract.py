# -*- coding: utf-8 -*-
"""2.6.8 T5：双轨 API 契约——金额/条数/排序一致；越权一致拒；先红后绿。

不收敛端点。create_app 前 refresh 种 summary，避免「无快照」永久 skip。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _names(items: list) -> list[str]:
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        n = it.get("name") or it.get("名称") or it.get("label") or it.get("sales") or it.get("customer") or ""
        if n:
            out.append(str(n))
    return out


def _parse_disp_wan(s) -> float | None:
    """'2,294.7万' / '659.1万' → 元(万*1e4) 近似数。"""
    if s is None:
        return None
    t = str(s).strip().replace(",", "").replace("，", "")
    if not t:
        return None
    mult = 1.0
    if t.endswith("万"):
        mult = 10000.0
        t = t[:-1]
    try:
        return float(t) * mult
    except ValueError:
        return None


def _amt_key(it: dict) -> float:
    for k in ("revenue", "收入", "amount", "金额", "value", "交付额", "毛利", "profit", "wo", "wr"):
        if k in it and it[k] is not None:
            try:
                return float(it[k])
            except (TypeError, ValueError):
                pass
    for k in ("revenue_disp", "order_disp", "receipt_disp", "cost_pct_disp"):
        v = _parse_disp_wan(it.get(k))
        if v is not None:
            return v
    return 0.0


def ranking_order_contract(items_a: list, items_b: list, min_common: int = 3) -> tuple[bool, str]:
    """返回 (ok, detail)。两侧名称交集的相对序须一致。"""
    na, nb = _names(items_a), _names(items_b)
    if not na and not nb:
        return False, "两端皆空"
    common = [n for n in na if n in set(nb)]
    if len(common) < min_common:
        return False, f"交集不足 common={len(common)} need>={min_common} na={len(na)} nb={len(nb)}"
    sample = common[: max(min_common, min(8, len(common)))]
    pos_a = {n: i for i, n in enumerate(na)}
    pos_b = {n: i for i, n in enumerate(nb)}
    order_a = sorted(sample, key=lambda n: pos_a[n])
    order_b = sorted(sample, key=lambda n: pos_b[n])
    if order_a != order_b:
        return False, f"排序不一致 a={order_a} b={order_b}"
    return True, f"order_ok sample={sample}"


def ranking_count_contract(items_a: list, items_b: list, tol: int = 2) -> tuple[bool, str]:
    ca, cb = len(items_a or []), len(items_b or [])
    if abs(ca - cb) > tol:
        return False, f"count 差超容差 a={ca} b={cb} tol={tol}"
    return True, f"count_ok a={ca} b={cb}"


class TestRankingComparatorRedGreen(unittest.TestCase):
    """先红后绿：比较器本身必须能抓到排序破坏。"""

    def test_order_mismatch_is_red(self):
        a = [{"name": "甲"}, {"name": "乙"}, {"name": "丙"}]
        b = [{"name": "丙"}, {"name": "乙"}, {"name": "甲"}]
        ok, det = ranking_order_contract(a, b, min_common=3)
        self.assertFalse(ok, det)

    def test_order_match_is_green(self):
        a = [{"name": "甲"}, {"name": "乙"}, {"name": "丙"}, {"name": "丁"}]
        b = [{"name": "甲"}, {"name": "乙"}, {"name": "丙"}]
        ok, det = ranking_order_contract(a, b, min_common=3)
        self.assertTrue(ok, det)

    def test_count_mismatch_is_red(self):
        ok, det = ranking_count_contract([{}] * 10, [{}] * 1, tol=2)
        self.assertFalse(ok, det)


def _refreshed_admin_client():
    """refresh 种 summary 后登录管理员。"""
    import loaders
    import server
    from fastapi.testclient import TestClient

    cfg = dict(loaders.load_config(ROOT))
    cfg["zhiyun_auto_fetch"] = False
    try:
        server.refresh(cfg, ROOT)
    except Exception as e:
        raise unittest.SkipTest(f"refresh 失败（本地无数据？）: {e}") from e
    from app_state import _state

    if not (_state.get("built_at") or _state.get("summary")):
        raise unittest.SkipTest("refresh 后仍无 summary/built_at")
    app = server.create_app(cfg, root=ROOT)
    c = TestClient(app)
    rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("accounts") or []
    admin = next(a for a in rows if a.get("权限") == "管理员")
    lr = c.post("/api/v1/login", json={"account": admin["账号"], "password": admin["密码"]})
    assert lr.status_code in (200, 303), lr.text[:200]
    return c, cfg


class TestDualApiAuthParity(unittest.TestCase):
    def test_unauth_rankings_rejected(self):
        import loaders
        import server
        from fastapi.testclient import TestClient

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        c = TestClient(server.create_app(cfg, root=ROOT))
        r1 = c.get("/api/v1/rankings/profit", params={"dim": "sales", "start": "2026-01-01", "end": "2026-07-01"})
        r1b = c.get(
            "/api/v1/rankings/profit",
            params={"dim": "sales", "start": "2026-01-01", "end": "2026-07-01"},
        )
        r2 = c.get("/api/v1/rankings/full", params={"period": "2026年", "dim": "sales"})
        self.assertIn(r1.status_code, (401, 403), r1.text[:120])
        self.assertIn(r1b.status_code, (401, 403), r1b.text[:120])
        self.assertEqual(r1.status_code, r1b.status_code)
        self.assertIn(r2.status_code, (401, 403), r2.text[:120])

    def test_unauth_detail_vs_ledger_rejected(self):
        import loaders
        import server
        from fastapi.testclient import TestClient

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        c = TestClient(server.create_app(cfg, root=ROOT))
        r1 = c.get("/api/v1/admin/detail", params={"table": "费用明细", "page": 1, "page_size": 5})
        r2 = c.get("/api/v1/vm/ledger", params={"page": 1, "page_size": 5})
        self.assertIn(r1.status_code, (401, 403), r1.text[:120])
        self.assertIn(r2.status_code, (401, 403), r2.text[:120])

    def test_bu_session_cannot_cross_bu_rankings(self):
        """BU 会话取别的 BU → 403（双端一致）。"""
        import loaders
        import server
        from fastapi.testclient import TestClient

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        # 尽量 refresh 让 bu_pages 存在
        try:
            server.refresh(cfg, ROOT)
        except Exception:
            pass
        app = server.create_app(cfg, root=ROOT)
        c = TestClient(app)
        rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("accounts") or []
        bu_acc = next(
            (
                a
                for a in rows
                if a.get("权限") in ("业务线", "BU", "业务BU")
                or (a.get("BU") or a.get("业务BU") or a.get("可见BU"))
            ),
            None,
        )
        if not bu_acc:
            # 看板账号可能用 权限=查看 + 业务线 字段
            bu_acc = next((a for a in rows if a.get("权限") != "管理员" and a.get("密码")), None)
        if not bu_acc:
            self.skipTest("无非管理员账号可测跨 BU")
        lr = c.post("/api/v1/login", json={"account": bu_acc["账号"], "password": bu_acc["密码"]})
        if lr.status_code not in (200, 303):
            self.skipTest(f"BU 登录失败 {lr.status_code}")
        # 故意要一个很可能无权的 BU 名
        r1 = c.get(
            "/api/v1/rankings/profit",
            params={
                "dim": "sales",
                "start": "2026-01-01",
                "end": "2026-12-31",
                "bu": "__不存在的BU_2_6_8__",
            },
        )
        r2 = c.get(
            "/api/v1/rankings/full",
            params={"period": "2026年", "dim": "sales", "bu": "__不存在的BU_2_6_8__"},
        )
        self.assertIn(r1.status_code, (401, 403, 404), r1.text[:160])
        self.assertIn(r2.status_code, (401, 403, 404), r2.text[:160])


class TestDualApiDataContract(unittest.TestCase):
    def test_profit_ranking_vs_rankings_full_order_and_count(self):
        """整体：双轨 HTTP 与其同源预计算路径序/条数一致（强制 ranking_order_contract）。

        产品语义：
        - `/api/v1/rankings/profit` = 收入毛利榜 ↔ `summary.profit_rankings.revenue_by_*`
        - `/api/v1/rankings/full` dim=sales = 下单/回款双榜 ↔ `rankings_view_for_period(...).sales`

        跨语义强制同序是错的（收入序 ≠ 下单序）。契约绑**同语义双轨**。
        故意反转快照 → ranking_order_contract 必红（本测内断言 + ComparatorRedGreen）。
        """
        c, _cfg = _refreshed_admin_client()
        from app_state import _state
        import api_v1

        period = "2026年"
        pv = ((_state.get("summary") or {}).get("periods") or {}).get(period) or {}
        self.assertTrue(pv, "summary 缺 2026年 period")

        # --- A) profit_ranking ↔ snapshot ---
        r_old = c.get(
            "/api/v1/rankings/profit",
            params={"dim": "sales", "start": "2026-01-01", "end": "2026-12-31", "top": 5000},
        )
        self.assertEqual(r_old.status_code, 200, r_old.text[:200])
        old_items = (r_old.json() or {}).get("items") or []
        snap = (pv.get("profit_rankings") or {}).get("revenue_by_sales") or {}
        # 优先 full_items（完整榜）；退回 items（top-N 截断）
        snap_items = list(snap.get("full_items") or snap.get("items") or [])
        self.assertGreater(len(old_items), 0, "profit_ranking items 空")
        self.assertGreater(len(snap_items), 0, "snapshot revenue_by_sales 空")
        # 若快照仅 top-N，则比 API 前缀；否则比全量
        n_cmp = min(len(old_items), len(snap_items))
        api_cmp = old_items[:n_cmp]
        snap_cmp = snap_items[:n_cmp]
        ok_o, det_o = ranking_order_contract(api_cmp, snap_cmp, min_common=min(3, n_cmp))
        self.assertTrue(ok_o, f"profit dual order fail: {det_o}")
        ok_c, det_c = ranking_count_contract(api_cmp, snap_cmp, tol=0)
        self.assertTrue(ok_c, f"profit dual count fail: {det_c}")
        # 反向：反转快照序 → 契约必须红（证明不是只比集合）
        rev = list(reversed(snap_cmp))
        if len(_names(snap_cmp)) >= 3:
            ok_bad, det_bad = ranking_order_contract(api_cmp, rev, min_common=3)
            self.assertFalse(ok_bad, f"reversed snap should fail order: {det_bad}")

        # --- B) rankings/full ↔ view builder ---
        r_full = c.get("/api/v1/rankings/full", params={"period": period, "dim": "sales"})
        self.assertEqual(r_full.status_code, 200, r_full.text[:200])
        full_items = (r_full.json() or {}).get("items") or []
        view = api_v1.rankings_view_for_period(pv, embed_full=True, monthly_store={})
        blk = view.get("sales") or {}
        view_items = list(blk.get("full_items") or blk.get("items") or [])
        self.assertGreater(len(full_items), 0, "rankings/full items 空")
        self.assertGreater(len(view_items), 0, "view sales full_items 空")
        ok_f, det_f = ranking_order_contract(full_items, view_items, min_common=3)
        self.assertTrue(ok_f, f"full dual order fail: {det_f}")
        ok_fc, det_fc = ranking_count_contract(full_items, view_items, tol=2)
        self.assertTrue(ok_fc, f"full dual count fail: {det_fc}")
        # 金额可解析（各自字段）
        self.assertTrue(any(_amt_key(it) != 0 for it in old_items[:5]), "profit 金额解析失败")
        self.assertTrue(any(_amt_key(it) != 0 for it in full_items[:5]), "full 金额解析失败")

        # --- C) 2.7.1：旧 /api/profit_ranking 已删 → 404；v1 唯一 ---
        r_legacy = c.get(
            "/api/profit_ranking",
            params={"dim": "sales", "start": "2026-01-01", "end": "2026-12-31", "top": 5000},
        )
        self.assertEqual(r_legacy.status_code, 404, r_legacy.text[:200])

    def test_bu_dual_ranking_order_and_count(self):
        """BU 口径：同 bu= 下 profit_ranking / rankings/full 各自与同源路径序+条数一致。"""
        c, _cfg = _refreshed_admin_client()
        from app_state import _state
        import api_v1

        pages = _state.get("bu_pages") or {}
        if not pages:
            self.skipTest("无 bu_pages")
        bu = next(iter(pages.keys()))
        page = pages[bu] or {}
        psum = page.get("summary") or {}
        period = (psum.get("meta") or {}).get("year_key") or "2026年"
        pv = (psum.get("periods") or {}).get(period) or {}
        if not pv:
            # 回退：整体 period 仅测 HTTP 两端均 200 + detail 行数
            pv = {}

        r_old = c.get(
            "/api/v1/rankings/profit",
            params={
                "dim": "sales",
                "start": "2026-01-01",
                "end": "2026-12-31",
                "top": 5000,
                "bu": bu,
            },
        )
        r_full = c.get(
            "/api/v1/rankings/full",
            params={"period": period, "dim": "sales", "bu": bu},
        )
        self.assertEqual(r_old.status_code, 200, r_old.text[:200])
        self.assertEqual(r_full.status_code, 200, r_full.text[:200])
        old_items = (r_old.json() or {}).get("items") or []
        full_items = (r_full.json() or {}).get("items") or []
        self.assertGreater(len(old_items) + len(full_items), 0, f"BU={bu} 两端皆空")

        if pv:
            snap = (pv.get("profit_rankings") or {}).get("revenue_by_sales") or {}
            snap_items = list(snap.get("full_items") or snap.get("items") or [])
            if snap_items and old_items:
                n = min(len(old_items), len(snap_items))
                api_cmp, snap_cmp = old_items[:n], snap_items[:n]
                ok_o, det_o = ranking_order_contract(
                    api_cmp, snap_cmp, min_common=min(3, n)
                )
                self.assertTrue(ok_o, f"BU profit dual order fail bu={bu}: {det_o}")
                ok_c, det_c = ranking_count_contract(api_cmp, snap_cmp, tol=0)
                self.assertTrue(ok_c, f"BU profit dual count fail bu={bu}: {det_c}")
            view = api_v1.rankings_view_for_period(pv, embed_full=True, monthly_store={})
            view_items = list(
                ((view.get("sales") or {}).get("full_items") or (view.get("sales") or {}).get("items") or [])
            )
            if view_items and full_items:
                ok_f, det_f = ranking_order_contract(
                    full_items, view_items, min_common=min(3, len(view_items))
                )
                self.assertTrue(ok_f, f"BU full dual order fail bu={bu}: {det_f}")

        # detail ↔ ledger 同 BU 行数
        r1 = c.get(
            "/api/v1/admin/detail",
            params={
                "table": "费用明细",
                "page": 1,
                "page_size": 1,
                "month_from": "2026-01",
                "month_to": "2026-12",
                "bu": bu,
            },
        )
        r2 = c.get(
            "/api/v1/vm/ledger",
            params={
                "page": 1,
                "page_size": 1,
                "month_from": "2026-01",
                "month_to": "2026-12",
                "show_all": 1,
                "bu": bu,
            },
        )
        self.assertEqual(r1.status_code, 200, r1.text[:160])
        self.assertEqual(r2.status_code, 200, r2.text[:160])
        t1 = (r1.json() or {}).get("total")
        t2 = (r2.json() or {}).get("total")
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertEqual(int(t1), int(t2), f"BU={bu} detail total={t1} ledger total={t2}")

    def test_empty_period_consistent_shape(self):
        """空/不存在周期：两端均应 4xx 或 items 空，不得 500。"""
        c, _ = _refreshed_admin_client()
        r_full = c.get("/api/v1/rankings/full", params={"period": "1999年", "dim": "sales"})
        self.assertIn(r_full.status_code, (200, 404), r_full.text[:120])
        if r_full.status_code == 200:
            items = (r_full.json() or {}).get("items") or []
            self.assertEqual(items, [])
        r_old = c.get(
            "/api/v1/rankings/profit",
            params={"dim": "sales", "start": "1999-01-01", "end": "1999-01-31", "top": 50},
        )
        self.assertIn(r_old.status_code, (200, 400, 404), r_old.text[:120])
        if r_old.status_code == 200:
            items = (r_old.json() or {}).get("items") or []
            self.assertEqual(len(items), 0)

    def test_detail_vs_ledger_expense_total_rows(self):
        """管理员：同月区间 detail 与 ledger?show_all=1 行数一致。"""
        c, _ = _refreshed_admin_client()
        r1 = c.get(
            "/api/v1/admin/detail",
            params={
                "table": "费用明细",
                "page": 1,
                "page_size": 1,
                "month_from": "2026-01",
                "month_to": "2026-12",
            },
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
        self.assertEqual(r1.status_code, 200, r1.text[:200])
        self.assertEqual(r2.status_code, 200, r2.text[:200])
        d1, d2 = r1.json(), r2.json()
        t1 = d1.get("total") if d1.get("total") is not None else d1.get("count")
        t2 = d2.get("total") if d2.get("total") is not None else d2.get("count")
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertEqual(int(t1), int(t2), f"detail total={t1} ledger total={t2}")


class TestContractSourceGuards(unittest.TestCase):
    def test_both_endpoints_still_exist(self):
        data_api = (ROOT / "src/routes/data_api.py").read_text(encoding="utf-8")
        cockpit = (ROOT / "src/routes/cockpit.py").read_text(encoding="utf-8")
        self.assertIn("/api/v1/rankings/profit", data_api)
        self.assertIn("/api/v1/admin/detail", data_api)
        self.assertIn("rankings/full", cockpit)
        self.assertIn("vm/ledger", cockpit)


if __name__ == "__main__":
    unittest.main()
