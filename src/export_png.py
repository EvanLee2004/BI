#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 导出（Playwright 截图；C：从 server 抽出）。

2.7.8 G3：HTML 主路径为 kanban_snapshot 播放器（#app Vue 挂载，ES module）。
         使用临时 file:// 打开（set_content 不跑 type=module 脚本）。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def screenshot_png(html: str, blk: str = "", width: int = 1440) -> bytes:
    """把导出 HTML 在无头浏览器里渲开并整页截图。

    - 方案 A 快照（data-kanban-export=snapshot）：写临时文件后 page.goto(file://)，
      等 body 出现「基本情况/下单」等 KPI 文案后再截。
    - 旧 assemble 页：仍支持 body[data-assembled=1]。
    """
    from playwright.sync_api import sync_playwright

    is_snapshot = (
        'data-kanban-export="snapshot"' in html
        or 'data-export-scheme="A"' in html
        or "kanban_snapshot" in html
        or "__KANBAN_SNAPSHOT__" in html
    )

    tmp_path: str | None = None
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        try:
            ctx = br.new_context(
                viewport={"width": width, "height": 900}, reduced_motion="reduce", device_scale_factor=2
            )
            pg = ctx.new_page()
            if is_snapshot:
                # ES module 播放器：必须 file://（set_content 不执行 type=module）
                fd, tmp_path = tempfile.mkstemp(suffix=".html")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(html)
                pg.goto(Path(tmp_path).resolve().as_uri(), wait_until="load", timeout=60000)
                try:
                    pg.wait_for_selector("#app", timeout=15000)
                    pg.wait_for_function(
                        """() => {
                          const t = (document.body && document.body.innerText) || '';
                          return (
                            t.includes('基本情况') ||
                            t.includes('下单') ||
                            (t.includes('经营看板') && t.includes('万'))
                          );
                        }""",
                        timeout=25000,
                    )
                    pg.wait_for_timeout(600)
                except Exception:
                    pg.wait_for_timeout(2000)
                if blk:
                    try:
                        pg.evaluate(
                            """(k) => {
                              try {
                                window.__KANBAN_EXPORT_PERIOD__ = k;
                                window.dispatchEvent(new CustomEvent('kanban-export-period', { detail: k }));
                              } catch (e) {}
                              const nodes = Array.from(document.querySelectorAll('button, [role=button]'));
                              const hit = nodes.find(n => (n.textContent || '').trim().includes(k));
                              if (hit) hit.click();
                            }""",
                            blk,
                        )
                        pg.wait_for_timeout(400)
                    except Exception:
                        pass
            else:
                pg.set_content(html, wait_until="load")
                try:
                    pg.wait_for_selector('body[data-assembled="1"]', timeout=15000)
                except Exception:
                    pg.wait_for_timeout(400)
                if blk:
                    pg.evaluate(
                        "k=>{document.querySelectorAll('.pv').forEach(x=>{"
                        "x.style.display=x.getAttribute('data-blk')===k?'':'none';});"
                        "var b=document.getElementById('periodBtn');"
                        "if(b)b.childNodes[0].textContent=k+' ';}",
                        blk,
                    )
            pg.add_style_tag(content=".particles,#exportBtn,#themeBtn{display:none!important}")
            pg.wait_for_timeout(400)
            return pg.screenshot(full_page=True, type="png")
        finally:
            br.close()
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
