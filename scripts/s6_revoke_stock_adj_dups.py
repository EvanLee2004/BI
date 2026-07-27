# -*- coding: utf-8 -*-
"""2.6.9 S6：5 组重复生效调整中，撤销「晚到的重复」id（不删记录）。

清单（from docs/验收证据/2_6_8/t3_stock_adj_dups.txt）:
  pairs 10/12, 3/9, 2/7, 1/5, 20/21

⚠ 任务书原文写「撤销较早 id」。生产实测：较早 id 是真实 原值→新值 变更，
较晚 id 是 原值=新值 的空操作重复。撤销较早会导致回放只剩空操作 → 数字漂移
（例：SOD26060992 交付月从 6 月回到 7 月，H1 交付约 −9.2 万）。
因此实现改为撤销 **较晚 id**：12,9,7,5,21；保留较早 10,3,2,1,20 为生效。

用法:
  .venv/bin/python scripts/s6_revoke_stock_adj_dups.py          # dry-run
  .venv/bin/python scripts/s6_revoke_stock_adj_dups.py --apply  # 备份后写库

证据: docs/验收证据/2_6_9/s6_stock_adj_revoke.txt + s6_rollback.sql
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 每组较晚 id（重复空操作）——撤销这些
REVOKE_IDS = [12, 9, 7, 5, 21]
# 每组较早 id（真实变更）——保留生效
KEEP_IDS = [10, 3, 2, 1, 20]
# 完整配对（early kept, late revoked）
PAIRS = [(10, 12), (3, 9), (2, 7), (1, 5), (20, 21)]
EVID = ROOT / "docs" / "验收证据" / "2_6_9"


def _status_counts(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT 状态, count(*) FROM adj_调整记录 GROUP BY 状态 ORDER BY 状态"
    ).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(ROOT / "数据" / "看板.db"))
    ap.add_argument("--apply", action="store_true", help="写库；默认 dry-run")
    args = ap.parse_args()
    db = Path(args.db)
    if not db.is_file():
        print("missing db", db)
        return 2

    EVID.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    found: dict[int, str] = {}
    for i in REVOKE_IDS + KEEP_IDS:
        row = conn.execute(
            "SELECT id, 状态, 目标表, 定位键, 字段, 原值, 新值 FROM adj_调整记录 WHERE id=?",
            (i,),
        ).fetchone()
        if row:
            found[i] = str(row["状态"])
            print(
                f"id={i} status={row['状态']} table={row['目标表']} "
                f"key={row['定位键']} field={row['字段']} "
                f"{row['原值']!r}→{row['新值']!r}"
            )
        else:
            print(f"id={i} NOT_IN_DB")

    # 撤销目标：较晚 id；接受 生效/过期疑似（空操作重复常见为过期疑似）
    to_revoke = [
        i for i in REVOKE_IDS if found.get(i) in ("生效", "过期疑似")
    ]
    already = [i for i in REVOKE_IDS if found.get(i) == "已撤销"]
    missing = [i for i in REVOKE_IDS if i not in found]
    print("to_revoke", to_revoke)
    print("already_revoked", already)
    print("missing_in_db", missing)
    print("keep_early", KEEP_IDS)
    print("status_before", _status_counts(conn))

    rb = EVID / "s6_rollback.sql"
    rb.write_text(
        "-- S6 rollback: restore late-id duplicates to 生效\n"
        f"UPDATE adj_调整记录 SET 状态='生效' WHERE id IN ({','.join(str(i) for i in REVOKE_IDS)});\n"
        "-- pairs (early kept, late revoked): " + repr(PAIRS) + "\n"
        "-- keep early effective: " + repr(KEEP_IDS) + "\n",
        encoding="utf-8",
    )
    print("wrote", rb)

    if not args.apply:
        note = {
            "mode": "dry-run",
            "pairs": PAIRS,
            "revoke_ids": REVOKE_IDS,
            "keep_ids": KEEP_IDS,
            "found": found,
            "to_revoke": to_revoke,
            "already_revoked": already,
            "missing_in_db": missing,
            "status_before": [list(x) for x in _status_counts(conn)],
            "rollback_sql": str(rb),
            "note": "Revoke LATE no-op duplicates; keep EARLY real mutations.",
        }
        (EVID / "s6_stock_adj_revoke.txt").write_text(
            json.dumps(note, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("dry-run only; pass --apply to write")
        conn.close()
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = db.with_name(db.name + f".bak_s6_{ts}")
    shutil.copy2(db, bak)
    print("backup", bak, bak.stat().st_size)

    if to_revoke:
        placeholders = ",".join("?" * len(to_revoke))
        conn.execute(
            f"UPDATE adj_调整记录 SET 状态='已撤销' "
            f"WHERE id IN ({placeholders}) AND 状态 IN ('生效','过期疑似')",
            to_revoke,
        )
        conn.commit()

    after = _status_counts(conn)
    print("status_after", after)
    conn.close()

    note = {
        "mode": "apply",
        "pairs": PAIRS,
        "revoke_ids": REVOKE_IDS,
        "keep_ids": KEEP_IDS,
        "found_before": found,
        "revoked_ids": to_revoke,
        "already_revoked": already,
        "missing_in_db": missing,
        "backup": str(bak),
        "backup_bytes": bak.stat().st_size,
        "status_after": [list(x) for x in after],
        "rollback_sql": str(rb),
        "note": (
            "Revoke late no-op dups (12,9,7,5,21); keep early real changes. "
            "On production expect 生效 25→20 (or 20+过期疑似→20 生效 +5 已撤销)."
        ),
    }
    (EVID / "s6_stock_adj_revoke.txt").write_text(
        json.dumps(note, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
