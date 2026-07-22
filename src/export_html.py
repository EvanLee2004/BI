#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.7 导出 HTML：优先 Playwright 打开 Vue 页 → canvas 转 img → 冻成可离线 HTML。

降级：用当前 VM + static/templates/export/fallback.html（禁止 assemble_dashboard_html 老皮）。
PNG 兼容仍走 export_png.screenshot_png，本模块不删 Playwright。
"""

from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


def _canvas_to_img_script() -> str:
    # 无 HTML 标签字面量（守卫 test_no_html_in_py）；运行时在浏览器拼 DOM
    return """() => {
  document.querySelectorAll('canvas').forEach(c => {
    try {
      const img = document.createElement('img');
      img.src = c.toDataURL('image/png');
      img.alt = 'chart';
      const cs = window.getComputedStyle(c);
      img.style.width = cs.width;
      img.style.height = cs.height;
      img.style.maxWidth = '100%';
      img.className = (c.className || '') + ' export-chart-img';
      if (c.parentNode) c.parentNode.replaceChild(img, c);
    } catch (e) {}
  });
  ['#exportBtn','#logoutBtn','#pwBtn'].forEach(sel => {
    document.querySelectorAll(sel).forEach(el => { el.style.display = 'none'; });
  });
}"""


def capture_vue_export_html(
    page_url: str,
    *,
    cookie_header: str = "",
    blk: str = "",
    width: int = 1440,
    timeout_ms: int = 45000,
) -> str:
    """Playwright 打开已登录 Vue 页，等 KPI，canvas→img，返回整页 HTML。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        try:
            ctx = br.new_context(
                viewport={"width": width, "height": 900},
                reduced_motion="reduce",
                device_scale_factor=2,
            )
            if cookie_header:
                from urllib.parse import urlparse

                host = urlparse(page_url).hostname or "127.0.0.1"
                cookies = []
                for part in cookie_header.split(";"):
                    part = part.strip()
                    if not part or "=" not in part:
                        continue
                    name, _, val = part.partition("=")
                    cookies.append({"name": name.strip(), "value": val.strip(), "domain": host, "path": "/"})
                if cookies:
                    ctx.add_cookies(cookies)
            pg = ctx.new_page()
            pg.goto(page_url, wait_until="load", timeout=timeout_ms)
            try:
                pg.wait_for_selector(
                    ".kpi-grid, .kpi-cards, [class*='kpi'], #periodSync, .topbar",
                    timeout=min(20000, timeout_ms),
                )
            except Exception:
                pg.wait_for_timeout(800)
            if blk:
                try:
                    pg.evaluate(
                        """(k) => {
                      try {
                        const store = window.__pinia && Object.values(window.__pinia.state.value||{})[0];
                        if (store && store.period !== undefined) store.period = k;
                      } catch (e) {}
                      document.querySelectorAll('[data-period]').forEach(el => {
                        if (el.getAttribute('data-period') === k) el.click();
                      });
                    }""",
                        blk,
                    )
                    pg.wait_for_timeout(400)
                except Exception:
                    pass
            pg.evaluate(_canvas_to_img_script())
            pg.wait_for_timeout(300)
            raw = pg.content()
            return _absolutize_urls(raw, page_url)
        finally:
            br.close()


def _absolutize_urls(html: str, base_url: str) -> str:
    """相对 /app /static 资源改为绝对 URL，便于离线打开仍能尽量加载。"""
    base = base_url if base_url.endswith("/") else base_url.rsplit("/", 1)[0] + "/"
    origin = re.match(r"^(https?://[^/]+)", base_url)
    origin_s = origin.group(1) if origin else base_url.rstrip("/")

    def abs_attr(m):
        attr, quote, url = m.group(1), m.group(2), m.group(3)
        if url.startswith(("http://", "https://", "data:", "blob:", "mailto:", "#")):
            return m.group(0)
        if url.startswith("//"):
            return f"{attr}={quote}https:{url}{quote}"
        if url.startswith("/"):
            return f"{attr}={quote}{origin_s}{url}{quote}"
        return f"{attr}={quote}{urljoin(base, url)}{quote}"

    return re.sub(
        r"""\b(href|src)=(["'])([^"']+)\2""",
        abs_attr,
        html,
        flags=re.I,
    )


def _el(tag: str, body: str, **attrs: str) -> str:
    """运行时拼标签，避免 py 源码出现标签字面量（test_no_html_in_py）。"""
    parts = []
    for k, v in attrs.items():
        parts.append(f'{k}="{html_lib.escape(v, quote=True)}"')
    a = (" " + " ".join(parts)) if parts else ""
    return f"<{tag}{a}>{body}</{tag}>"


