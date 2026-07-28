# -*- coding: utf-8 -*-
"""2.6.12 F-01：完整排名弹层须与主列表同 click 契约（onItemClick + mkey → 月钻）。

根因：RankList 主列表可点，rank-modal-list 弹层漏绑 onItemClick。
本文件锁：
1. 源码：modal 列表行含 is-clickable / onItemClick / mkey 契约（与主列表同）
2. RankingsDual 传 on-item-click，toListItems/fetchFull 保留 mkey
3. 服务端 full 行带 mkey（契约不回退）
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestRankListModalClickContract(unittest.TestCase):
    """F-01：弹层与主列表 click 契约一致。"""

    def test_rank_list_modal_binds_on_item_click(self):
        src = (ROOT / "frontend/src/components/base/RankList.vue").read_text(encoding="utf-8")
        self.assertIn('data-testid="rank-modal-list"', src)
        # 弹层块内须有 is-clickable + onItemClick（与主列表同契约）
        # 取 rank-modal-list 之后到 </DataModal> 之前
        m = re.search(
            r'data-testid="rank-modal-list"[\s\S]*?</DataModal>',
            src,
        )
        self.assertIsNotNone(m, "rank-modal-list block missing")
        block = m.group(0)
        self.assertIn("is-clickable", block)
        self.assertIn("onItemClick", block)
        self.assertIn("mkey", block)
        # 必须是行容器 click，不能只渲染 RankBar
        self.assertIn("rank-list__row", block)
        self.assertRegex(block, r"@click=.*onItemClick")

    def test_main_list_still_clickable(self):
        src = (ROOT / "frontend/src/components/base/RankList.vue").read_text(encoding="utf-8")
        # 主列表契约不回退
        self.assertIn("is-clickable", src)
        self.assertIn("onItemClick", src)
        self.assertGreaterEqual(src.count("is-clickable"), 2, "main + modal both need is-clickable")

    def test_rankings_dual_passes_mkey_and_handler(self):
        src = (ROOT / "frontend/src/components/RankingsDual.vue").read_text(encoding="utf-8")
        self.assertIn("on-item-click", src)
        self.assertIn("onItemClick", src)
        self.assertIn("mkey", src)
        self.assertIn("1~12", src)
        self.assertIn("rankings_monthly_data", src)
        # full 映射保留 mkey
        self.assertIn("mkey: it.mkey", src)
        self.assertGreaterEqual(src.count("mkey: it.mkey"), 2)


class TestRankingsFullMkeyServer(unittest.TestCase):
    """full API 行带 mkey（弹层能开月钻的数据前提）。"""

    def test_item_row_includes_mkey(self):
        api = (ROOT / "src/api_v1.py").read_text(encoding="utf-8")
        self.assertIn('"mkey"', api)
        # _item_row 或等价须输出 mkey
        self.assertRegex(api, r'["\']mkey["\']\s*:')


class TestPasswordFreeAndWriteNo8888(unittest.TestCase):
    """F-02/F-03：短密 OK、空密 fail、_write 不静默 8888。"""

    def test_accounts_source_no_min8(self):
        src = (ROOT / "src/accounts.py").read_text(encoding="utf-8")
        self.assertNotIn("新密码至少 8 位", src)
        self.assertNotIn("len(new_pw or \"\") < 8", src)
        self.assertNotIn('a.get("密码") or DEFAULT_VIEW_PW', src)

    def test_write_empty_raises_not_8888(self):
        import sys
        import tempfile
        import shutil

        sys.path.insert(0, str(ROOT / "src"))
        import accounts
        import loaders

        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = dict(loaders.load_config())
            cfg["data_dir"] = str(tmp)
            (tmp / "数据").mkdir(parents=True, exist_ok=True)
            # 直接调 _write 空密
            p = tmp / "数据" / "看板账号.json"
            with self.assertRaises(ValueError) as cm:
                accounts._write(
                    p,
                    [
                        {
                            "账号": "x",
                            "显示名": "x",
                            "权限": "整体",
                            "密码": "",
                            "密码版本": 0,
                        }
                    ],
                )
            self.assertIn("空", str(cm.exception))
            self.assertFalse(p.exists() or (p.exists() and "8888" in p.read_text(encoding="utf-8")))
            # seed 仍可显式默认
            rows = accounts.seed_defaults(cfg, tmp)
            self.assertTrue(any(r.get("密码") == accounts.DEFAULT_VIEW_PW for r in rows))
            # 短密 set 成功
            err = accounts.set_password(cfg, tmp, rows[0]["账号"], "ab")
            self.assertIsNone(err)
            acc = accounts.find_account(cfg, tmp, rows[0]["账号"])
            self.assertEqual(acc["密码"], "ab")
            self.assertNotEqual(acc["密码"], "8888")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMonthSnapshotExistsMarker(unittest.TestCase):
    """F-04：仅有 _SNAPSHOT_OK 才 exists。"""

    def test_snapshot_exists_marker_only(self):
        import sys
        import tempfile
        import shutil

        sys.path.insert(0, str(ROOT / "src"))
        from ingest import archive

        tmp = Path(tempfile.mkdtemp())
        try:
            base = tmp
            d = archive._snapshot_month_dir(base, 2026, 6)
            # 无目录
            self.assertFalse(archive._month_snapshot_exists(base, 2026, 6))
            # 有目录无 marker
            d.mkdir(parents=True)
            (d / "foo.xlsx").write_bytes(b"x")
            self.assertFalse(archive._month_snapshot_exists(base, 2026, 6))
            # 有 marker
            (d / "_SNAPSHOT_OK").write_text("ok\n", encoding="utf-8")
            self.assertTrue(archive._month_snapshot_exists(base, 2026, 6))
            # 仅 .partial
            shutil.rmtree(d)
            partial = d.parent / (d.name + ".partial")
            partial.mkdir(parents=True)
            (partial / "bar.xlsx").write_bytes(b"y")
            self.assertFalse(archive._month_snapshot_exists(base, 2026, 6))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestVersionChangelog2612(unittest.TestCase):
    def test_version_and_changelog(self):
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(ver, "2.7.0")
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        import version

        self.assertEqual(version.read_version(), "2.7.0")
        vers = [e.get("version") for e in version.PRODUCT_CHANGELOG if e.get("version")]
        self.assertIn("2.7.0", vers)
        self.assertIn("2.6.13", vers)
        self.assertIn("2.6.12", vers)
        self.assertEqual(vers[0], "2.7.0")


class TestF05ProfitRankingOneFen(unittest.TestCase):
    """F-05：样例 [100,100,100]@6% 总分=分项 net 之和（delta=0）。"""

    def test_total_rev_equals_sum_items(self):
        import sys
        import datetime as dt

        sys.path.insert(0, str(ROOT / "src"))
        from profit.tax_revenue import compute_profit_ranking

        cols = {
            "project_delivery_date": "整单交付日期",
            "project_revenue": "交付额",
            "project_cost": "项目成本",
        }
        s, e = dt.date(2026, 1, 1), dt.date(2026, 12, 31)
        rows = [
            {"客户": "A", "销售": "s", "整单交付日期": "2026-03-01", "交付额": 100, "项目成本": 0},
            {"客户": "B", "销售": "s", "整单交付日期": "2026-03-01", "交付额": 100, "项目成本": 0},
            {"客户": "C", "销售": "s", "整单交付日期": "2026-03-01", "交付额": 100, "项目成本": 0},
        ]
        rk = compute_profit_ranking(rows, "客户", cols, s, e, 0.06, top=10)
        item_sum = sum(it["revenue"] for it in rk["full_items"])
        self.assertEqual(rk["total_revenue"], item_sum)
        self.assertEqual(rk["total_revenue"] - item_sum, 0)


if __name__ == "__main__":
    unittest.main()
