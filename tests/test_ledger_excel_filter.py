#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看端费用明细 Excel 式多选筛选：filters.in 真路径 + /api/v1/vm/ledger/values + UI 结构。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import support  # noqa: E402,F401

import accounts
import db
import loaders
import server


class TestLedgerInFilterDb(unittest.TestCase):
    """db.query_detail 真路径：in 多选只返回匹配行。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = loaders.load_config(ROOT)
        self.cfg = dict(cfg)
        self.cfg["data_dir"] = str(self.tmp / "数据")
        (self.tmp / "数据").mkdir(parents=True)
        self.conn = db.connect(self.cfg, self.tmp)
        self.addCleanup(self.conn.close)
        import db_write

        db_write.insert_std_records(
            self.conn,
            "std_费用明细",
            [
                {
                    "定位键": "xf-1",
                    "收单月份": "2026-06",
                    "收单日期": "2026-06-01",
                    "含税金额": 10.0,
                    "业务BU": "数据",
                    "对应报表大类": "管理费用",
                    "预算明细费用类型": "办公费",
                    "预算归属部门": "财务",
                    "事项": "甲事项",
                    "业务员": "张三",
                    "归属月": "2026-06",
                    "原值_归属月": "2026-06",
                },
                {
                    "定位键": "xf-2",
                    "收单月份": "2026-06",
                    "收单日期": "2026-06-02",
                    "含税金额": 20.0,
                    "业务BU": "数据",
                    "对应报表大类": "销售费用",
                    "预算明细费用类型": "差旅费",
                    "预算归属部门": "销售",
                    "事项": "乙事项",
                    "业务员": "李四",
                    "归属月": "2026-06",
                    "原值_归属月": "2026-06",
                },
                {
                    "定位键": "xf-3",
                    "收单月份": "2026-06",
                    "收单日期": "2026-06-03",
                    "含税金额": 30.0,
                    "业务BU": "数据",
                    "对应报表大类": "管理费用",
                    "预算明细费用类型": "办公费",
                    "预算归属部门": "财务",
                    "事项": "丙事项",
                    "业务员": "张三",
                    "归属月": "2026-06",
                    "原值_归属月": "2026-06",
                },
            ],
        )
        self.conn.commit()

    def test_in_filter_matches_only_selected(self):
        d = db.query_detail(
            self.conn,
            "费用明细",
            filters={"业务员": {"in": ["张三"]}},
            page_size=50,
            audience="view",
        )
        self.assertEqual(d["total"], 2)
        names = {str(r.get("业务员")) for r in d["rows"]}
        self.assertEqual(names, {"张三"})

    def test_in_multi_and_clear(self):
        d = db.query_detail(
            self.conn,
            "费用明细",
            filters={"对应报表大类": {"in": ["管理费用", "销售费用"]}},
            page_size=50,
            audience="view",
        )
        self.assertEqual(d["total"], 3)
        d0 = db.query_detail(self.conn, "费用明细", filters={}, page_size=50, audience="view")
        self.assertEqual(d0["total"], 3)

    def test_distinct_lists_column_values(self):
        d = db.query_detail_distinct(
            self.conn,
            "费用明细",
            "业务员",
            audience="view",
            limit=50,
        )
        vals = set(d.get("values") or [])
        self.assertIn("张三", vals)
        self.assertIn("李四", vals)

    def test_distinct_excludes_self_in_but_keeps_other_filters(self):
        d = db.query_detail_distinct(
            self.conn,
            "费用明细",
            "业务员",
            filters={"业务员": {"in": ["张三"]}, "对应报表大类": {"in": ["管理费用"]}},
            audience="view",
        )
        # 本列 in 被排除，管理费用下应有张三（两条里业务员都是张三）+ 无李四
        vals = set(d.get("values") or [])
        self.assertIn("张三", vals)
        self.assertNotIn("李四", vals)

    def test_in_empty_string_matches_null_or_blank(self):
        """勾选 (空)：in 含 '' 须命中空/NULL 行。"""
        import db_write

        db_write.insert_std_records(
            self.conn,
            "std_费用明细",
            [
                {
                    "定位键": "xf-empty",
                    "收单月份": "2026-06",
                    "收单日期": "2026-06-04",
                    "含税金额": 1.0,
                    "业务BU": "数据",
                    "对应报表大类": "管理费用",
                    "预算明细费用类型": "办公费",
                    "预算归属部门": "财务",
                    "事项": "空业务员行",
                    "业务员": "",
                    "归属月": "2026-06",
                    "原值_归属月": "2026-06",
                },
            ],
        )
        self.conn.commit()
        d = db.query_detail(
            self.conn,
            "费用明细",
            filters={"业务员": {"in": [""]}},
            page_size=50,
            audience="view",
        )
        self.assertGreaterEqual(d["total"], 1)
        for r in d["rows"]:
            self.assertEqual(str(r.get("业务员") or ""), "")

    def test_in_empty_plus_named(self):
        """(空)+张三：两行都要，不能因 strip 空串而丢掉空。"""
        import db_write

        db_write.insert_std_records(
            self.conn,
            "std_费用明细",
            [
                {
                    "定位键": "xf-e2",
                    "收单月份": "2026-06",
                    "收单日期": "2026-06-05",
                    "含税金额": 2.0,
                    "业务BU": "数据",
                    "对应报表大类": "管理费用",
                    "预算明细费用类型": "办公费",
                    "预算归属部门": "财务",
                    "事项": "空2",
                    "业务员": None,
                    "归属月": "2026-06",
                    "原值_归属月": "2026-06",
                },
            ],
        )
        self.conn.commit()
        d = db.query_detail(
            self.conn,
            "费用明细",
            filters={"业务员": {"in": ["", "张三"]}},
            page_size=50,
            audience="view",
        )
        names = {str(r.get("业务员") or "") for r in d["rows"]}
        self.assertIn("", names)
        self.assertIn("张三", names)
        self.assertNotIn("李四", names)

    def test_number_col_in_via_cast_text(self):
        """金额列 in 走 CAST 文本 IN（分串），不得静默忽略。"""
        fen = self.conn.execute(
            "SELECT 含税金额 FROM std_费用明细 WHERE 定位键='xf-1'"
        ).fetchone()[0]
        d = db.query_detail(
            self.conn,
            "费用明细",
            filters={"含税金额": {"in": [str(fen)]}},
            page_size=50,
            audience="view",
        )
        self.assertEqual(d["total"], 1)
        self.assertIn("甲事项", str(d["rows"]))

    def test_number_col_q_keyword_like_narrows(self):
        """金额列 filters.q 必须 CAST LIKE 收窄，不得只亮筛却全量。"""
        d_all = db.query_detail(self.conn, "费用明细", page_size=50, audience="view")
        self.assertGreaterEqual(d_all["total"], 2)
        fen = self.conn.execute(
            "SELECT 含税金额 FROM std_费用明细 WHERE 定位键='xf-1'"
        ).fetchone()[0]
        # 库内分值全文 LIKE（xf-1=1000 分，xf-2=2000，xf-3=3000 → "1000" 仅命中一行）
        d = db.query_detail(
            self.conn,
            "费用明细",
            filters={"含税金额": {"q": str(fen)}},
            page_size=50,
            audience="view",
        )
        self.assertEqual(d["total"], 1, msg=f"q={fen!r} 应收窄到 1 行，得 {d['total']}（全量 {d_all['total']}）")
        self.assertIn("甲事项", str(d["rows"]))
        self.assertNotIn("乙事项", str(d["rows"]))

    def test_date_col_q_keyword_like_narrows(self):
        """日期列 q 亦走 CAST LIKE。"""
        d = db.query_detail(
            self.conn,
            "费用明细",
            filters={"收单日期": {"q": "2026-06-01"}},
            page_size=50,
            audience="view",
        )
        self.assertEqual(d["total"], 1)
        self.assertIn("甲事项", str(d["rows"]))


class TestLedgerValuesHttp(unittest.TestCase):
    """GET /api/v1/vm/ledger/values + filters.in 列表。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = loaders.load_config(ROOT)
        self.cfg = dict(cfg)
        self.cfg["data_dir"] = str(self.tmp / "数据")
        (self.tmp / "数据").mkdir(parents=True)
        accounts.seed_defaults(self.cfg, self.tmp)
        conn = db.connect(self.cfg, self.tmp)
        try:
            import db_write

            db_write.insert_std_records(
                conn,
                "std_费用明细",
                [
                    {
                        "定位键": "api-xf-1",
                        "收单月份": "2026-06",
                        "收单日期": "2026-06-05",
                        "含税金额": 11.0,
                        "业务BU": "数据",
                        "对应报表大类": "管理费用",
                        "预算明细费用类型": "办公费",
                        "预算归属部门": "财务",
                        "事项": "事项A",
                        "业务员": "王五",
                        "归属月": "2026-06",
                        "原值_归属月": "2026-06",
                    },
                    {
                        "定位键": "api-xf-2",
                        "收单月份": "2026-06",
                        "收单日期": "2026-06-08",
                        "含税金额": 22.0,
                        "业务BU": "数据",
                        "对应报表大类": "销售费用",
                        "预算明细费用类型": "差旅费",
                        "预算归属部门": "销售",
                        "事项": "事项B",
                        "业务员": "赵六",
                        "归属月": "2026-06",
                        "原值_归属月": "2026-06",
                    },
                ],
            )
            conn.commit()
        finally:
            conn.close()
        self.app = server.create_app(self.cfg, self.tmp)
        from fastapi.testclient import TestClient

        self.client = TestClient(self.app)

    def _login(self):
        r = self.client.post(
            "/api/v1/login",
            json={"account": accounts.MASTER_ACCOUNT, "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertEqual(r.status_code, 200, r.text[:300])
        return self.client

    def test_values_endpoint_returns_distinct(self):
        c = self._login()
        r = c.get(
            "/api/v1/vm/ledger/values",
            params={
                "column": "业务员",
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "show_all": 1,
            },
        )
        self.assertEqual(r.status_code, 200, r.text[:400])
        body = r.json()
        vals = set(body.get("values") or [])
        self.assertIn("王五", vals)
        self.assertIn("赵六", vals)

    def test_ledger_list_with_in_filter(self):
        c = self._login()
        filt = json.dumps({"业务员": {"in": ["王五"]}}, ensure_ascii=False)
        r = c.get(
            "/api/v1/vm/ledger",
            params={
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "show_all": 1,
                "filters": filt,
                "page_size": 50,
            },
        )
        self.assertEqual(r.status_code, 200, r.text[:400])
        data = r.json()
        self.assertEqual(data["total"], 1)
        self.assertIn("王五", str(data.get("rows")))
        self.assertNotIn("赵六", str(data.get("rows")))


class TestLedgerTableUiStructure(unittest.TestCase):
    """看端 LedgerTable：多选漏斗 + values API，禁止只剩盲输。"""

    def test_component_has_excel_style_multiselect(self):
        p = ROOT / "frontend" / "src" / "components" / "LedgerTable.vue"
        t = p.read_text(encoding="utf-8")
        self.assertIn("/api/v1/vm/ledger/values", t)
        self.assertIn("ledger-col-option-list", t)
        self.assertIn("ledger-col-option-cb", t)
        self.assertIn('type="checkbox"', t)
        self.assertIn("colIns", t)
        self.assertIn("isTextCol", t)
        self.assertIn("column_meta", t)
        # 空串须保留进 in（不得 filter 掉 ''）
        self.assertNotIn(".filter((x) => x !== '')", t)
        self.assertNotIn('.filter((x) => x !== "")', t)
        # text 才拉 values；number/date 走关键词
        self.assertIn("isTextCol(c)", t)
        self.assertIn("ledger-col-q", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