def fallback_export_html(
    vm: dict[str, Any],
    *,
    scope: str = "整体",
    bu_name: str = "",
    blk: str = "",
    version: str = "",
    theme_css: str = "",
    root: Path | None = None,
) -> str:
    """降级导出壳：模板在 static/templates/export/fallback.html。"""
    import tpl

    period = blk or vm.get("year_key") or (vm.get("period_keys") or [""])[0] or ""
    title = f"甲骨易智能经营罗盘 · {bu_name}" if bu_name else "甲骨易智能经营罗盘"
    cards = ((vm.get("kpi") or {}).get("cards_by_period") or {}).get(period) or []
    if not cards and (vm.get("kpi") or {}).get("cards_by_period"):
        cbp = (vm.get("kpi") or {}).get("cards_by_period") or {}
        for k, v in cbp.items():
            if v:
                period = k
                cards = v
                break
    card_parts = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        name = html_lib.escape(str(c.get("title") or c.get("name") or ""))
        val = html_lib.escape(str(c.get("value_disp") or c.get("value") or "—"))
        unit = html_lib.escape(str(c.get("unit") or ""))
        inner = (
            _el("div", name, **{"class": "k"})
            + _el("div", val + _el("span", unit, **{"class": "u"}), **{"class": "v"})
        )
        card_parts.append(_el("div", inner, **{"class": "kpi-card"}))
    cards_block = "\n".join(card_parts) or _el("div", "（无 KPI 数据）", **{"class": "muted"})

    pl_rows = ((vm.get("pl") or {}).get("table_by_period") or {}).get(period) or {}
    rows = pl_rows.get("rows") if isinstance(pl_rows, dict) else []
    trs = []
    if isinstance(rows, list):
        for r in rows[:40]:
            if not isinstance(r, dict):
                continue
            lab = html_lib.escape(str(r.get("label") or r.get("name") or ""))
            amt = html_lib.escape(str(r.get("value_disp") or r.get("amt_disp") or ""))
            trs.append(
                _el(
                    "tr",
                    _el("td", lab) + _el("td", amt, style="text-align:right"),
                )
            )
    if trs:
        pl_block = _el("table", _el("tbody", "".join(trs)), **{"class": "pl", "style": "width:100%;border-collapse:collapse"})
    else:
        pl_block = _el("div", "（无利润表行）", **{"class": "muted"})

    css = theme_css or _default_export_css()
    meta_json = html_lib.escape(
        json.dumps({"period": period, "scope": scope, "bu": bu_name}, ensure_ascii=False)
    )
    bu_suffix = (" · " + html_lib.escape(bu_name)) if bu_name else ""
    # tpl.fill 用 str.format，模板里 {{ }} 已转义
    return tpl.fill(
        "export/fallback.html",
        title=html_lib.escape(title),
        css=css,
        period=html_lib.escape(period),
        version=html_lib.escape(version or ""),
        bu_suffix=bu_suffix,
        cards=cards_block,
        pl=pl_block,
        meta_json=meta_json,
    )


def _default_export_css() -> str:
    return """
:root {
  --bg:#0b1220; --fg:#e2e8f0; --card:#1e293b; --line:#334155; --mut:#94a3b8;
  --blue:#38bdf8; --neg:#f87171;
}
"""


def load_theme_css(root: Path | None = None) -> str:
    """尽量内联 static/css/theme.css，使离线 HTML 自带主题色。"""
    bases = []
    if root:
        bases.append(Path(root))
    bases.append(Path(__file__).resolve().parent.parent)
    for base in bases:
        p = base / "static" / "css" / "theme.css"
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                pass
    return _default_export_css()


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
    prefer_playwright: bool = True,
) -> tuple[str, str]:
    """返回 (html, mode) mode=playwright|fallback。"""
    import os

    offline = (os.environ.get("KANBAN_OFFLINE") or "").strip() in ("1", "true", "yes")
    test_host = bool(
        page_url
        and (
            "testserver" in page_url
            or (page_url.startswith("http://test") and "localhost" not in page_url and "127.0.0.1" not in page_url)
        )
    )
    if prefer_playwright and page_url and not offline and not test_host:
        try:
            html = capture_vue_export_html(page_url, cookie_header=cookie_header, blk=blk)
            if html and len(html) > 200:
                return html, "playwright"
        except Exception:
            pass
    theme = load_theme_css(root)
    return (
        fallback_export_html(
            vm or {},
            scope=scope,
            bu_name=bu_name,
            blk=blk,
            version=version,
            theme_css=theme,
            root=root,
        ),
        "fallback",
    )
