#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 导出（Playwright 截图；C：从 server 抽出）。"""
from __future__ import annotations


def screenshot_png(html: str, blk: str = "", width: int = 1440) -> bytes:
    """把用户页 HTML 在无头浏览器里渲开并整页截图。blk 非空=先切到该周期视图。
    reduced_motion 关掉全部动效，截出来是静止完整帧。
    等 body[data-assembled=1]（B 组装完成标记）。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        try:
            ctx = br.new_context(viewport={"width": width, "height": 900},
                                 reduced_motion="reduce", device_scale_factor=2)
            pg = ctx.new_page()
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
                    "if(b)b.childNodes[0].textContent=k+' ';}", blk)
            pg.add_style_tag(content=".particles,#exportBtn,#themeBtn{display:none!important}")
            pg.wait_for_timeout(400)
            return pg.screenshot(full_page=True, type="png")
        finally:
            br.close()
