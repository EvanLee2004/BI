#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智云（明道云）四源自动抓取：调内部接口拉表 → 产出与人工导出同构的 xlsx 写进料口 数据/。

纯函数层见 fetch_zhiyun_pure（2.6.1 R7 拆分，语义零变更）。
"""

from __future__ import annotations

import json
from pathlib import Path

import loaders

# re-export pure API for tests/importers that still `from fetch_zhiyun import parse_cell`
from .fetch_zhiyun_pure import (  # noqa: F401
    DEFAULT_ROW_DROP_RATIO,
    MAX_PAGES,
    PAGE_SIZE,
    ROW_TOTAL_ABS_TOL,
    ROW_TOTAL_REL_TOL,
    SOURCES,
    build_date_since_filter,
    check_required_columns,
    controls_with_name,
    fetch_all_rows,
    parse_cell,
    resolve_zhiyun_since,
    row_total_tolerance,
    rows_to_records,
    write_records_xlsx,
    ZHIYUN_DEFAULTS,
    _since_filter_value,
    _extract_row_total,
)

def _zhiyun_cfg_path(cfg: dict, root: Path | None) -> Path:
    return loaders.data_dir(cfg, root) / "智云配置.json"


def _merged_zhiyun_cfg(file_cfg: dict | None) -> dict:
    """内置默认 ← 本地文件（非空值胜出；tables 按源逐个合并）。永远返回可用 dict。"""
    out = {
        "base_url": ZHIYUN_DEFAULTS["base_url"],
        "app_id": ZHIYUN_DEFAULTS["app_id"],
        "tables": {s: dict(t) for s, t in ZHIYUN_DEFAULTS["tables"].items()},
    }
    for k, v in (file_cfg or {}).items():
        if k == "tables":
            for s, t in (v or {}).items():
                if not isinstance(t, dict):
                    continue
                cur = out["tables"].setdefault(s, {})
                for tk, tv in t.items():
                    if tv not in (None, ""):
                        cur[tk] = tv
        elif v not in (None, ""):
            out[k] = v
    return out


def _load_zhiyun_cfg(cfg: dict, root: Path | None) -> dict:
    """读 数据/智云配置.json 并叠加内置默认（文件缺失/坏 → 纯默认：连接信息可用、无账号密码）。"""
    p = _zhiyun_cfg_path(cfg, root)
    file_cfg = None
    if p.exists():
        try:
            file_cfg = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            file_cfg = None
    return _merged_zhiyun_cfg(file_cfg)


def _save_session(cfg: dict, root: Path | None, token: str, account_id: str | None) -> None:
    """把新 md_pss_id（和登录时取到的 account_id）回写进 智云配置.json，保留其余内容。
    文件不存在（连接走内置默认）也要写——否则 token 不持久、每轮更新都重登。失败静默。"""
    p = _zhiyun_cfg_path(cfg, root)
    try:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
        data["md_pss_id"] = token
        if account_id:
            data["account_id"] = account_id
        from secure_io import write_private_text

        write_private_text(p, json.dumps(data, ensure_ascii=False, indent=2))
    except OSError:
        pass


def _login_cooldown_path(cfg: dict, root: Path | None) -> Path:
    try:
        return loaders.data_dir(cfg or {}, root) / "智云登录冷却.json"
    except Exception:
        base = Path(root) if root else Path(".")
        return base / "智云登录冷却.json"


def load_login_cooldown(cfg: dict, root: Path | None = None) -> dict:
    """短退避状态：fails/temp_fails/cred_fails/until_ts/error_kind/needs_credential_check/last_success_ts。"""
    p = _login_cooldown_path(cfg, root)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def clear_login_cooldown(cfg: dict, root: Path | None = None) -> None:
    """登录成功：清失败计数/短退避；保留既有 last_success_ts（登录≠数据成功）。"""
    p = _login_cooldown_path(cfg, root)
    prev = load_login_cooldown(cfg, root)
    out: dict = {
        "fails": 0,
        "temp_fails": 0,
        "cred_fails": 0,
        "until_ts": 0,
        "active": False,
        "needs_credential_check": False,
        "error_kind": "",
        "last_error": "",
    }
    # 仅保留历史成功时间；无则不伪造（由 record_fetch_success 在四源成功时写入）
    if prev.get("last_success_ts"):
        out["last_success_ts"] = prev["last_success_ts"]
    if prev.get("last_success_at"):
        out["last_success_at"] = prev["last_success_at"]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(out, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass


def record_fetch_success(
    cfg: dict, root: Path | None = None, *, now_ts: float | None = None
) -> dict:
    """四源抓取成功且完整性通过：刷新最近成功时间，并清短退避/错态。

    与 clear_login_cooldown 区分：后者仅登录成功；本函数才是 48h 新鲜度的权威写入点。
    """
    import time

    now = float(now_ts if now_ts is not None else time.time())
    p = _login_cooldown_path(cfg, root)
    out = {
        "fails": 0,
        "temp_fails": 0,
        "cred_fails": 0,
        "until_ts": 0,
        "active": False,
        "needs_credential_check": False,
        "error_kind": "",
        "last_error": "",
        "last_success_ts": now,
        "last_success_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return out


def register_login_failure(cfg: dict, root: Path | None, err: str) -> dict:
    """连败累计；达阈 → **仅短退避**（默认 5min，上限 15min），绝不 24h 停抓。

    网络/超时/5xx/token 临时失效 → temporary，不累计为凭据失败。
    明确账号/密码/权限错误 → credential，提示人工检查，仍短退避。
    """
    from ingest.fetch_policy import next_backoff_state

    st = load_login_cooldown(cfg, root)
    out = next_backoff_state(st, err, cfg=cfg)
    # 保留上次成功时间戳（供 48h 新鲜度）
    if st.get("last_success_ts"):
        out["last_success_ts"] = st.get("last_success_ts")
    if st.get("last_success_at"):
        out["last_success_at"] = st.get("last_success_at")
    p = _login_cooldown_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def login_cooldown_active(cfg: dict, root: Path | None = None) -> dict | None:
    """短退避窗口内 active；过期返回 None（下一定时槽可再试）。"""
    from ingest.fetch_policy import is_backoff_active

    st = load_login_cooldown(cfg, root)
    if is_backoff_active(st):
        st = dict(st)
        st["active"] = True
        st["backoff_kind"] = st.get("backoff_kind") or "short"
        return st
    return None


def last_fetch_success_ts(cfg: dict, root: Path | None = None) -> float | None:
    st = load_login_cooldown(cfg, root)
    try:
        v = float(st.get("last_success_ts") or 0)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _auto_login(zy: dict, cfg: dict, root: Path | None) -> str:
    """账号密码登录换新 token（顺带取 account_id→换账号零配置），回写配置 + 更新内存 zy。返回 token。"""
    from ingest import login_zhiyun

    cd = login_cooldown_active(cfg, root)
    if cd:
        if cd.get("needs_credential_check") or cd.get("error_kind") == "credential":
            raise RuntimeError(
                "智云登录短退避中（凭据疑似错误，请人工检查账号密码；稍后定时槽会再试）"
            )
        raise RuntimeError(
            "智云登录短退避中（临时网络/上游波动，稍后定时槽自动恢复，非 24h 停抓）"
        )
    try:
        token, account_id = login_zhiyun.login(zy)
    except Exception as e:
        register_login_failure(cfg, root, f"{type(e).__name__}: {e}")
        raise
    clear_login_cooldown(cfg, root)
    zy["md_pss_id"] = token
    if account_id:
        zy["account_id"] = account_id
    _save_session(cfg, root, token, account_id)
    return token


def _is_auth_expired(j) -> bool:
    """智云 token 失效时回 HTTP 200 但 state==0 且提示退出/登录。"""
    if not isinstance(j, dict) or j.get("state") not in (0, "0"):
        return False
    msg = str(j.get("exception") or j.get("message") or "")
    return ("登录" in msg) or ("退出" in msg) or ("登陆" in msg)


def _make_post(zy: dict, cfg: dict | None = None, root: Path | None = None):
    """构造 post(path, body)。token 失效（state==0 需登录 / HTTP 401）时自动重登一次。

    cfg 为 None 时不自动重登（离线测试用桩注入，不走这里）。
    """
    import requests

    state = {"token": zy.get("md_pss_id", "")}

    def _headers():
        return {
            "Content-Type": "application/json",
            "Authorization": f"md_pss_id {state['token']}",
            "AccountId": zy.get("account_id", ""),
            "X-Requested-With": "XMLHttpRequest",
        }

    def _do(path, body):
        r = requests.post(f"{zy['base_url']}/wwwapi/{path}", headers=_headers(), json=body, timeout=120)
        return r

    def post(path: str, body: dict) -> dict:
        r = _do(path, body)
        need_relogin = r.status_code == 401
        if not need_relogin and r.status_code == 200:
            try:
                need_relogin = _is_auth_expired(r.json())
            except ValueError:
                need_relogin = False
        if need_relogin and cfg is not None:
            if state.get("login_failed"):  # 本轮已登录失败过：不再反复试（慢+密码错反复试有锁号风险）
                raise RuntimeError("智云登录失败（本轮更新不再重试，请检查账号密码）")
            try:
                state["token"] = _auto_login(zy, cfg, root)  # 失效→重登一次
            except Exception:
                state["login_failed"] = True
                raise
            r = _do(path, body)
        r.raise_for_status()
        return r.json()

    return post


def _dest_path(cfg: dict, source: str, root: Path | None) -> Path:
    name = cfg["files"][SOURCES[source]["file_key"]]
    if not name.endswith(".xlsx"):
        name += ".xlsx"  # project_detail_stem 是词干
    return loaders.data_dir(cfg, root) / name


def _last_counts_path(cfg: dict, root: Path | None) -> Path:
    """上次成功抓取各源行数（任务书30·0.5 骤降告警）。gitignore 数据目录内。"""
    return loaders.data_dir(cfg, root) / "智云抓数上次行数.json"


def _baseline7_path(cfg: dict, root: Path | None) -> Path:
    """7 日滚动基线：{source: {ts, rows}}。任务书66·D。"""
    return loaders.data_dir(cfg, root) / "智云抓数7日基线.json"


def load_last_row_counts(cfg: dict, root: Path | None = None) -> dict[str, int]:
    p = _last_counts_path(cfg, root)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def save_last_row_count(cfg: dict, source: str, n: int, root: Path | None = None) -> None:
    import time

    counts = load_last_row_counts(cfg, root)
    counts[source] = int(n)
    p = _last_counts_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    # 7 日基线：若无基线或已超过 7 天则刷新快照
    bpath = _baseline7_path(cfg, root)
    try:
        base = json.loads(bpath.read_text(encoding="utf-8")) if bpath.is_file() else {}
    except (OSError, ValueError, TypeError):
        base = {}
    if not isinstance(base, dict):
        base = {}
    now = time.time()
    ent = base.get(source) if isinstance(base.get(source), dict) else {}
    ts = float(ent.get("ts") or 0)
    if not ts or (now - ts) >= 7 * 86400:
        base[source] = {"ts": now, "rows": int(n)}
        bpath.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")


def load_baseline7_rows(cfg: dict, source: str, root: Path | None = None) -> int | None:
    """7 日前左右基线行数；无/过旧返回 None（首跑不误报）。"""
    import time

    p = _baseline7_path(cfg, root)
    if not p.is_file():
        return None
    try:
        base = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    ent = base.get(source) if isinstance(base, dict) else None
    if not isinstance(ent, dict):
        return None
    try:
        rows = int(ent.get("rows"))
        ts = float(ent.get("ts") or 0)
    except (TypeError, ValueError):
        return None
    # 基线至少 6 天前才参与「7 日」对比；过新当无
    if not ts or (time.time() - ts) < 6 * 86400:
        return None
    return rows


def row_drop_ratio(cfg: dict) -> float:
    """骤降阈值，默认 30%。config.zhiyun_row_drop_ratio 可调（0~1）。"""
    try:
        r = float(cfg.get("zhiyun_row_drop_ratio", DEFAULT_ROW_DROP_RATIO))
    except (TypeError, ValueError):
        r = DEFAULT_ROW_DROP_RATIO
    if r < 0:
        return 0.0
    if r > 1:
        return 1.0
    return r


def check_row_drop(prev: int | None, curr: int, ratio: float) -> str | None:
    """若 curr 比 prev 少超过 ratio，返回告警文案；否则 None。prev 空/0 不告警。"""
    if not prev or prev <= 0 or ratio <= 0:
        return None
    if curr >= prev:
        return None
    drop = (prev - curr) / float(prev)
    if drop > ratio + 1e-12:
        pct = int(round(ratio * 100))
        return f"行数骤降：上次成功 {prev} → 本次 {curr}（降幅 {drop:.0%} > 阈值 {pct}%）"
    return None


def _fetch_fallback(local: Path, reason: str) -> dict:
    if local.exists():
        return {"status": "local_fallback", "detail": f"{reason}，用数据目录现有文件"}
    return {"status": "no_source", "detail": f"{reason}，且无本地文件"}


def _date_control_dup_info(controls, date_col: str) -> list[str]:
    """同名日期控件多于一个：仅 info（2.2.8 不进 warnings、不驱动黄红），防顺序变了无声换列。"""
    if not date_col:
        return []
    dups = controls_with_name(controls, date_col)
    if len(dups) <= 1:
        return []
    ids = ",".join(str(c.get("controlId") or "")[:12] for c in dups)
    return [
        f"表模板「{date_col}」同名控件 {len(dups)} 个，已按规则取首个有值"
        f"（controlId≈{ids}…）"
    ]


# 兼容旧名（测试/外部若仍引用）
_date_control_dup_warnings = _date_control_dup_info


def _fetch_and_write_source(cfg, source, root, post, zy, tbl, local) -> dict:  # noqa: C901
    """在线抓取→校验→写盘；失败用 _fetch_fallback。"""
    info = post(
        "Worksheet/getWorksheetInfo",
        {"worksheetId": tbl["worksheetId"], "appId": zy["app_id"], "getTemplate": True},
    )
    controls = info["data"]["template"]["controls"]
    since = cfg.get("zhiyun_since") if cfg.get("zhiyun_since") is not None else "auto"
    date_col = cfg["columns"].get(SOURCES[source]["date_col_key"], "")
    info_msgs = list(_date_control_dup_info(controls, date_col))
    warnings: list[str] = []
    fc = build_date_since_filter(controls, date_col, since)
    rows = fetch_all_rows(post, tbl["worksheetId"], zy["app_id"], filter_controls=fc)
    records = rows_to_records(rows, controls)
    # 2.6.7 C-1 / C-13：0 行与缺列拆分支——0 行禁止静默沿用旧 xlsx
    if len(records) == 0:
        import datetime as _dt

        mon = _dt.date.today().month
        # 2.6.9 S5：0 行禁止 unlink；重命名为 .stale-<ts> 保留证据，下游不读 stale
        stale_name = local.name
        try:
            if local.exists():
                ts = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
                stale = local.with_name(f"{local.name}.stale-{ts}")
                local.rename(stale)
                stale_name = stale.name
        except OSError:
            pass
        save_last_row_count(cfg, source, 0, root)
        if mon == 1:
            # 1 月 0 行：信息级（新年正常空），不抬体检红
            return {
                "status": "fetched",
                "detail": f"新年正常空：1 月抓到 0 行（本地旧文件已标 stale 保留）→ {stale_name}",
                "rows": 0,
                "info": ["新年正常空（1 月 0 行，不判抓取失败）"] + info_msgs,
            }
        # 非 1 月 0 行：抬体检红 + 告警，绝不 fallback 旧文件
        return {
            "status": "empty_fetch",
            "detail": f"智云抓取 0 行（非1月），已拒沿用并将旧文件标 stale 保留 → {stale_name}",
            "rows": 0,
            "warnings": [f"{source} 智云抓取 0 行，未沿用本地旧 xlsx，请检查过滤条件/账号权限"],
            "info": info_msgs,
        }
    missing = check_required_columns(records, cfg, source)
    if missing:
        # 缺列：维持原状——可 fallback 本地旧文件
        return _fetch_fallback(local, f"抓到 {len(records)} 行但缺必需列 {missing}（可能无权限/表不对）")
    # 行数门槛护栏（智云配置.json tables.<源>.min_rows）：抓到的行数异常少=账号行级权限不足
    min_rows = int(tbl.get("min_rows") or 0)
    if len(records) < min_rows:
        return _fetch_fallback(
            local, f"只抓到 {len(records)} 行 < 门槛 {min_rows}（疑似账号行级权限不足、只看到自己的记录）"
        )
    prev_counts = load_last_row_counts(cfg, root)
    drop_msg = check_row_drop(prev_counts.get(source), len(records), row_drop_ratio(cfg))
    if drop_msg:
        warnings.append(drop_msg)
    # 任务书66·D：与约 7 天前基线累计对比（同阈值）
    b7 = load_baseline7_rows(cfg, source, root)
    drop7 = check_row_drop(b7, len(records), row_drop_ratio(cfg))
    if drop7:
        warnings.append("相对7日基线·" + drop7)
    write_records_xlsx(records, local)
    save_last_row_count(cfg, source, len(records), root)
    detail = f"智云抓取 {len(records)} 行 → {local.name}"
    if warnings:
        detail += "；" + "；".join(warnings)
    out = {"status": "fetched", "detail": detail, "rows": len(records)}
    if warnings:
        out["warnings"] = warnings
    if info_msgs:
        out["info"] = info_msgs
    return out


def fetch_source(cfg: dict, source: str, root: Path | None = None, post=None, zy: dict | None = None) -> dict:
    """抓一个源到进料口。返回 {status, detail, ...}，三态同 fetch_ledger，永不抛异常。"""
    local = _dest_path(cfg, source, root)
    zy = zy or _load_zhiyun_cfg(cfg, root)
    if not zy.get("base_url"):
        return _fetch_fallback(local, "智云服务器地址为空（管理端「设置→智云账号」可填）")
    tbl = (zy.get("tables") or {}).get(source) or {}
    if not tbl.get("worksheetId"):
        return _fetch_fallback(local, f"智云配置缺 tables.{source}.worksheetId")
    try:
        post = post or _make_post(zy, cfg, root)
        return _fetch_and_write_source(cfg, source, root, post, zy, tbl, local)
    except Exception as e:  # noqa: BLE001 铁律：抓失败不中断管道
        return _fetch_fallback(local, f"智云抓取失败（{type(e).__name__}: {e}）")


def _server_reachable(base_url: str, timeout: int = 5, *, worksheet_probe: dict | None = None) -> bool:
    """连通性探测：优先轻量 POST Worksheet API（任务书66·D），否则回落 GET 根 URL。"""
    import requests

    if worksheet_probe and worksheet_probe.get("worksheetId") and worksheet_probe.get("app_id"):
        try:
            r = requests.post(
                f"{base_url.rstrip('/')}/wwwapi/Worksheet/getWorksheetInfo",
                json={
                    "worksheetId": worksheet_probe["worksheetId"],
                    "appId": worksheet_probe["app_id"],
                    "getTemplate": True,
                },
                timeout=timeout,
            )
            # 401/业务鉴权失败也算「服务器可达」
            return r.status_code < 500
        except Exception:  # noqa: BLE001
            return False
    try:
        requests.get(base_url, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def _source_entries(results: dict) -> list[tuple[str, dict]]:
    return [(k, v) for k, v in results.items() if not str(k).startswith("_") and isinstance(v, dict)]


def _integrity_flags_from_results(results: dict) -> dict[str, bool]:
    """从各源 status/detail 推断完整性问题（缺列 / min_rows / 阻断性 0 行）。"""
    zero_rows = False
    missing_columns = False
    below_min_rows = False
    for _s, r in _source_entries(results):
        st = str(r.get("status") or "")
        det = str(r.get("detail") or "")
        if st == "empty_fetch":
            zero_rows = True
        if "缺必需列" in det:
            missing_columns = True
        if "门槛" in det or "行级权限" in det:
            below_min_rows = True
    return {
        "zero_rows_blocking": zero_rows,
        "missing_columns": missing_columns,
        "below_min_rows": below_min_rows,
    }


def _all_sources_fetched_ok(results: dict) -> bool:
    """四源均为 fetched 且无完整性降级文案。"""
    flags = _integrity_flags_from_results(results)
    if any(flags.values()):
        return False
    entries = _source_entries(results)
    if len(entries) < len(SOURCES):
        return False
    return all(str(r.get("status") or "") == "fetched" for _s, r in entries)


def assemble_fetch_freshness(
    cfg: dict,
    root: Path | None,
    results: dict,
    *,
    fetch_ok: bool | None = None,
    now_ts: float | None = None,
) -> dict:
    """统一组装 data_freshness（失败/成功路径共用，供 fetch_all 与测试）。"""
    import time

    from ingest.fetch_policy import classify_source_data_state

    flags = _integrity_flags_from_results(results)
    if fetch_ok is None:
        fetch_ok = _all_sources_fetched_ok(results)
    has_any_local = any(_dest_path(cfg, s, root).exists() for s in SOURCES)
    last_ok = last_fetch_success_ts(cfg, root)
    integrity_bad = (
        flags["zero_rows_blocking"]
        or flags["missing_columns"]
        or flags["below_min_rows"]
    )
    return classify_source_data_state(
        fetch_ok=bool(fetch_ok) and not integrity_bad,
        last_success_ts=last_ok,
        now_ts=float(now_ts if now_ts is not None else time.time()),
        has_local_copy=has_any_local,
        integrity_ok=not integrity_bad,
        zero_rows_blocking=flags["zero_rows_blocking"],
        missing_columns=flags["missing_columns"],
        below_min_rows=flags["below_min_rows"],
    )


def _fallback_all_sources(cfg: dict, root: Path | None, detail: str) -> dict[str, dict]:
    return {
        s: {
            "status": "local_fallback" if _dest_path(cfg, s, root).exists() else "no_source",
            "detail": detail,
        }
        for s in SOURCES
    }


def _attach_freshness(
    cfg: dict, root: Path | None, out: dict, *, fetch_ok: bool
) -> dict[str, dict]:
    out["_meta_freshness"] = assemble_fetch_freshness(  # type: ignore[assignment]
        cfg, root, out, fetch_ok=fetch_ok
    )
    return out


def _cooldown_skip_all(cfg: dict, root: Path | None, cd: dict) -> dict[str, dict]:
    """短退避窗口内：四源降级 + freshness（不真登）。"""
    needs_cred = bool(cd.get("needs_credential_check") or cd.get("error_kind") == "credential")
    if needs_cred:
        det = "智云凭据疑似错误（短退避中，请人工检查账号密码；稍后定时槽会再试，非 24h 停抓）"
    else:
        det = "智云临时不可用（短退避中，网络/上游波动；稍后定时槽自动恢复）"
    kind = cd.get("error_kind") or ("credential" if needs_cred else "temporary")
    out = {
        s: {
            "status": "local_fallback" if _dest_path(cfg, s, root).exists() else "no_source",
            "detail": det,
            "login_cooldown": True,
            "error_kind": kind,
        }
        for s in SOURCES
    }
    out["_meta_cooldown"] = cd  # type: ignore[assignment]
    return _attach_freshness(cfg, root, out, fetch_ok=False)


def _login_fail_all(cfg: dict, root: Path | None, err: BaseException) -> dict[str, dict]:
    """首次自动登录失败：四源整体降级（不逐源重试）。"""
    det = f"智云自动登录失败（{type(err).__name__}: {err}），用数据目录现有文件（体检黄）"
    out = _fallback_all_sources(cfg, root, det)
    cool = load_login_cooldown(cfg, root)
    if cool:
        out["_meta_cooldown"] = cool  # type: ignore[assignment]
    return _attach_freshness(cfg, root, out, fetch_ok=False)


def _finalize_source_results(
    cfg: dict, root: Path | None, results: dict[str, dict]
) -> dict[str, dict]:
    """成功则写 last_success；无论成败均挂 _meta_freshness。"""
    ok = _all_sources_fetched_ok(results)
    if ok:
        record_fetch_success(cfg, root)
    return _attach_freshness(cfg, root, results, fetch_ok=ok)


def _worksheet_probe(zy: dict) -> dict | None:
    tbl0 = next(iter((zy.get("tables") or {}).values()), None) or {}
    if tbl0.get("worksheetId"):
        return {"worksheetId": tbl0["worksheetId"], "app_id": zy.get("app_id")}
    return None


def _make_shared_post_or_login_fail(
    zy: dict, cfg: dict, root: Path | None
) -> tuple[object | None, dict[str, dict] | None]:
    """有账号密码时构造共享 post；空 token 先登录，失败返回 (None, fallback_dict)。"""
    if not (zy.get("base_url") and zy.get("username") and zy.get("password")):
        return None, None
    if not zy.get("md_pss_id"):
        try:
            _auto_login(zy, cfg, root)
        except Exception as e:  # noqa: BLE001
            return None, _login_fail_all(cfg, root, e)
    return _make_post(zy, cfg, root), None


def fetch_all(cfg: dict, root: Path | None = None, today=None) -> dict[str, dict]:
    """抓全部四源，返回 {source: {status, detail}}。供 pipeline/体检使用。

    token 为空时先自动登录一次；四源共享同一个带自动重登的 post（不重复登录）。
    内网不可达/登录失败则各源自然降级为 local_fallback（体检黄），不中断管道。
    每次成功且完整性通过写入 last_success_ts；所有失败路径统一产出 _meta_freshness。
    任务书64·E：写盘前若跨年会截断旧年 xlsx，先做年度归档（只一次）。
    """
    # 跨年归档由管道入口 ingest.build_std_db 在抓取前单独调用（不污染本 dict 的源键）
    zy = _load_zhiyun_cfg(cfg, root)
    cd = login_cooldown_active(cfg, root) if zy else None
    if cd:
        return _cooldown_skip_all(cfg, root, cd)
    probe = _worksheet_probe(zy) if zy else None
    if zy and zy.get("base_url") and not _server_reachable(zy["base_url"], worksheet_probe=probe):
        det = "智云服务器不可达（不在公司内网？），用数据目录现有文件（体检黄）"
        return _attach_freshness(
            cfg, root, _fallback_all_sources(cfg, root, det), fetch_ok=False
        )
    post, login_fail = _make_shared_post_or_login_fail(zy, cfg, root) if zy else (None, None)
    if login_fail is not None:
        return login_fail
    results = {s: fetch_source(cfg, s, root, post=post, zy=zy) for s in SOURCES}
    return _finalize_source_results(cfg, root, results)
