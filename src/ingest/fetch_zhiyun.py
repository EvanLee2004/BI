#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智云（明道云）四源自动抓取：调内部接口拉表 → 产出与人工导出同构的 xlsx 写进料口 数据/。

架构契约（07 迭代计划）：
- 产物 = 与人工导出同列名的 xlsx，落 数据/<下单|回款记录|项目明细|内部译员>.xlsx；下游 readers 以下零改。
- 三态返回（同 fetch.fetch_ledger）：fetched / local_fallback（保留上次文件+体检黄）/ no_source；永不抛异常中断管道。
- **连接配置分两层（2026-07-13 明昊拍板）**：服务器地址/appId/四表 worksheetId = 内置默认 `ZHIYUN_DEFAULTS`
  随代码进公开库（部署机开箱免拷模板）；**账号/密码/md_pss_id cookie/account_id 绝不进库**，只在
  数据/智云配置.json（gitignore，管理端「设置→智云账号」填）。文件里同名非空字段覆盖内置默认。
- 必需列（config.columns 声明）抓完必须在场，缺了该表按失败处理——铁律"必需列缺失即报错，不静默算 0"。

数据/智云配置.json（本地覆盖层·可只有账号密码）：
{
  "username": "...", "password": "...",   // 管理端设置页填
  "md_pss_id": "<登录cookie>",            // 程序自动维护
  "account_id": "<账号GUID>",             // 登录时自动获取
  "base_url" / "app_id" / "tables": ...   // 可选：非空则覆盖内置默认（换服务器/换表用）
}
"""

from __future__ import annotations

import json
from pathlib import Path

import loaders

# 每个源：进料口文件名的 config.files 键 + 必需列的 config.columns 键
SOURCES = {
    "orders": {"file_key": "orders", "required_cols": ["order_amount", "order_date"], "date_col_key": "order_date"},
    "receipts": {
        "file_key": "receipts",
        "required_cols": ["receipt_amount", "receipt_date"],
        "date_col_key": "receipt_date",
    },
    "project_detail": {
        "file_key": "project_detail_stem",
        "required_cols": ["project_delivery_date", "project_revenue", "project_cost", "project_line"],
        "date_col_key": "project_delivery_date",
    },
    "inhouse": {
        "file_key": "inhouse",
        "required_cols": ["inhouse_amount", "inhouse_date", "inhouse_type"],
        "date_col_key": "inhouse_date",
    },
}
# date_col_key = 该源"归属月"所依据的日期字段（与清洗层 normalize 一致）；
# 服务器端只抓这个日期 **>= config.zhiyun_since** 的行（只要当年、少抓快抓）。
# 实现：filterType=13 实测为**严格大于** value，故 value 传 since 的前一天（见 build_date_since_filter）。
# 日期为空的行本就归属月=None、看板不计入任何月份，被服务器过滤掉不影响口径。

PAGE_SIZE = 1000
MAX_PAGES = 500  # 翻页安全上限（50万行，远超任何表；防接口异常时死循环）
# 任务书30 批次0.5 / 任务书35 补做：本次成功抓取行数比上次少超此比例 → 体检黄（不拦）
DEFAULT_ROW_DROP_RATIO = 0.30


# ---------- 纯函数层（离线可测） ----------


def parse_cell(cell, ctrl: dict) -> str:
    """按明道云字段类型把单元格解析成导出同款文本（成员/部门/选项/关联通用，解析失败回退原串）。"""
    if cell in (None, ""):
        return ""
    if isinstance(cell, (list, dict)):  # 已是对象（个别接口不回 JSON 串）直接走结构解析
        v, s = cell, json.dumps(cell, ensure_ascii=False)
    else:
        s = str(cell)
        if s[:1] not in ("[", "{"):
            return s
        try:
            v = json.loads(s)
        except (ValueError, TypeError):
            return s
    if not isinstance(v, list):
        return s
    if v and isinstance(v[0], str):  # 选项 key → 中文
        m = {o["key"]: o["value"] for o in (ctrl.get("options") or [])}
        return "/".join(m.get(k, k) for k in v)
    out = []
    for x in v:  # 成员/部门/关联 = 对象数组
        if isinstance(x, dict):
            out.append(
                x.get("fullname")
                or x.get("departmentName")
                or x.get("name")
                or x.get("organizeName")
                or x.get("sourcevalue")
                or ""
            )
        else:
            out.append(str(x))
    return "/".join(o for o in out if o)


def rows_to_records(rows: list[dict], controls: list[dict]) -> list[dict[str, str]]:
    """原始行（controlId 为键）→ 中文列名记录（全字段，等价人工导出勾"导出所有字段"）。

    ⚠同名列合并：智云可有多个同名控件（如两个"整单交付日期"，一个有值一个空）。
    按控件顺序取**首个非空**值，空值不覆盖已有非空——否则空的同名列会把有值的清掉
    （2026-07-10 踩坑：项目明细归月依据"整单交付日期"因此被清空、收入归不到月）。
    """
    cols = [(c["controlName"], c) for c in controls if c.get("controlName")]
    out = []
    for row in rows:
        rec: dict[str, str] = {}
        for name, c in cols:
            val = parse_cell(row.get(c["controlId"]), c)
            if name not in rec or (not rec[name] and val):
                rec[name] = val
        out.append(rec)
    return out


def check_required_columns(records: list[dict[str, str]], cfg: dict, source: str) -> list[str]:
    """返回缺失的必需列名列表（空=齐）。records 为空也按缺列处理。"""
    wanted = [cfg["columns"][k] for k in SOURCES[source]["required_cols"]]
    have = set(records[0].keys()) if records else set()
    return [w for w in wanted if w not in have]


def resolve_zhiyun_since(since: str | None, today=None) -> str:
    """规范化 config.zhiyun_since → 'YYYY-MM-DD' 或 ''（空=全量不过滤）。

    - ``"auto"``（大小写不敏感）：当年元旦（today.year-01-01；today 可注入便于单测）
    - 空串 / None：全量（不过滤）——与历史「留空=抓全量」一致
    - 写死 ``YYYY-MM-DD``：原样返回（兼容补历史）
    - 其它非法串：返回空（build_date_since_filter 跳过过滤）
    """
    from datetime import date as _date

    if since is None:
        return ""
    s = str(since).strip()
    if not s:
        return ""
    if s.lower() == "auto":
        t = today if today is not None else _date.today()
        return f"{int(t.year):04d}-01-01"
    # 写死日期：只认前 10 位 YYYY-MM-DD 形态
    head = s[:10]
    try:
        from datetime import datetime as _dt

        _dt.strptime(head, "%Y-%m-%d")
        return head
    except ValueError:
        return ""


def _since_filter_value(since: str) -> str:
    """zhiyun_since → filterType=13 的 value。

    2026-07-16 真实 API 实测：filterType=13 为**严格大于** value（不是 >=）。
    要包含 since 当天，value 必须传 since 的**前一天**（datetime 计算，禁止字符串硬减）。
    since 须已是 YYYY-MM-DD（先经 resolve_zhiyun_since）。
    """
    from datetime import datetime, timedelta

    s = str(since).strip()[:10]
    d = datetime.strptime(s, "%Y-%m-%d").date()
    return (d - timedelta(days=1)).isoformat()


def controls_with_name(controls: list[dict], name: str) -> list[dict]:
    """同名控件列表（顺序=模板顺序；抓取/过滤取第一个）。"""
    return [c for c in (controls or []) if c.get("controlName") == name]


def build_date_since_filter(controls: list[dict], date_col_name: str, since: str, today=None) -> list[dict]:
    """构造「该日期字段 **>= since**」的服务器端过滤。

    ⚠ filterType=13 实测语义=**严格大于** value（2026-07-16 陆总号 GetFilterRows 对账）：
    value=since 会丢掉 since 当天行；故 value=since 前一天，整体效果等价于 >= since。
    since 支持 ``"auto"``=当年元旦（见 resolve_zhiyun_since）；空/解析失败 → []（不过滤）。
    同名列多于一个时用**第一个**（与 rows_to_records 首个非空策略对齐）。
    """
    resolved = resolve_zhiyun_since(since, today=today)
    if not resolved or not date_col_name:
        return []
    matches = controls_with_name(controls, date_col_name)
    if not matches:
        return []
    ctrl = matches[0]
    try:
        value = _since_filter_value(resolved)
    except ValueError:
        return []  # since 非法日期 → 不过滤，避免整表抓挂
    return [
        {
            "controlId": ctrl["controlId"],
            "dataType": ctrl.get("type", 15),
            "spec": {},
            "filterType": 13,
            "dateRange": 0,
            "value": value,
            "values": [],
        }
    ]


def _extract_row_total(page_data: dict) -> int | None:
    """首页 GetFilterRows data 里取总条数。明道常见 count；兼容 total/totalNum。"""
    if not isinstance(page_data, dict):
        return None
    for k in ("count", "total", "totalNum", "allCount"):
        if k not in page_data or page_data[k] is None or page_data[k] == "":
            continue
        try:
            return int(page_data[k])
        except (TypeError, ValueError):
            continue
    return None


def fetch_all_rows(post, worksheet_id: str, app_id: str, filter_controls: list[dict] | None = None) -> list[dict]:
    """翻页拉全量。post(path, body)->dict 由调用方注入（真实 requests 或测试桩）。

    filter_controls 非空时只抓命中过滤的行（如日期 >= zhiyun_since）。
    任务书30·批次0.5 / 任务书35 补做：首页 notGetTotal=false 取 total，
    抓完 len(out) 必须等于 total，差了 raise（整表按失败，不静默残缺）。
    """
    fc = filter_controls or []
    out, page = [], 1
    declared_total: int | None = None
    while page <= MAX_PAGES:
        body = {
            "worksheetId": worksheet_id,
            "appId": app_id,
            "pageSize": PAGE_SIZE,
            "pageIndex": page,
            "status": 1,
            "sortControls": [],
            "notGetTotal": page > 1,
            "searchType": 1,
            "keyWords": "",
            "filterControls": fc,
            "fastFilters": [],
            "navGroupFilters": [],
        }
        d = post("Worksheet/GetFilterRows", body).get("data") or {}
        rows = d.get("data") or []
        if page == 1:
            declared_total = _extract_row_total(d)
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        page += 1
    else:
        raise RuntimeError(f"翻页超过安全上限 {MAX_PAGES} 页仍未拉完，接口行为异常（拒收疑似坏数据）")
    if declared_total is not None and len(out) != declared_total:
        raise RuntimeError(
            f"行数对账失败：接口 total={declared_total}，实际抓到 {len(out)} 行（疑似翻页残缺，拒收）"
        )
    return out


def write_records_xlsx(records: list[dict[str, str]], dest: Path) -> None:
    """写成与人工导出同构的 xlsx（单 sheet、首行表头）。原子替换：先写临时文件再换名。"""
    if not records:
        raise ValueError("空数据不落盘（调用方应先走必需列护栏）")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    headers = list(records[0].keys())
    ws.append(headers)
    for r in records:
        ws.append([r.get(h, "") for h in headers])
    tmp = dest.with_suffix(".tmp.xlsx")
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(tmp)
    tmp.replace(dest)


# ---------- 接线层（要内网 + 智云配置.json） ----------

# 内置默认连接配置（2026-07-13 明昊拍板进公开库：内网地址+表ID随代码走，部署机开箱免拷模板；
# 账号/密码/cookie 仍绝不进库——只在 数据/智云配置.json（gitignore）里，管理端设置页填）。
# 数据/智云配置.json 里同名字段非空则覆盖这里（老部署/换表零冲突）。
ZHIYUN_DEFAULTS: dict = {
    "base_url": "http://192.168.10.167:18880",
    "app_id": "6ff4fb2e-e68c-4ee9-83a0-836de8f72c11",
    "tables": {
        "orders": {"worksheetId": "6501688ebf25d7b91abdb465"},
        "receipts": {"worksheetId": "6555d2b1f9460e517040ba6c"},
        "project_detail": {"worksheetId": "65a4f4afdd2dc6df7283bf1a"},
        # 「任务」表=内部译员真源；min_rows 护栏：行级权限不足账号只抓到自己的任务（如 85 行）
        # → 行数低于门槛当失败降级、不覆盖现有文件；换全量权限账号自然全绿。
        "inhouse": {"worksheetId": "654da962f9460e517040a9f0", "min_rows": 1000},
    },
}


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
    """{fails, until_ts, last_error}；until_ts 为 epoch 秒。"""
    p = _login_cooldown_path(cfg, root)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def clear_login_cooldown(cfg: dict, root: Path | None = None) -> None:
    p = _login_cooldown_path(cfg, root)
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass


def register_login_failure(cfg: dict, root: Path | None, err: str) -> dict:
    """连败累计；达阈（默认 3）→ 冷却 24h。返回冷却状态 dict。"""
    import time

    max_f = int(cfg.get("zhiyun_login_max_failures", 3) or 3)
    cool_h = float(cfg.get("zhiyun_login_cooldown_hours", 24) or 24)
    st = load_login_cooldown(cfg, root)
    fails = int(st.get("fails") or 0) + 1
    out = {"fails": fails, "last_error": str(err)[:200], "until_ts": st.get("until_ts") or 0}
    if fails >= max_f:
        out["until_ts"] = time.time() + cool_h * 3600
        out["active"] = True
    p = _login_cooldown_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def login_cooldown_active(cfg: dict, root: Path | None = None) -> dict | None:
    import time

    st = load_login_cooldown(cfg, root)
    until = float(st.get("until_ts") or 0)
    if until and time.time() < until:
        st = dict(st)
        st["active"] = True
        return st
    return None


def _auto_login(zy: dict, cfg: dict, root: Path | None) -> str:
    """账号密码登录换新 token（顺带取 account_id→换账号零配置），回写配置 + 更新内存 zy。返回 token。"""
    from ingest import login_zhiyun

    if login_cooldown_active(cfg, root):
        raise RuntimeError("智云登录冷却中（连续失败达阈，24h 内不再真实登录；请人工检查凭据）")
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
        return {"status": "local_fallback", "detail": f"{reason}，用数据目录现有文件（体检黄）"}
    return {"status": "no_source", "detail": f"{reason}，且无本地文件"}


def _date_control_dup_warnings(controls, date_col: str) -> list[str]:
    """同名日期控件多于一个：观察项（黄），防顺序变了无声换列。"""
    if not date_col:
        return []
    dups = controls_with_name(controls, date_col)
    if len(dups) <= 1:
        return []
    ids = ",".join(str(c.get("controlId") or "")[:12] for c in dups)
    return [
        f"表模板「{date_col}」同名控件 {len(dups)} 个（controlId≈{ids}…）；"
        f"过滤/取值用第一个，请确认未换序"
    ]


def _fetch_and_write_source(cfg, source, root, post, zy, tbl, local) -> dict:
    """在线抓取→校验→写盘；失败用 _fetch_fallback。"""
    info = post(
        "Worksheet/getWorksheetInfo",
        {"worksheetId": tbl["worksheetId"], "appId": zy["app_id"], "getTemplate": True},
    )
    controls = info["data"]["template"]["controls"]
    since = cfg.get("zhiyun_since") if cfg.get("zhiyun_since") is not None else "auto"
    date_col = cfg["columns"].get(SOURCES[source]["date_col_key"], "")
    warnings = _date_control_dup_warnings(controls, date_col)
    fc = build_date_since_filter(controls, date_col, since)
    rows = fetch_all_rows(post, tbl["worksheetId"], zy["app_id"], filter_controls=fc)
    records = rows_to_records(rows, controls)
    missing = check_required_columns(records, cfg, source)
    if missing:
        return _fetch_fallback(local, f"抓到 {len(records)} 行但缺必需列 {missing}（可能无权限/表不对）")
    # 行数门槛护栏（智云配置.json tables.<源>.min_rows）：抓到的行数异常少=账号行级权限不足
    min_rows = int(tbl.get("min_rows") or 0)
    if len(records) < min_rows:
        return _fetch_fallback(
            local, f"只抓到 {len(records)} 行 < 门槛 {min_rows}（疑似账号行级权限不足、只看到自己的记录）"
        )
    # 新年 1 月 0 行：信息级，不当地抓取失败黄
    import datetime as _dt

    mon = _dt.date.today().month
    if len(records) == 0 and mon == 1:
        write_records_xlsx(records, local)
        save_last_row_count(cfg, source, 0, root)
        return {
            "status": "fetched",
            "detail": f"新年正常空：1 月抓到 0 行 → {local.name}",
            "rows": 0,
            "info": ["新年正常空（1 月 0 行，不判抓取失败）"],
        }
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


def fetch_all(cfg: dict, root: Path | None = None, today=None) -> dict[str, dict]:
    """抓全部四源，返回 {source: {status, detail}}。供 pipeline/体检使用。

    token 为空时先自动登录一次；四源共享同一个带自动重登的 post（不重复登录）。
    内网不可达/登录失败则各源自然降级为 local_fallback（体检黄），不中断管道。
    任务书64·E：写盘前若跨年会截断旧年 xlsx，先做年度归档（只一次）。
    """
    # 跨年归档由管道入口 ingest.build_std_db 在抓取前单独调用（不污染本 dict 的源键）
    zy = _load_zhiyun_cfg(cfg, root)
    # 冷却中：不真登，四源降级 + 标记红
    cd = login_cooldown_active(cfg, root) if zy else None
    if cd:
        det = "智云凭据疑似失效（登录冷却中，需人工检查账号密码）"
        out = {
            s: {
                "status": "local_fallback" if _dest_path(cfg, s, root).exists() else "no_source",
                "detail": det,
                "login_cooldown": True,
            }
            for s in SOURCES
        }
        out["_meta_cooldown"] = cd  # type: ignore[assignment]
        return out
    probe = None
    if zy:
        tbl0 = next(iter((zy.get("tables") or {}).values()), None) or {}
        if tbl0.get("worksheetId"):
            probe = {"worksheetId": tbl0["worksheetId"], "app_id": zy.get("app_id")}
    if zy and zy.get("base_url") and not _server_reachable(zy["base_url"], worksheet_probe=probe):
        det = "智云服务器不可达（不在公司内网？），用数据目录现有文件（体检黄）"
        return {
            s: {
                "status": "local_fallback" if _dest_path(cfg, s, root).exists() else "no_source",
                "detail": det,
            }
            for s in SOURCES
        }
    post = None
    if zy and zy.get("base_url") and zy.get("username") and zy.get("password"):
        if not zy.get("md_pss_id"):
            try:
                _auto_login(zy, cfg, root)  # 首次/空 token：先登录
            except Exception as e:  # noqa: BLE001 登录失败→四源整体快速降级
                # ⚠不能把 zy 置 None 后继续调 fetch_source——那样它会自己重读配置再建 post，
                # 四个源各重试一次登录（慢+密码错时反复试有锁号风险）。直接全部降级。
                det = f"智云自动登录失败（{type(e).__name__}: {e}），用数据目录现有文件（体检黄）"
                return {
                    s: {
                        "status": "local_fallback" if _dest_path(cfg, s, root).exists() else "no_source",
                        "detail": det,
                    }
                    for s in SOURCES
                }
        post = _make_post(zy, cfg, root)
    return {s: fetch_source(cfg, s, root, post=post, zy=zy) for s in SOURCES}
