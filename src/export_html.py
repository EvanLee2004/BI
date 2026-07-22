#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.9 导出 HTML：方案 A 自包含静态可交互快照（Vue 播放器 + kanban_snapshot pack）。

- 主路径：assemble_export_pack + build_snapshot_export_html（不依赖 Playwright）。
- KANBAN_OFFLINE=1 或 Playwright 不可用时仍出真快照；失败 → 明确异常（路由转 503），
  **禁止**静默返回 data-export-fallback 残壳冒充成功。
- PNG 兼容仍走 export_png；历史 archive 仍走 ingest.archive.snapshot_vm。
- 旧 Playwright 冻页 / fallback 残壳已退役（仅测试夹可引用历史语义，生产主路径不走）。
"""

from __future__ import annotations

import html as html_lib
import json
import time
from pathlib import Path
from typing import Any


SNAPSHOT_KIND = "kanban_snapshot"
SNAPSHOT_SCHEMA = 1


def _stub_vm(summary: dict | None, *, bu_name: str = "") -> dict:
    meta = (summary or {}).get("meta") or {}
    out: dict[str, Any] = {
        "year_key": meta.get("year_key") or "",
        "period_keys": list((summary or {}).get("periods") or {}),
        "kpi": {"cards_by_period": {}},
    }
    if bu_name:
        out["bu_name"] = bu_name
    return out


def _build_vm_from_summary(summary: dict | None, cfg: dict | None, *, bu_name: str = "") -> dict:
    if not summary:
        return _stub_vm(summary, bu_name=bu_name)
    try:
        import viewmodels

        if bu_name:
            return viewmodels.build_bu_vm(bu_name, summary, cfg or {}).model_dump()
        return viewmodels.build_cockpit_vm(summary, cfg or {}).model_dump()
    except Exception:
        return _stub_vm(summary, bu_name=bu_name)


def normalize_export_theme(theme: str | None) -> str:
    """白名单：neon|dark|light；非法一律 neon。"""
    t = (theme or "").strip().lower()
    if t in ("neon", "dark", "light"):
        return t
    return "neon"


def assemble_export_pack(
    *,
    scope: str = "整体",
    bu_name: str = "",
    blk: str = "",
    version: str = "",
    built_at: str | None = None,
    exported_at: str | None = None,
    cockpit_vm: dict | None = None,
    bu_vms: dict[str, dict] | None = None,
    state: dict | None = None,
    cfg: dict | None = None,
    theme: str | None = None,
) -> dict[str, Any]:
    """纯函数：组装 kind=kanban_snapshot 数据包（可单测、与 HTTP 解耦）。

    - 整体/管理员：cockpit 完整 + bu=全部已发布 BU 的 PageVM。
    - BU：scope=BU，bu 仅该一个键；cockpit 为空对象。
    - 禁止写入口令/密码字段。
    - 2.3.0：theme 字段（neon|dark|light）。
    """
    st = state if state is not None else {}
    exp_at = exported_at or time.strftime("%Y-%m-%d %H:%M:%S")
    b_at = built_at or (st.get("built_at") if isinstance(st.get("built_at"), str) else None) or exp_at
    ver = version or ""
    theme_v = normalize_export_theme(theme)

    if scope == "BU" and bu_name:
        if bu_vms is not None and bu_name in bu_vms:
            one = bu_vms[bu_name]
        else:
            page = (st.get("bu_pages") or {}).get(bu_name) or {}
            summary = page.get("summary") if isinstance(page, dict) else None
            one = _build_vm_from_summary(summary, cfg, bu_name=bu_name)
        period_keys = list((one or {}).get("period_keys") or [])
        default_period = blk if blk and (not period_keys or blk in period_keys) else (
            (one or {}).get("year_key") or (period_keys[0] if period_keys else blk or "")
        )
        return {
            "kind": SNAPSHOT_KIND,
            "schema": SNAPSHOT_SCHEMA,
            "exported_at": exp_at,
            "built_at": b_at,
            "version": ver,
            "default_period": default_period,
            "scope": "BU",
            "bu_export_name": bu_name,
            "theme": theme_v,
            "cockpit": {},
            "bu": {bu_name: one if isinstance(one, dict) else {}},
        }

    # 整体
    if cockpit_vm is not None:
        cockpit = cockpit_vm
    else:
        summary = st.get("summary")
        cockpit = _build_vm_from_summary(summary if isinstance(summary, dict) else None, cfg)

    if bu_vms is not None:
        bus = {k: v for k, v in bu_vms.items() if isinstance(v, dict)}
    else:
        bus = {}
        for name, page in (st.get("bu_pages") or {}).items():
            if not isinstance(page, dict):
                continue
            summary = page.get("summary")
            bus[str(name)] = _build_vm_from_summary(
                summary if isinstance(summary, dict) else None, cfg, bu_name=str(name)
            )

    period_keys = list((cockpit or {}).get("period_keys") or [])
    default_period = blk if blk and (not period_keys or blk in period_keys) else (
        (cockpit or {}).get("year_key") or (period_keys[0] if period_keys else blk or "")
    )
    return {
        "kind": SNAPSHOT_KIND,
        "schema": SNAPSHOT_SCHEMA,
        "exported_at": exp_at,
        "built_at": b_at,
        "version": ver,
        "default_period": default_period,
        "scope": "整体",
        "bu_export_name": "",
        "theme": theme_v,
        "cockpit": cockpit if isinstance(cockpit, dict) else {},
        "bu": bus,
    }


def _package_root() -> Path:
    """程序包根（含 frontend/、static/），与数据 root 无关。"""
    return Path(__file__).resolve().parent.parent


def _find_root(root: Path | None = None) -> Path:
    """兼容旧调用；播放器/主题资源一律走 _package_root。"""
    if root:
        return Path(root)
    return _package_root()


def _snapshot_asset_paths(root: Path | None = None) -> tuple[Path, Path | None]:
    """返回 (js_path, css_path|None)。固定从程序包根找 dist-snapshot（非数据 root）。"""
    del root  # 数据 root 无 dist；忽略
    base = _package_root() / "frontend" / "dist-snapshot"
    js = base / "snapshot.js"
    if not js.is_file():
        # 兼容 hash 名
        for p in sorted(base.glob("*.js")):
            if p.name != "snapshot.html":
                js = p
                break
    css: Path | None = None
    c1 = base / "snapshot.css"
    if c1.is_file():
        css = c1
    else:
        for p in sorted(base.glob("*.css")):
            css = p
            break
    return js, css


def load_theme_css(root: Path | None = None) -> str:
    """内联 static/css/theme.css（程序包根优先；可选数据 root 覆盖）。"""
    bases = [_package_root()]
    if root:
        bases.insert(0, Path(root))
    for base in bases:
        p = base / "static" / "css" / "theme.css"
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                pass
    return (
        ":root{--bg:#0b1220;--fg:#e2e8f0;--card:#1e293b;"
        "--line:#334155;--mut:#94a3b8;--blue:#38bdf8;--neg:#f87171;}"
    )


def build_snapshot_export_html(
    pack: dict[str, Any],
    *,
    root: Path | None = None,
    theme_css: str | None = None,
) -> str:
    """把 pack + 快照播放器（dist-snapshot）装配成单文件 HTML。

    失败抛 RuntimeError（路由转 503）；绝不返回 fallback 残壳。
    """
    # 播放器固定从程序包根加载；root 仅用于可选 theme 覆盖
    js_path, css_path = _snapshot_asset_paths(None)
    if not js_path.is_file():
        raise RuntimeError(
            "快照播放器未构建：缺少 frontend/dist-snapshot/snapshot.js；"
            "请在 frontend 执行 npm run build（含 build:snapshot）"
        )
    try:
        player_js = js_path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"读取快照 JS 失败: {e}") from e
    player_css = ""
    if css_path and css_path.is_file():
        try:
            player_css = css_path.read_text(encoding="utf-8")
        except OSError:
            player_css = ""
    theme = theme_css if theme_css is not None else load_theme_css(root)

    # JSON 安全嵌入：</script> 拆开防提前闭合
    pack_raw = json.dumps(pack, ensure_ascii=False, default=str)
    pack_raw = pack_raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    # application/json 槽用转义后的同串
    pack_for_tag = pack_raw

    scope = str(pack.get("scope") or "整体")
    bu = str(pack.get("bu_export_name") or "")
    del scope  # 仅 title 用 bu
    title = f"甲骨易智能经营罗盘 · {bu}（静态快照）" if bu else "甲骨易智能经营罗盘（静态快照）"
    title_esc = html_lib.escape(title)

    # 用 token 替换（不用 str.format：player_js / pack 含大量 {}）
    import tpl

    shell = tpl.load("export/snapshot_shell.html")
    out = (
        shell.replace("__TITLE__", title_esc)
        .replace("__THEME_CSS__", theme)
        .replace("__PLAYER_CSS__", player_css)
        .replace("__PACK_JSON__", pack_for_tag)
        .replace("__PACK_JSON_RAW__", pack_raw)
        .replace("__PLAYER_JS__", player_js)
    )
    if "__TITLE__" in out or "__PLAYER_JS__" in out:
        raise RuntimeError("快照模板 token 未替换干净")
    # S6.D：密级页脚 token（HTML 在模板里，py 不拼标签——test_no_html_in_py）
    exp_at = html_lib.escape(str(pack.get("exported_at") or ""))
    out = out.replace("__EXPORTED_AT__", exp_at)
    if "__EXPORTED_AT__" in out:
        raise RuntimeError("快照密级页脚 token 未替换")
    return out


def build_export_html(
    *,
    page_url: str | None = None,
    cookie_header: str = "",
    blk: str = "",
    vm: dict | None = None,
    scope: str = "整体",
    bu_name: str = "",
    version: str = "",
    root: Path | None = None,
    prefer_playwright: bool = False,
    pack: dict | None = None,
    state: dict | None = None,
    cfg: dict | None = None,
    cockpit_vm: dict | None = None,
    bu_vms: dict | None = None,
    built_at: str | None = None,
) -> tuple[str, str]:
    """返回 (html, mode)；mode=snapshot。

    2.2.9：主路径仅为 snapshot；prefer_playwright 忽略（保留形参兼容旧调用）。
    失败抛异常，由路由转 503——**永不**返回 fallback 残壳。
    """
    del page_url, cookie_header, prefer_playwright  # 兼容形参，方案 A 不用
    if pack is None:
        # 若调用方只给了单页 vm（旧接口），包一层
        if scope == "BU" and bu_name and vm is not None and cockpit_vm is None and bu_vms is None:
            pack = assemble_export_pack(
                scope="BU",
                bu_name=bu_name,
                blk=blk,
                version=version,
                built_at=built_at,
                bu_vms={bu_name: vm},
                state=state,
                cfg=cfg,
            )
        elif vm is not None and cockpit_vm is None and bu_vms is None and scope != "BU":
            pack = assemble_export_pack(
                scope="整体",
                blk=blk,
                version=version,
                built_at=built_at,
                cockpit_vm=vm,
                bu_vms={},
                state=state,
                cfg=cfg,
            )
        else:
            pack = assemble_export_pack(
                scope=scope if scope in ("整体", "BU") else ("BU" if bu_name else "整体"),
                bu_name=bu_name,
                blk=blk,
                version=version,
                built_at=built_at,
                cockpit_vm=cockpit_vm,
                bu_vms=bu_vms,
                state=state,
                cfg=cfg,
            )
    html = build_snapshot_export_html(pack, root=root)
    if not html or "kanban_snapshot" not in html:
        raise RuntimeError("快照 HTML 装配结果无效")
    if 'data-export-fallback="1"' in html or "data-export-fallback='1'" in html:
        raise RuntimeError("禁止导出残壳 fallback")
    return html, "snapshot"


# --- 以下为 2.2.7 时代 API 兼容壳（已不作为成功主路径；生产路由不再调用） ---


def capture_vue_export_html(*_a, **_k) -> str:
    """已退役：2.2.9 起导出主路径为 snapshot，不再 Playwright 冻页。"""
    raise RuntimeError("capture_vue_export_html 已退役（2.2.9 方案 A 快照）")


def fallback_export_html(*_a, **_k) -> str:
    """已退役：禁止残壳冒充成功。"""
    raise RuntimeError("fallback_export_html 已退役（2.2.9 禁止 data-export-fallback 假成功）")
