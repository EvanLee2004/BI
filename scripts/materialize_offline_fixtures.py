#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""物化 3.6.0 离线门禁脱敏 fixture → 仓库根 `_golden_data/`。

确定性：对 seed 业务文件整文件拷贝，两次运行同名文件 SHA-256 一致。
不写正式 `config.json`，不依赖本机 `数据/`，不含生产口令。

用法：
  python scripts/materialize_offline_fixtures.py
  python scripts/materialize_offline_fixtures.py --check-hash
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "tests" / "fixtures" / "offline_seed"
# 双落盘：_golden_data 供 KANBAN_PROFILE=dev；数据/ 供默认 config 与硬编码路径测试
DESTS = (ROOT / "_golden_data", ROOT / "数据")

# 业务进料 + BU 配置（整文件从 seed 拷贝）
COPY_NAMES = (
    "下单.xlsx",
    "内部译员.xlsx",
    "回款记录.xlsx",
    "手填与调整.xlsx",
    "收单台账.xlsx",
    "项目明细.xlsx",
    "BU配置.json",
    "智云配置.json",
)

# 账号始终由 seed 的脱敏表写入（覆盖任何残留生产账号）
ACCOUNTS_NAME = "看板账号.json"

# 离线本机覆盖：关智云抓数（可被本地配置合入；不写 config.json）
LOCAL_OVERLAY = {
    "zhiyun_auto_fetch": False,
    "_offline_fixture": True,
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_accounts(acc_src: Path) -> None:
    raw = json.loads(acc_src.read_text(encoding="utf-8"))
    accounts = raw.get("accounts") or []
    if not accounts:
        raise SystemExit("offline accounts seed empty")
    for a in accounts:
        if not str(a.get("密码") or "").strip():
            raise SystemExit(f"empty password in seed account {a.get('账号')!r}")
        # 拒绝生产真人账号名进入 seed 物化
        if a.get("账号") in {"lushasha"}:
            raise SystemExit(f"production-like account rejected: {a.get('账号')!r}")


def _materialize_one(dest: Path) -> dict[str, str]:
    dest.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for name in COPY_NAMES:
        src = SEED / name
        if not src.is_file():
            raise SystemExit(f"missing seed file: {src}")
        dst = dest / name
        shutil.copy2(src, dst)
        hashes[name] = _sha256(dst)
    acc_src = SEED / ACCOUNTS_NAME
    if not acc_src.is_file():
        raise SystemExit(f"missing accounts seed: {acc_src}")
    _validate_accounts(acc_src)
    shutil.copy2(acc_src, dest / ACCOUNTS_NAME)
    hashes[ACCOUNTS_NAME] = _sha256(dest / ACCOUNTS_NAME)
    # 本地覆盖（gitignore 的 json；仅离线 fixture 标记）
    loc = dest / "本地配置.json"
    loc.write_text(json.dumps(LOCAL_OVERLAY, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hashes["本地配置.json"] = _sha256(loc)
    meta = {
        "source": "tests/fixtures/offline_seed",
        "purpose": "KANBAN_OFFLINE gate",
        "dest": str(dest.relative_to(ROOT)) if dest.is_relative_to(ROOT) else str(dest),
        "files": sorted(hashes.keys()),
    }
    (dest / ".offline_fixture_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return hashes


def materialize() -> dict[str, str]:
    if not SEED.is_dir():
        raise SystemExit(f"missing seed dir: {SEED}")
    all_h: dict[str, str] = {}
    for dest in DESTS:
        h = _materialize_one(dest)
        for k, v in h.items():
            all_h[f"{dest.name}/{k}"] = v
    return all_h


def main() -> int:
    ap = argparse.ArgumentParser(description="Materialize offline fixtures to _golden_data and 数据/")
    ap.add_argument(
        "--check-hash",
        action="store_true",
        help="materialize twice and assert file hashes match",
    )
    args = ap.parse_args()
    h1 = materialize()
    print(f"materialized {len(h1)} file-slots → {[str(d.name) for d in DESTS]}")
    for k, v in sorted(h1.items()):
        print(f"  {k}: {v[:16]}…")
    if args.check_hash:
        h2 = materialize()
        if h1 != h2:
            print("HASH MISMATCH between two materializations", file=sys.stderr)
            for k in sorted(set(h1) | set(h2)):
                if h1.get(k) != h2.get(k):
                    print(f"  {k}: {h1.get(k)} vs {h2.get(k)}", file=sys.stderr)
            return 1
        print("hash check OK (deterministic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
