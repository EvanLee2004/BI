#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归档：db 每日滚动备份（留30份）+ 月末快照（03 详细设计 一·3 / 七）。

- **db 每日备份**：每次更新跑完拷 数据/备份/看板_YYYYMMDD.db，留最近 30 份——人工表(调整/手填)
  不可再生，标准表可重抓。
- **月末快照**：当天=当月最后一天 → 拷 6 个原始源 + 看板.db + summary.json 到 数据/快照存档/YYYY-MM/。
  "财务永远讲某一个时点"。
两者都写在 数据/ 内，已由 .gitignore 挡住（绝不进 git）。
"""

from __future__ import annotations

import calendar
import datetime
import shutil
from pathlib import Path

import loaders
import db


def _vacuum_into(src: Path, dst: Path) -> None:
    """SQLite ≥3.27：VACUUM INTO 产出单文件一致快照（含 WAL 视图）。"""
    import sqlite3

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    conn = sqlite3.connect(str(src), timeout=30.0)
    try:
        # 安全字面量路径：仅接受本机 Path 解析后的绝对路径
        target = str(dst.resolve())
        if "'" in target:
            raise OSError("backup path contains quote")
        conn.execute(f"VACUUM INTO '{target}'")
    finally:
        conn.close()


def backup_db(  # noqa: C901  # 2.6.3·D5 pre-restore 清理分支
    cfg: dict, today: datetime.date | None = None, root: Path | None = None, keep: int | None = None
) -> dict:
    """拷 看板.db → 数据/备份/看板_YYYYMMDD.db，滚动保留最近 keep 份（每天一份≈保留 keep 天）。

    任务书64·D1：优先 VACUUM INTO 一致快照；失败回退 copy2 并体检黄（status=degraded）。
    keep 不传 → 读 config.backup_keep_days（缺省 30），管理员端「设置」页可改。
    注意：仅清理 备份/看板_*.db；**不触及** 快照存档/ 与 年度归档/（永久保留）。
    """
    if keep is None:
        keep = max(1, int(cfg.get("backup_keep_days", 30) or 30))
    src = db.db_path(cfg, root)
    if not src.exists():
        return {"status": "skip", "detail": "库文件不存在", "ok": False}
    day = today or datetime.date.today()
    bdir = loaders.data_dir(cfg, root) / "备份"
    bdir.mkdir(parents=True, exist_ok=True)
    dst = bdir / f"看板_{day:%Y%m%d}.db"
    method = "vacuum_into"
    try:
        _vacuum_into(src, dst)
    except Exception as e:
        method = "copy2_fallback"
        try:
            shutil.copy2(src, dst)
        except OSError as e2:
            return {"status": "error", "detail": f"VACUUM INTO 失败({type(e).__name__}: {e}); copy2 失败({e2})", "ok": False}
    backups = sorted(bdir.glob("看板_*.db"))
    pruned = 0
    while len(backups) > keep:
        backups[0].unlink()
        backups.pop(0)
        pruned += 1
    # 2.6.3·D5：看板.db.pre-restore-* 一并滚动清理（与 keep 同量级，留最近 keep 份）
    pre_restores = sorted(bdir.glob("看板.db.pre-restore-*")) + sorted(
        loaders.data_dir(cfg, root).glob("看板.db.pre-restore-*")
    )
    # 去重路径
    seen_pre: set[str] = set()
    pre_list: list[Path] = []
    for pp in pre_restores:
        k = str(pp.resolve()) if pp.exists() else str(pp)
        if k in seen_pre:
            continue
        seen_pre.add(k)
        pre_list.append(pp)
    pre_list = sorted(pre_list, key=lambda x: x.stat().st_mtime if x.exists() else 0)
    while len(pre_list) > keep:
        try:
            pre_list[0].unlink(missing_ok=True)
            pruned += 1
        except OSError:
            pass
        pre_list.pop(0)
    out = {
        "status": "ok" if method == "vacuum_into" else "degraded",
        "path": str(dst),
        "kept": len(backups),
        "pruned": pruned,
        "ok": True,
        "method": method,
    }
    if method != "vacuum_into":
        out["detail"] = "VACUUM INTO 失败，已回退 copy2（体检黄）"
        out["yellow"] = True
    return out


def restore_db_from_backup(
    cfg: dict, backup_path: Path | str, root: Path | None = None
) -> dict:
    """从每日滚动备份恢复看板.db（覆盖当前库）。测试/演练用；部署手册「恢复演练」章节同步骤。

    步骤：停写 → copy2 备份→目标 → 下次 connect 自动 migrate/建表。
    返回 {status, path, detail}。
    """
    src = Path(backup_path)
    if not src.exists() or not src.is_file():
        return {"status": "error", "detail": f"备份不存在：{src}"}
    dst = db.db_path(cfg, root)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # 恢复前再留一份当前库（若存在）
    if dst.exists():
        pre = dst.with_name(dst.name + f".pre-restore-{datetime.datetime.now():%Y%m%d%H%M%S}")
        try:
            shutil.copy2(dst, pre)
        except OSError:
            pre = None
    else:
        pre = None
    try:
        shutil.copy2(src, dst)
    except OSError as e:
        return {"status": "error", "detail": str(e), "pre": str(pre) if pre else None}
    return {"status": "ok", "path": str(dst), "from": str(src), "pre": str(pre) if pre else None}


_ARCHIVE_OK = "_ARCHIVE_OK"


def _year_archive_complete(arch: Path) -> bool:
    """已归档只认最终目录 + _ARCHIVE_OK 标记（2.6.3·B4）。"""
    return arch.is_dir() and (arch / _ARCHIVE_OK).is_file()


def maybe_year_archive_zhiyun(  # noqa: C901  # 跨年归档分支：存在/跳过/拷贝/失败
    cfg: dict,
    root: Path | None = None,
    today: datetime.date | None = None,
) -> dict:
    """跨年自动归档（任务书64·E / 2.6.3·B4）：

    先拷进 ``年度归档/<旧年>.partial/``，**全部成功**再原子 rename 成 ``<旧年>/`` 并写 ``_ARCHIVE_OK``。
    半截 partial 不视为 exists；下次会清掉 partial 重来。失败 → status=error（管道抬红+告警）。
    归档触发已移出 zhiyun_auto_fetch 分支，由管道必跑一步调用本函数。
    """
    from ingest import fetch_zhiyun

    day = today or datetime.date.today()
    since_raw = cfg.get("zhiyun_since") if cfg.get("zhiyun_since") is not None else "auto"
    resolved = fetch_zhiyun.resolve_zhiyun_since(since_raw, today=day)
    if not resolved:
        return {"status": "skip", "detail": "zhiyun_since 全量/空，不触发跨年归档"}
    try:
        y = int(resolved[:4])
    except (TypeError, ValueError):
        return {"status": "skip", "detail": f"无法解析 since 年份：{resolved}"}
    if y != day.year:
        return {"status": "skip", "detail": f"since 年 {y} ≠ today 年 {day.year}"}
    prev = y - 1
    if prev < 2000:
        return {"status": "skip", "detail": "prev year 无效"}
    base = loaders.data_dir(cfg, root)
    arch_root = base / "年度归档"
    arch = arch_root / str(prev)
    if _year_archive_complete(arch):
        return {"status": "exists", "path": str(arch), "year": prev, "ok": True}
    # 半截最终目录（无 OK 标记）→ 视为失败残留，不当 exists；移走后重做
    if arch.is_dir():
        try:
            broken = arch_root / f"{prev}.broken-{datetime.datetime.now():%Y%m%d%H%M%S}"
            arch.rename(broken)
        except OSError as e:
            return {
                "status": "error",
                "detail": f"残留归档目录无法移走: {e}",
                "ok": False,
                "year": prev,
                "red": True,
            }
    stems = []
    files_cfg = cfg.get("files") or {}
    for key in ("orders", "receipts", "project_detail_stem", "inhouse"):
        name = files_cfg.get(key)
        if not name:
            continue
        if key == "project_detail_stem":
            p = base / f"{name}.xlsx"
        else:
            p = base / name
        if p.is_file():
            stems.append(p)
    if not stems:
        return {"status": "skip", "detail": "无本地四源 xlsx，跳过归档", "year": prev}
    partial = arch_root / f"{prev}.partial"
    try:
        if partial.exists():
            shutil.rmtree(partial)
        partial.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"status": "error", "detail": f"无法创建 partial: {e}", "ok": False, "year": prev, "red": True}
    copied: list[str] = []
    try:
        for p in stems:
            shutil.copy2(p, partial / p.name)
            copied.append(p.name)
        dbp = db.db_path(cfg, root)
        if dbp.is_file():
            try:
                _vacuum_into(dbp, partial / f"看板_{prev}.db")
            except Exception:
                shutil.copy2(dbp, partial / f"看板_{prev}.db")
            copied.append(f"看板_{prev}.db")
        # 完成标记 + 原子 rename
        (partial / _ARCHIVE_OK).write_text(
            f"year={prev}\nfiles={','.join(copied)}\n",
            encoding="utf-8",
        )
        partial.rename(arch)
    except OSError as e:
        return {
            "status": "error",
            "detail": str(e),
            "ok": False,
            "year": prev,
            "files": copied,
            "red": True,
        }
    return {
        "status": "archived",
        "path": str(arch),
        "year": prev,
        "files": copied,
        "ok": True,
        "detail": f"已归档 {prev}",
    }


def snapshot_page(
    cfg: dict, html: str, today: datetime.date | None = None, root: Path | None = None, keep: int | None = None
) -> dict:
    """2.2.7 起停写老页面 HTML 快照（历史改为 vm JSON + Vue 只读）。

    保留函数签名供旧测试/调用兼容；不再落盘 `页面_*.html`。
    新路径请用 ``snapshot_vm``。
    """
    _ = (cfg, html, today, root, keep)
    return {"status": "disabled", "path": "", "kept": 0, "pruned": 0, "detail": "2.2.7 起停写页面_*.html，改用 snapshot_vm"}


def snapshot_vm(
    cfg: dict,
    *,
    cockpit_vm: dict,
    bu_vms: dict | None = None,
    today: datetime.date | None = None,
    root: Path | None = None,
    keep: int | None = None,
    built_at: str | None = None,
    version: str | None = None,
) -> dict:
    """存当天经营 VM → 数据/备份/vm_YYYYMMDD.json（同天覆盖=留当天最后一次）。

    内容与 /api/v1/vm/cockpit 同源结构的 cockpit + 可选 bu 字典 + built_at + version。
    滚动保留 keep 天（同 backup_keep_days）；月末另拷入 快照存档/YYYY-MM/ 永久保留。
    """
    import json
    import time

    if keep is None:
        keep = max(1, int(cfg.get("backup_keep_days", 365) or 365))
    day = today or datetime.date.today()
    bdir = loaders.data_dir(cfg, root) / "备份"
    bdir.mkdir(parents=True, exist_ok=True)
    dest = bdir / f"vm_{day:%Y%m%d}.json"
    if version is None:
        try:
            from version import read_version

            version = read_version()
        except Exception:
            version = ""
    if built_at is None:
        built_at = time.strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "day": f"{day:%Y%m%d}",
        "built_at": built_at,
        "version": version or "",
        "cockpit": cockpit_vm if isinstance(cockpit_vm, dict) else {},
        "bu": bu_vms if isinstance(bu_vms, dict) else {},
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    if is_month_end(day):
        snap = loaders.data_dir(cfg, root) / "快照存档" / f"{day:%Y-%m}"
        snap.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, snap / dest.name)
    pages = sorted(bdir.glob("vm_*.json"))
    pruned = 0
    while len(pages) > keep:
        pages[0].unlink()
        pages.pop(0)
        pruned += 1
    return {"status": "ok", "path": str(dest), "kept": len(pages), "pruned": pruned}


def list_vm_archives(cfg: dict, root: Path | None = None) -> list[dict]:
    """列出 备份/vm_*.json，倒序（新→旧）。字段 day/label/saved_at/kb 供管理端历史列表。"""
    import time

    bdir = loaders.data_dir(cfg, root) / "备份"
    out: list[dict] = []
    if not bdir.is_dir():
        return out
    for p in sorted(bdir.glob("vm_*.json"), reverse=True):
        stem = p.stem  # vm_YYYYMMDD
        parts = stem.split("_", 1)
        d = parts[1] if len(parts) == 2 else ""
        if len(d) != 8 or not d.isdigit():
            continue
        out.append(
            {
                "day": d,
                "label": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                "saved_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
                "kb": round(p.stat().st_size / 1024),
                "format": "vm",
            }
        )
    return out


def load_vm_archive(cfg: dict, day: str, root: Path | None = None) -> dict | None:
    """读 备份/vm_YYYYMMDD.json；不存在返回 None。day 须为 8 位数字。"""
    import json

    if not day or len(day) != 8 or not day.isdigit():
        return None
    p = loaders.data_dir(cfg, root) / "备份" / f"vm_{day}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_month_end(day: datetime.date) -> bool:
    return day.day == calendar.monthrange(day.year, day.month)[1]


def _snapshot_month_dir(base: Path, year: int, month: int) -> Path:
    return base / "快照存档" / f"{year:04d}-{month:02d}"


def _month_snapshot_exists(base: Path, year: int, month: int) -> bool:
    """2.6.7 C-6：半截（.partial）视为不存在；完整目录才算 exists。"""
    d = _snapshot_month_dir(base, year, month)
    if d.name.endswith(".partial"):
        return False
    partial = d.parent / (d.name + ".partial")
    if partial.is_dir():
        # 仅有 partial、无正式目录 → 不存在
        return False
    marker = d / "_SNAPSHOT_OK"
    if d.is_dir() and marker.is_file():
        return True
    # 兼容旧快照（无 marker 但有内容）
    return d.is_dir() and any(p.name != ".partial" for p in d.iterdir())


def ensure_prev_month_snapshot(
    cfg: dict, today: datetime.date | None = None, root: Path | None = None
) -> dict:
    """2.6.3·B3：每次管道检查上个月快照是否存在；不在则补做（用「上月最后一天」作 day）。

    返回 {status, done, missing_month, path?, yellow?}。
    """
    day = today or datetime.date.today()
    # 上月
    if day.month == 1:
        py, pm = day.year - 1, 12
    else:
        py, pm = day.year, day.month - 1
    base = loaders.data_dir(cfg, root)
    if _month_snapshot_exists(base, py, pm):
        return {
            "status": "exists",
            "done": True,
            "missing_month": None,
            "path": str(_snapshot_month_dir(base, py, pm)),
        }
    # 上月最后一天
    last = calendar.monthrange(py, pm)[1]
    snap_day = datetime.date(py, pm, last)
    r = snapshot_if_month_end(cfg, snap_day, root, force=True)
    r["missing_month"] = f"{py:04d}-{pm:02d}"
    r["yellow"] = True  # 缺月补做 → 体检黄
    r["detail"] = (r.get("detail") or "") + f"；补做上月快照 {py:04d}-{pm:02d}"
    return r


def snapshot_if_month_end(
    cfg: dict,
    today: datetime.date | None = None,
    root: Path | None = None,
    *,
    force: bool = False,
) -> dict:
    """当天=当月最后一天 → 拷 原始6源 + 看板.db + summary.json 到 快照存档/YYYY-MM/。

    2.6.3·B3：返回明确 ``done`` 布尔；force=True 时忽略「是否月末」检查（供补漏月）。
    """
    day = today or datetime.date.today()
    if not force and not is_month_end(day):
        return {"status": "skip", "detail": "非当月最后一天", "done": False}
    base = loaders.data_dir(cfg, root)
    snap = base / "快照存档" / f"{day:%Y-%m}"
    # 2.6.7 C-6：先写 .partial，完成再原子 rename；半截不视为 exists
    partial = base / "快照存档" / f"{day:%Y-%m}.partial"
    if partial.exists():
        shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True, exist_ok=True)
    copied = []
    # 6 个原始源（项目明细是 stem 无后缀，补 .xlsx/.csv；其余已带后缀）
    for name in (cfg.get("files") or {}).values():
        for p in (base / name, base / f"{name}.xlsx", base / f"{name}.csv"):
            if p.exists() and p.is_file():
                shutil.copy2(p, partial / p.name)
                copied.append(p.name)
                break
    # 看板.db
    dbp = db.db_path(cfg, root)
    if dbp.exists():
        shutil.copy2(dbp, partial / dbp.name)
        copied.append(dbp.name)
    # summary.json（run_batch 写到 output_json）
    sj = loaders.ROOT / cfg.get("output_json", "data/驾驶舱数据.json")
    if sj.exists():
        shutil.copy2(sj, partial / "summary.json")
        copied.append("summary.json")
    done = bool(copied)
    if done:
        (partial / "_SNAPSHOT_OK").write_text("ok\n", encoding="utf-8")
        if snap.exists():
            shutil.rmtree(snap, ignore_errors=True)
        partial.rename(snap)
        path_out = str(snap)
    else:
        shutil.rmtree(partial, ignore_errors=True)
        path_out = str(snap)
    return {
        "status": "snapshot" if done else "empty",
        "path": path_out,
        "copied": sorted(set(copied)),
        "done": done,
    }
