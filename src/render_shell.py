#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看端页面骨架 HTML 常量（抽屉/粒子/改密弹窗/日段面板/排名弹窗）。
从 render.py 按符号迁出；字符串内容与迁前逐字节一致。
"""
from __future__ import annotations

# 右侧抽屉（点利润表大类看构成）——单例，放 body 末尾
DRAWER_HTML = ('<div id="drawer" class="drawer" aria-hidden="true">'
               '<div class="drawer-mask" data-close></div>'
               '<aside class="drawer-panel" role="dialog" aria-modal="true">'
               '<div class="drawer-h"><span id="drawerTitle"></span>'
               '<button class="drawer-x" data-close aria-label="关闭">×</button></div>'
               '<div class="drawer-body" id="drawerBody"></div></aside></div>')

# 背景粒子流（科技风环境动效）——固定位置表，纯装饰、不进任何计算/回归
# (left%, 直径px, 时长s, 延迟s, 颜色变量)
_PARTICLES = [(4, 2, 20, -3, "--blue"), (9, 3, 15, -9, "--purple"), (15, 2, 22, -14, "--teal"),
              (20, 2, 17, -5, "--blue"), (26, 3, 24, -18, "--purple"), (31, 2, 14, -2, "--teal"),
              (37, 2, 21, -11, "--blue"), (43, 3, 27, -7, "--purple"), (48, 2, 16, -15, "--teal"),
              (54, 2, 25, -20, "--teal"), (59, 2, 19, -12, "--blue"), (65, 3, 13, -6, "--purple"),
              (70, 3, 26, -16, "--teal"), (76, 2, 18, -9, "--blue"), (81, 2, 23, -3, "--purple"),
              (87, 2, 15, -13, "--teal"), (92, 3, 28, -8, "--blue"), (97, 2, 20, -17, "--purple"),
              (12, 2, 12, -1, "--blue"), (34, 2, 30, -22, "--teal"), (46, 2, 11, -4, "--purple"),
              (57, 3, 29, -10, "--teal"), (68, 2, 13, -19, "--blue"), (79, 2, 24, -6, "--purple"),
              (90, 2, 16, -14, "--teal"), (24, 3, 21, -2, "--blue"), (50, 2, 27, -11, "--purple"),
              (72, 2, 14, -7, "--teal")]

PARTICLES_HTML = ('<div class="particles" aria-hidden="true">' + "".join(
    f'<i style="left:{l}%;width:{s}px;height:{s}px;background:var({c});box-shadow:0 0 6px var({c});'
    f'animation-duration:{d}s;animation-delay:{dl}s"></i>' for l, s, d, dl, c in _PARTICLES) + '</div>')

# 看的人自改密码（v8.0）：弹窗文案必须含「密码管理员可见，请勿使用你在其他地方用的密码」
PW_MODAL_HTML = """
<div id="pwModal" style="display:none;position:fixed;inset:0;z-index:80;background:#0f172acc;
 align-items:center;justify-content:center">
 <div style="background:#1e293b;color:#e2e8f0;padding:22px 24px;border-radius:12px;width:min(360px,92vw);
  box-shadow:0 12px 40px #0009;font-family:-apple-system,system-ui,sans-serif">
  <div style="font-size:16px;font-weight:700;margin-bottom:10px">修改密码</div>
  <div style="font-size:12px;color:#fde68a;line-height:1.5;margin-bottom:12px;padding:8px 10px;
   background:#422006;border-radius:8px">密码管理员可见，请勿使用你在其他地方用的密码</div>
  <label style="font-size:12px;color:#94a3b8">旧密码</label>
  <input id="pwOld" type="password" autocomplete="current-password"
   style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;border-radius:7px;
   border:1px solid #334155;background:#0f172a;color:#e2e8f0">
  <label style="font-size:12px;color:#94a3b8">新密码（至少 4 位）</label>
  <input id="pwNew" type="password" autocomplete="new-password"
   style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;border-radius:7px;
   border:1px solid #334155;background:#0f172a;color:#e2e8f0">
  <div id="pwMsg" style="font-size:12px;color:#f87171;min-height:16px;margin-bottom:8px"></div>
  <div style="display:flex;gap:8px;justify-content:flex-end">
   <button type="button" id="pwCancel" style="padding:7px 12px;border-radius:7px;border:1px solid #334155;
    background:transparent;color:#e2e8f0;cursor:pointer">取消</button>
   <button type="button" id="pwOk" style="padding:7px 14px;border-radius:7px;border:0;
    background:#8b5cf6;color:#fff;cursor:pointer">保存</button>
  </div>
 </div>
</div>
"""

# ---------- 按天明细（迭代17 批次A：常显 + 跟顶 + 返回默认全年）----------
# 铁律2：金额显示串全部由 /api/daily 后端算好（*_disp）；前端 JS 已外置 static/js/cockpit.js。
# 排名「其余」弹窗壳（整体页 API 展开 / BU 页本地预渲染展开共用）
RK_MODAL_HTML = """
<div id="rkModal" style="display:none">
  <div class="rkm-box">
    <div class="card-h"><span id="rkmTitle"></span> <span class="tag" id="rkmTag"></span>
      <button class="toggle daily-close" id="rkmClose" type="button"><span>✕</span> 关闭</button></div>
    <div class="rkm-list" id="rkmList"></div>
  </div>
</div>"""

# 顶部「看哪段」不动；本面板只改板块③排名（查询才打 /api/daily；跟顶只改日期框）。
DAILY_HTML = """
<div class="card" id="dailyPanel" style="margin-bottom:16px">
  <div class="card-h">按时间段看</div>
  <div class="daily-bar">
    <input type="date" id="dailyS"> ~ <input type="date" id="dailyE">
    <button class="toggle" id="dailyGo" type="button">查询</button>
    <button class="toggle" id="dailyToday" type="button">今日</button>
    <button class="toggle" id="dailyMonth" type="button">本月</button>
    <button class="toggle" id="dailyClose" type="button">本年</button>
    <span id="dailySum" class="daily-note"></span>
  </div>
</div>
""" + RK_MODAL_HTML

