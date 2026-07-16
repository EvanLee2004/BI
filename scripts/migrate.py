#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·5：schema 迁移工具化——罗列/执行版本。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    ap = argparse.ArgumentParser(description="看板 schema 迁移")
    ap.add_argument("action", choices=["list", "apply"], help="list=罗列 / apply=执行 ensure_schema")
    args = ap.parse_args()
    import db
    import loaders
    from domain import config_engine as ce

    cfg = loaders.load_config(ROOT)
    conn = db.connect(cfg, ROOT)
    try:
        if args.action == "list":
            print("schema: db.ensure_schema / money fen / cfg_口径配置")
            print("tables:", list(db.SCHEMA.keys()) if hasattr(db, "SCHEMA") else "(see schema.py)")
        else:
            # 复用现有建表
            if hasattr(db, "init_schema"):
                db.init_schema(conn)
            elif hasattr(db, "ensure_schema"):
                db.ensure_schema(conn)
            ce.ensure_schema(conn)
            ce.seed_if_empty(conn, cfg)
            print("✓ migrate apply 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
