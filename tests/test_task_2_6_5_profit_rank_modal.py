# -*- coding: utf-8 -*-
"""2.6.5 A-1：收入结构「点开展示明细」弹层须有内容（整体 + BU）。

战例（F1）：2.6.1 embed_full=False 后 ProfitStructure 仍只读 full_items → 空弹层。
本文件锁：
1. VM 首包 full_items 空 + others 在 → 必须走 API
2. /api/profit_ranking 整体会话 items>0
3. BU 会话带 bu 参数 items>0；无 bu 仍 401；他 BU 401
4. 前端源码含按需拉取（防再漏）
5. 故意断数据源 → 断言失败（红）再还原（写证据）
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import bu  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import profit  # noqa: E402
import server  # noqa: E402
from viewmodels import packers  # noqa: E402


def _seed_project(cfg, root: Path):
    import money

    conn = db.connect(cfg, root)
    rows = [
        ("P1", "SO1", "客户甲", "线1", "销售A", "2026-03-10", 1060.0, 300.0),
        ("P2", "SO2", "客户甲", "线1", "销售A", "2026-04-10", 1060.0, 200.0),
        ("P3", "SO3", "客户乙", "线2", "销售B", "2026-05-10", 3180.0, 2000.0),
        ("P4", "SO4", "客户丙", "线1", "销售A", "2026-06-10", 2120.0, 400.0),
        ("P5", "SO5", "客户丁", "线2", "销售B", "2026-07-10", 1590.0, 500.0),
    ]
    for k, so, cu, ln, sal, d, rev, cost in rows:
        conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,"
            "归属月,原值_交付日期,原值_归属月,已删除) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
            (k, so, cu, ln, sal, d, money.yuan_to_fen(rev), money.yuan_to_fen(cost), d[:7], d, d[:7]),
        )
    conn.commit()
    conn.close()


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


def _write_accts(cfg, root, rows):
    accounts.save_accounts(cfg, root, rows)


COLS = {"project_delivery_date": "整单交付日期", "project_revenue": "交付额", "project_cost": "项目成本"}


def _modal_items_from_side(side: dict) -> list:
    """复现 2.6.4 漏修逻辑：只读 full_items（会空）。"""
    return list(side.get("full_items") or [])


class TestVmEmbedFullEmpty(unittest.TestCase):
    """VM 契约：embed_full=False 时 others 在、full_items 空 → 弹层不能只读 local。"""

    def test_pack_profit_rank_no_full_when_embed_false(self):
        import datetime as dt

        S, E = dt.date(2026, 1, 1), dt.date(2026, 12, 31)
        # top=1 强制造 others
        rk = profit.compute_profit_ranking(
            [
                {"客户": "客1", "销售": "A", "整单交付日期": "2026-03-01", "交付额": 1060, "项目成本": 100},
                {"客户": "客2", "销售": "B", "整单交付日期": "2026-04-01", "交付额": 2120, "项目成本": 200},
            ],
            "客户",
            COLS,
            S,
            E,
            0.06,
            top=1,
        )
        summary = {
            "periods": {
                "2026年": {
                    "range": ("2026-01-01", "2026-12-31"),
                    "profit_rankings": {
                        "revenue_by_customer": rk,
                        "revenue_by_sales": profit.compute_profit_ranking(
                            [
                                {
                                    "客户": "客1",
                                    "销售": "A",
                                    "整单交付日期": "2026-03-01",
                                    "交付额": 1060,
                                    "项目成本": 100,
                                }
                            ],
                            "销售",
                            COLS,
                            S,
                            E,
                            0.06,
                            top=1,
                        ),
                    },
                }
            }
        }
        packed = packers.pack_profit_rank_by_period(summary, embed_full=False)
        side = packed["2026年"]["customer"]
        self.assertIsNotNone(side.get("others"), "须有「其余」行")
        self.assertEqual(side.get("full_items") or [], [], "embed_full=False 不得下发 full_items")
        # 旧逻辑：弹层 items 必空
        self.assertEqual(_modal_items_from_side(side), [])


class TestProfitRankingApiMainAndBu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp
        cls.cfg = loaders.load_config()
        _seed_project(cls.cfg, cls.root)
        _write_bucfg(
            cls.cfg,
            cls.root,
            [
                {"name": "BU甲", "销售": ["销售A"]},
                {"name": "BU乙", "销售": ["销售B"]},
            ],
        )
        _write_accts(
            cls.cfg,
            cls.root,
            [
                {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
                {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
                {"账号": "user_a", "显示名": "甲负责人", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
                {"账号": "user_b", "显示名": "乙负责人", "权限": "BU乙", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        server._state["user_html"] = "<html>USER</html>"
        server._state["has_data"] = True
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.TC = TestClient

    def _login(self, account: str, pw: str | None = None):
        c = self.TC(self.app, follow_redirects=False)
        r = c.post("/login", data={"account": account, "password": pw or server.DEFAULT_VIEW_PW})
        self.assertIn(r.status_code, (303, 200, 302), r.text[:200])
        return c

    def test_main_modal_items_gt_zero(self):
        """整体会话：点开后 API items 数量 > 0。"""
        c = self._login("overall")
        r = c.get(
            "/api/profit_ranking",
            params={"dim": "customer", "start": "2026-01-01", "end": "2026-12-31", "top": 5000},
        )
        self.assertEqual(r.status_code, 200, r.text[:300])
        items = r.json().get("items") or []
        self.assertGreater(len(items), 0, "整体弹层 items 必须 > 0")
        self.assertIn("revenue_disp", items[0])
        self.assertIn("系统成本率", items[0].get("cost_pct_disp") or "")

    def test_bu_with_param_items_gt_zero(self):
        """BU 会话 + bu= 本 BU：合法路径 items > 0。"""
        c = self._login("user_a")
        # 无 bu → 仍 401（不可放宽为全公司）
        r0 = c.get(
            "/api/profit_ranking",
            params={"dim": "customer", "start": "2026-01-01", "end": "2026-12-31"},
        )
        self.assertEqual(r0.status_code, 403, "BU 无 bu 参数不得看全公司")
        r = c.get(
            "/api/profit_ranking",
            params={
                "dim": "customer",
                "start": "2026-01-01",
                "end": "2026-12-31",
                "top": 5000,
                "bu": "BU甲",
            },
        )
        self.assertEqual(r.status_code, 200, r.text[:300])
        items = r.json().get("items") or []
        self.assertGreater(len(items), 0, "BU 弹层 items 必须 > 0")
        # 只含本 BU 销售相关客户（销售A → 客户甲/客户丙）
        names = {it["name"] for it in items}
        self.assertTrue(names & {"客户甲", "客户丙"}, names)
        self.assertNotIn("客户乙", names)  # 销售B 属 BU乙
        self.assertEqual(r.json().get("bu"), "BU甲")

    def test_bu_cannot_view_other_bu(self):
        c = self._login("user_a")
        r = c.get(
            "/api/profit_ranking",
            params={
                "dim": "customer",
                "start": "2026-01-01",
                "end": "2026-12-31",
                "bu": "BU乙",
            },
        )
        self.assertEqual(r.status_code, 403)  # D-10

    def test_unauth_401(self):
        c = self.TC(self.app, follow_redirects=False)
        r = c.get(
            "/api/profit_ranking",
            params={"dim": "customer", "start": "2026-01-01", "end": "2026-12-31"},
        )
        self.assertEqual(r.status_code, 401)  # 未登录


class TestFrontendHasFetchFallback(unittest.TestCase):
    """源码守卫：ProfitStructure 必须按需拉 /api/profit_ranking（含 bu）。"""

    def test_profit_structure_source(self):
        src = (ROOT / "frontend" / "src" / "components" / "ProfitStructure.vue").read_text(encoding="utf-8")
        self.assertIn("/api/profit_ranking", src)
        self.assertIn("top=5000", src)
        self.assertIn("bu=", src)
        # 不得只剩 local full_items 赋值而无 fetch
        self.assertIn("fetch(", src)
        self.assertNotRegex(
            src,
            r"modalItems\.value\s*=\s*side\.full_items\s*\|\|\s*\[\]\s*\n\s*showMeta",
            "禁止只写 full_items 无兜底的旧逻辑",
        )


class TestRedThenGreenDataSource(unittest.TestCase):
    """故意断数据源 → 弹层 items 断言红 → 还原后绿。过程写证据文件。"""

    def test_broken_source_then_restore(self):
        import datetime as dt
        from fastapi.testclient import TestClient

        scratch = Path(
            "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-c31b43ef0cf9/implementer"
        )
        scratch.mkdir(parents=True, exist_ok=True)
        log = scratch / "a1_modal_red_green.log"
        lines: list[str] = []

        tmp = Path(tempfile.mkdtemp())
        cfg = loaders.load_config()
        _seed_project(cfg, tmp)
        _write_bucfg(cfg, tmp, [{"name": "BU甲", "销售": ["销售A"]}])
        _write_accts(
            cfg,
            tmp,
            [
                {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
                {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        server._state["user_html"] = "<html>USER</html>"
        app = server.create_app(cfg, root=tmp)
        c = TestClient(app, follow_redirects=False)
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})

        # --- 故意断：清空 std_收入明细 ---
        conn = db.connect(cfg, tmp)
        conn.execute("DELETE FROM std_收入明细")
        conn.commit()
        conn.close()
        r_broken = c.get(
            "/api/profit_ranking",
            params={"dim": "customer", "start": "2026-01-01", "end": "2026-12-31", "top": 5000},
        )
        items_broken = (r_broken.json() or {}).get("items") or []
        lines.append(f"BROKEN status={r_broken.status_code} items_len={len(items_broken)}")
        try:
            self.assertGreater(len(items_broken), 0, "expect RED when data wiped")
            red_caught = False
        except AssertionError as e:
            red_caught = True
            lines.append(f"RED_OK: {e}")
        self.assertTrue(red_caught, "断数据源后断言必须失败（证明会红）")

        # --- 还原 ---
        _seed_project(cfg, tmp)
        r_ok = c.get(
            "/api/profit_ranking",
            params={"dim": "customer", "start": "2026-01-01", "end": "2026-12-31", "top": 5000},
        )
        items_ok = (r_ok.json() or {}).get("items") or []
        lines.append(f"RESTORED status={r_ok.status_code} items_len={len(items_ok)}")
        self.assertEqual(r_ok.status_code, 200)
        self.assertGreater(len(items_ok), 0, "还原后弹层 items 必须 > 0")
        lines.append("GREEN_OK")
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestA2ScanEmbedFullConsumers(unittest.TestCase):
    """A-2：全仓扫 embed_full=False 后仍读 full_items 的前端点。"""

    def test_frontend_full_items_consumers_have_fallback(self):
        fe = ROOT / "frontend" / "src" / "components"
        offenders = []
        for p in fe.glob("*.vue"):
            text = p.read_text(encoding="utf-8")
            if "full_items" not in text:
                continue
            # 有 full_items 读取 → 须有 fetch 兜底或明确 embed 分支
            if "fetch(" not in text and "full_items" in text:
                # SciFi 等无关文件
                if "full_items" in text and ("openOthers" in text or "modalItems" in text):
                    offenders.append(p.name)
        self.assertEqual(
            offenders,
            [],
            f"以下组件读 full_items 却无 fetch 兜底（空弹层风险）: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
