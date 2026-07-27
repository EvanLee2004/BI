# -*- coding: utf-8 -*-
"""2.6.9 S6：将 5 组重复生效调整中较早 id 标「已撤销」（不删记录）。"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# early id of each pair
EARLY_IDS = [10, 3, 2, 1, 20]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "数据" / "看板.db"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    db = Path(args.db)
    if not db.is_file():
        print("missing db", db)
        return 2
    conn = sqlite3.connect(str(db))
    cur = conn.execute("SELECT id, 状态 FROM adj_调整记录 WHERE id IN (%s)" % ",".join("?" * len(EARLY_IDS)), EARLY_IDS)
    rows = {r[0]: r[1] for r in cur.fetchall()}
    print("found", rows)
    to_revoke = [i for i in EARLY_IDS if rows.get(i) == "生效"]
    print("to_revoke", to_revoke)
    if not args.apply:
        print("dry-run only; pass --apply to write")
        return 0
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = db.with_name(db.name + f".bak_s6_{ts}")
    shutil.copy2(db, bak)
    print("backup", bak, bak.stat().st_size)
    conn.execute(
        "UPDATE adj_调整记录 SET 状态=? WHERE id IN (%s) AND 状态=?"
        % ",".join("?" * len(to_revoke)),
        ["已撤销", *to_revoke, "生效"] if to_revoke else ["已撤销", "生效"],
    )
    if to_revoke:
        conn.execute(
            f"UPDATE adj_调整记录 SET 状态='已撤销' WHERE id IN ({','.join(str(i) for i in to_revoke)}) AND 状态='生效'"
        )
    conn.commit()
    print("status", conn.execute("SELECT 状态,count(*) FROM adj_调整记录 GROUP BY 状态").fetchall())
    conn.close()
    # rollback SQL
    rb = ROOT / "docs" / "验收证据" / "2_6_9" / "s6_rollback.sql"
    rb.parent.mkdir(parents=True, exist_ok=True)
    rb.write_text(
        "-- rollback S6\nUPDATE adj_调整记录 SET 状态='生效' WHERE id IN (%s);\n"
        % ",".join(str(i) for i in to_revoke),
        encoding="utf-8",
    )
    note = ROOT / "docs" / "验收证据" / "2_6_9" / "s6_stock_adj_revoke.txt"
    note.write_text(
        f"backup={bak}\nbytes={bak.stat().st_size}\nrevoked_ids={to_revoke}\nearly_ids={EARLY_IDS}\n",
        encoding="utf-8",
    )
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
