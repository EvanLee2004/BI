#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.4 密封证据入口（失败即非零退出）。

1) 强制 config.data_dir=_golden_data（否则 abort）
2) 本地配置注入合成台账路径（禁内网 UNC）
3) 临时 BU 配置示意BU甲 供 A4（跑完移除，不污染 golden 数字基线）
4) 调 playwright_task54p4_evidence
5) 卫生闸：results 关键键 + 证据文本/JSON 禁 192.168 / \\\\ / 财务部
6) 写回双复刻清单 A4 + 安全留痕 F2 改密踢

用法（服务已起且 data_dir=_golden_data）：
  KANBAN_BASE=http://127.0.0.1:8018 .venv/bin/python tests/frontend/seal_54p4_evidence.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "pixel" / "vue54p4"
SCRATCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-7034d6e0fee6/implementer"
)
SCRATCH.mkdir(parents=True, exist_ok=True)

SENSITIVE = re.compile(
    r"(\\\\|192\.168\.|10\.\d{1,3}\.|财务部|lushasha@|kanban2026|\\\\192)",
    re.I,
)

BU_SNIP = {
    "bus": [
        {
            "name": "示意BU甲",
            "销售": ["员工007", "员工013", "员工026"],
            "负责人": [],
        }
    ],
    "公共费用分摊启用": False,
}

LOCAL_SAFE = {
    "schedule_time": "09:30",
    "schedule_times": ["09:30"],
    "backup_keep_days": 365,
    "zhiyun_auto_fetch": False,
    "ledger_share_path": "/tmp/golden_share/示意收单台账.xlsx",
}

# 勿用内网默认；否则 settings 折叠层会带 192.168 进截图/DOM
ZHIYUN_SAFE = {
    "base_url": "http://127.0.0.1:9",
    "_comment": "golden synthetic only; not a live endpoint",
}


def die(msg: str, code: int = 1) -> None:
    print("SEAL_FAIL:", msg, file=sys.stderr)
    raise SystemExit(code)


def assert_golden_config() -> dict:
    cfg_path = ROOT / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg.get("data_dir") != "_golden_data":
        die(f"data_dir must be _golden_data, got {cfg.get('data_dir')!r}")
    return cfg


