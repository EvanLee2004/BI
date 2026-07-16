#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书37·B8：整体页费用明细 + 工资默隐 + 设置开关 + BU 隔离。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import bu as bu_mod  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import server  # noqa: E402


class TestOverallExpenseSalary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.root = Path(tempfile.mkdtemp())
        (cls.root / "数据").mkdir()
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "数据/看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        # 默认关工资
        cls.cfg.pop("overall_see_salary", None)
        accounts.save_accounts(
            cls.cfg,
            cls.root,
            [
                {"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"},
                {"账号": "all", "密码": "8888", "权限": "整体", "显示名": "姜总"},
                {"账号": "bu_a", "密码": "8888", "权限": "BU", "可见BU": ["甲BU"], "显示名": "甲"},
            ],
        )
        bu_mod.save_bu_config(
            cls.cfg,
            cls.root,
            [
                {"name": "甲BU", "负责人": [], "销售": ["销A"]},
                {"name": "乙BU", "负责人": [], "销售": ["销B"]},
            ],
        )
        conn = db.connect(cls.cfg, cls.root)
        samples = [
            ("s1", "甲BU", "工资", 1000.0, "工资事项"),
            ("s2", "甲BU", "管理费用", 200.0, "办公"),
            ("s3", "乙BU", "工资", 3000.0, "乙工资"),
            ("s4", "乙BU", "销售费用", 400.0, "差旅"),
        ]
        for i, (k, bu, cat, amt, matter) in enumerate(samples):
            conn.execute(
                "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
                "预算明细费用类型,预算归属部门,事项,归属月,原值_归属月,已删除)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                (
                    k,
                    "1月",
                    f"2026-01-{i + 1:02d}",
                    money.yuan_to_fen(amt),
                    bu,
                    cat,
                    "细类",
                    "部门",
                    matter,
                    "2026-01",
                    "2026-01",
                ),
            )
        conn.commit()
        conn.close()
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.TestClient = TestClient
        cls.cfg_path = loaders.config_path(cls.root) if hasattr(loaders, "config_path") else ROOT / "config.json"

    def _login(self, account, admin=False):
        c = self.TestClient(self.app)
        path = "/admin/login" if admin else "/login"
        r = c.post(path, data={"account": account, "password": "8888"}, follow_redirects=False)
        self.assertIn(r.status_code, (302, 303), r.text[:200])
        return c

    def test_overall_hides_salary_by_default(self):
        c = self._login("all")
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 50})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        cats = {row.get("对应报表大类") for row in d["rows"]}
        self.assertNotIn("工资", cats)
        self.assertIn("管理费用", cats)
        # 含事项列
        self.assertIn("事项", d["columns"])
        matters = {row.get("事项") for row in d["rows"]}
        self.assertIn("办公", matters)

    def test_overall_see_salary_when_enabled(self):
        c = self._login("admin1", admin=True)
        r = c.post("/api/settings", json={"overall_see_salary": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("overall_see_salary"))
        # 不得脏写 config.json
        cfg_file = ROOT / "config.json"
        text = cfg_file.read_text(encoding="utf-8")
        self.assertNotIn("overall_see_salary", text)

        c2 = self._login("all")
        r2 = c2.get("/api/detail", params={"table": "费用明细", "page_size": 50})
        self.assertEqual(r2.status_code, 200)
        cats = {row.get("对应报表大类") for row in r2.json()["rows"]}
        self.assertIn("工资", cats)

        # 关回
        c.post("/api/settings", json={"overall_see_salary": False})

    def test_admin_always_sees_salary(self):
        c = self._login("admin1", admin=True)
        # 即使开关关
        self.cfg["overall_see_salary"] = False
        r = c.get("/api/detail", params={"table": "费用明细", "page_size": 50})
        self.assertEqual(r.status_code, 200)
        cats = {row.get("对应报表大类") for row in r.json()["rows"]}
        self.assertIn("工资", cats)

    def test_bu_cannot_see_other_bu(self):
        c = self._login("bu_a")
        r = c.get("/api/detail", params={"table": "费用明细", "bu": "乙BU"})
        self.assertEqual(r.status_code, 403)
        r2 = c.get("/api/detail", params={"table": "费用明细", "page_size": 50})
        self.assertEqual(r2.status_code, 200)
        for row in r2.json()["rows"]:
            self.assertEqual(row.get("业务BU"), "甲BU")

    def test_dashboard_has_ledger_entry(self):
        html = (ROOT / "static" / "templates" / "render" / "dashboard_body.html").read_text(encoding="utf-8")
        self.assertIn("mainLedgerCard", html)
        self.assertIn("费用明细", html)
        self.assertIn("事项", html)
        self.assertIn("mlFilterPop", html, "整体页列筛弹层占位")
        js = (ROOT / "static" / "js" / "cockpit.js").read_text(encoding="utf-8")
        self.assertIn("mainLedgerCard", js)
        self.assertIn("/api/detail", js)
        self.assertIn("filters", js)

    def test_main_ledger_text_multiselect_like_b7(self):
        """准则2 同款：文本列关键词 + /api/detail/values 去重值多选（非仅 prompt）。"""
        js = (ROOT / "static" / "js" / "cockpit.js").read_text(encoding="utf-8")
        # 截取 mainLedger 段
        i = js.find("mainLedgerCard")
        self.assertGreater(i, 0)
        chunk = js[i : i + 9000]
        self.assertIn("/api/detail/values", chunk, "文本列须调 values 接口")
        self.assertIn("mlfVals", chunk, "去重值多选容器")
        self.assertIn("type=\"checkbox\"", chunk.replace("'", '"') or chunk, "多选 checkbox")
        self.assertIn("next.in", chunk, "应用多选 in 写入 colFilters")
        self.assertIn("mlfQ", chunk, "关键词输入")
        # 不得仅用 prompt 做文本筛（旧实现）
        self.assertNotIn('prompt(col+" 关键词', chunk)

    def test_ml_filter_pop_body_escape_rule17(self):
        """铁律17：#mlFilterPop 不得困在 #periodSync（will-change:transform）；打开时 body.appendChild。"""
        html = (ROOT / "static" / "templates" / "render" / "dashboard_body.html").read_text(encoding="utf-8")
        # 模板：弹层在 </div> wrap/foot 之后、与 #tip 同级（不在 periodSync 内）
        i_sync = html.find('id="periodSync"')
        i_end_sync = html.find("</div>", html.find('id="mainLedgerCard"'))  # rough
        i_pop = html.find('id="mlFilterPop"')
        self.assertGreater(i_pop, 0, "缺 mlFilterPop")
        # periodSync 开标签之后、mlFilterPop 之前不应仍把 pop 嵌在 sync 块内：
        # 可靠判据= pop 出现在脚注/foot 之后（与 tip 同区）
        self.assertIn("交付收入 = 交付金额", html[:i_pop] if i_pop > 0 else "")
        self.assertLess(html.find('id="mainLedgerCard"'), i_pop)
        # 不在 periodSync 开标签到 mainLedger 之间作为「仅内嵌」——要求 HTML 注释铁律17 或 body 区
        self.assertIn("铁律17", html[html.find("mlFilterPop") - 200 : html.find("mlFilterPop") + 80])
        js = (ROOT / "static" / "js" / "cockpit.js").read_text(encoding="utf-8")
        i = js.find("function openFilter")
        self.assertGreater(i, 0)
        open_fn = js[i : i + 600]
        self.assertIn("document.body.appendChild(pop)", open_fn, "打开列筛必须 body.appendChild(pop)")
        self.assertIn("parentElement!==document.body", open_fn)

    def test_settings_ui_has_switch(self):
        html = (ROOT / "static" / "admin" / "admin.html").read_text(encoding="utf-8")
        self.assertIn("sOverallSalary", html)
        self.assertIn("整体账号可见工资明细", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