def prepare_golden() -> tuple[Path, Path | None]:
    gd = ROOT / "_golden_data"
    if not gd.is_dir():
        die("missing _golden_data")
    local = gd / "本地配置.json"
    local.write_text(json.dumps(LOCAL_SAFE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (gd / "智云配置.json").write_text(
        json.dumps(ZHIYUN_SAFE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bu = gd / "BU配置.json"
    # keep previous aside
    prev = None
    if bu.exists():
        prev = Path(str(bu) + ".aside_seal")
        bu.replace(prev)
    bu.write_text(json.dumps(BU_SNIP, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # snippet for docs
    snip = OUT / "final" / "A4_golden_BU配置.snippet.json"
    snip.parent.mkdir(parents=True, exist_ok=True)
    snip.write_text(json.dumps(BU_SNIP, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # bu_only account
    accp = gd / "看板账号.json"
    if accp.exists():
        acc = json.loads(accp.read_text(encoding="utf-8"))
        for a in acc.get("accounts") or []:
            if a.get("账号") == "bu_only":
                a["权限"] = "示意BU甲"
                a["可见BU"] = ["示意BU甲"]
            if a.get("账号") in ("overall", "bu_only") and str(a.get("密码") or "").endswith("K"):
                a["密码"] = str(a["密码"])[:-1] or "8888"
        accp.write_text(json.dumps(acc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return bu, prev


def cleanup_bu(bu: Path, prev: Path | None) -> None:
    if bu.exists():
        bu.unlink()
    if prev and prev.exists():
        prev.replace(bu)


def run_evidence() -> int:
    script = ROOT / "tests" / "frontend" / "playwright_task54p4_evidence.py"
    r = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"), str(script), str(SCRATCH)],
        cwd=str(ROOT),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "KANBAN_OFFLINE": "1"},
    )
    return r.returncode


def hygiene_gate(results: dict) -> None:
    if results.get("admin_still_login"):
        die("admin_still_login true")
    if not results.get("A4_ok"):
        die("A4_ok false")
    a4 = OUT / "final" / "A4_BU_dark_1440.png"
    if not a4.is_file() or a4.stat().st_size < 100_000:
        die(f"A4 png missing or tiny: {a4}")
    if not results.get("F2_passwd_kick_ok"):
        die("F2_passwd_kick_ok false")
    save = results.get("admin_settings_save_net") or {}
    if not (
        results.get("admin_settings_save_click") == "button:has-text('保存全部设置')"
        or (isinstance(save, dict) and save.get("status") == 200)
    ):
        die(f"admin write path weak: {results.get('admin_settings_save_click')} {save}")
    # scan committed evidence text/json + PNG binary for 内网/UNC tokens
    bad: list[str] = []
    for p in OUT.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in {".json", ".txt", ".md", ".log"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if SENSITIVE.search(text):
                bad.append(str(p.relative_to(ROOT)))
        elif suf == ".png":
            data = p.read_bytes()
            for tok in (
                b"192.168",
                b"10.151",
                b"lara.zhao",
                b"\\192",
                "财务部".encode("utf-8"),
            ):
                if tok in data:
                    bad.append(f"{p.relative_to(ROOT)}:{tok!r}")
                    break
    if bad:
        die("sensitive pattern in evidence: " + ", ".join(bad[:8]))
    for key in ("A4_body_prefix", "admin_settings_url"):
        v = str(results.get(key) or "")
        if SENSITIVE.search(v):
            die(f"sensitive in results[{key}]")


def writeback_checklists(results: dict) -> None:
    a4_line_docs = (
        "| A4 | BU 页·暗色 | `BU页_*_暗色_1440` | **达标** | "
        "`docs/pixel/vue54p4/final/A4_BU_dark_1440.png`；golden 临时示意BU甲；"
        f"A4_ok={results.get('A4_ok')} |"
    )
    a4_pat = re.compile(r"^\| A4 \|.*$", re.M)

    docs_list = ROOT / "docs" / "复刻清单_54p4状态.md"
    if docs_list.is_file():
        t = docs_list.read_text(encoding="utf-8")
        t2 = a4_pat.sub(a4_line_docs, t, count=1)
        docs_list.write_text(t2, encoding="utf-8")

    # 原始素材权威表（目录名含中文括号）
    raw_root = ROOT.parents[1] / "原始素材"
    raw_list = None
    for d in raw_root.iterdir() if raw_root.is_dir() else []:
        if d.is_dir() and "legacy前端视觉基准" in d.name:
            cand = d / "复刻清单.md"
            if cand.is_file():
                raw_list = cand
                break
    if raw_list:
        t = raw_list.read_text(encoding="utf-8")
        a4_line_raw = (
            "| A4 | BU 页·暗色 | `BU页_*_暗色_1440` | **达标** | "
            "程序/看板正式程序/docs/pixel/vue54p4/final/A4_BU_dark_1440.png（golden 示意BU甲） |"
        )
        t2 = a4_pat.sub(a4_line_raw, t, count=1)
        raw_list.write_text(t2, encoding="utf-8")
        print("synced", raw_list)

    sec = ROOT / "docs" / "历史批次" / "20260718_任务书54.4_安全留痕.md"
    if sec.is_file():
        kick = results.get("F2_passwd_kick") or {}
        block = (
            "## F2 logout / 会话\n"
            "- **活体 logout**：管理员 form 登录 → `/api/accounts` 200 → `/admin/logout` → `/api/accounts` **401**\n"
            f"  - 证据：`docs/pixel/vue54p4/sec/results.json`（F2_logout_accounts={results.get('F2_logout_accounts')}）\n"
            "- **活体改密踢会话（F2）**：看端 overall 登录 → `POST /api/my_passwd` "
            f"{{old,new}} → change={kick.get('change')} → `/api/v1/session` **{kick.get('after_session')}** "
            f"（before={kick.get('before')}）；还原 `F2_passwd_restored={results.get('F2_passwd_restored')}`\n"
            "  - 证据：`docs/pixel/vue54p4/admin/results.json` / `sec/results.json` 字段 `F2_passwd_kick` / `F2_passwd_kick_ok`\n"
            "- Vue 看端 `api/client.ts`：401 → `/login`\n"
        )
        t = sec.read_text(encoding="utf-8")
        t2 = re.sub(r"## F2 logout / 会话\n.*?(?=\n## F3|\Z)", block, t, count=1, flags=re.S)
        if t2 == t and "## F2" in t:
            # replace from F2 to F3
            t2 = re.sub(r"## F2[\s\S]*?(?=## F3)", block + "\n", t, count=1)
        sec.write_text(t2, encoding="utf-8")
        print("synced", sec)


def main() -> int:
    assert_golden_config()
    bu, prev = prepare_golden()
    try:
        code = run_evidence()
        if code != 0:
            die(f"evidence script exit {code}", code)
        res_path = OUT / "admin" / "results.json"
        results = json.loads(res_path.read_text(encoding="utf-8"))
        hygiene_gate(results)
        writeback_checklists(results)
        (SCRATCH / "seal_ok.json").write_text(
            json.dumps(
                {
                    "A4_ok": results.get("A4_ok"),
                    "admin_still_login": results.get("admin_still_login"),
                    "F2_passwd_kick_ok": results.get("F2_passwd_kick_ok"),
                    "admin_settings_save_net": results.get("admin_settings_save_net"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("SEAL_OK")
        return 0
    finally:
        cleanup_bu(bu, prev)
        # restore bu_only 营销 for baseline-friendly golden accounts (tests)
        accp = ROOT / "_golden_data" / "看板账号.json"
        if accp.exists():
            acc = json.loads(accp.read_text(encoding="utf-8"))
            for a in acc.get("accounts") or []:
                if a.get("账号") == "bu_only":
                    a["权限"] = "BU"
                    a["可见BU"] = ["营销"]
            accp.write_text(json.dumps(acc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
