#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看端页面骨架 HTML 常量（抽屉/粒子/改密弹窗/日段面板/排名弹窗）。
从 render.py 按符号迁出；字符串内容与迁前逐字节一致。
v模板化：纯 HTML 外置 static/templates/partials/，本模块仅作载入缓存。
"""

from __future__ import annotations

import tpl

# 背景粒子流（科技风环境动效）——固定位置表，纯装饰、不进任何计算/回归
# (left%, 直径px, 时长s, 延迟s, 颜色变量)
_PARTICLES = [
    (4, 2, 20, -3, "--blue"),
    (9, 3, 15, -9, "--purple"),
    (15, 2, 22, -14, "--teal"),
    (20, 2, 17, -5, "--blue"),
    (26, 3, 24, -18, "--purple"),
    (31, 2, 14, -2, "--teal"),
    (37, 2, 21, -11, "--blue"),
    (43, 3, 27, -7, "--purple"),
    (48, 2, 16, -15, "--teal"),
    (54, 2, 25, -20, "--teal"),
    (59, 2, 19, -12, "--blue"),
    (65, 3, 13, -6, "--purple"),
    (70, 3, 26, -16, "--teal"),
    (76, 2, 18, -9, "--blue"),
    (81, 2, 23, -3, "--purple"),
    (87, 2, 15, -13, "--teal"),
    (92, 3, 28, -8, "--blue"),
    (97, 2, 20, -17, "--purple"),
    (12, 2, 12, -1, "--blue"),
    (34, 2, 30, -22, "--teal"),
    (46, 2, 11, -4, "--purple"),
    (57, 3, 29, -10, "--teal"),
    (68, 2, 13, -19, "--blue"),
    (79, 2, 24, -6, "--purple"),
    (90, 2, 16, -14, "--teal"),
    (24, 3, 21, -2, "--blue"),
    (50, 2, 27, -11, "--purple"),
    (72, 2, 14, -7, "--teal"),
]

# 右侧抽屉（点利润表大类看构成）——单例，放 body 末尾
DRAWER_HTML = tpl.load("partials/drawer.html")

# 粒子：数据表仍在本模块；行片段+外壳来自模板
_PARTICLE_ITEM = tpl.load("partials/particle_item.html")
_PARTICLES_WRAP = tpl.load("partials/particles_wrap.html")
PARTICLES_HTML = _PARTICLES_WRAP.format(
    items="".join(_PARTICLE_ITEM.format(l=left, s=s, d=d, dl=dl, c=c) for left, s, d, dl, c in _PARTICLES)
)

# 看的人自改密码（v8.0）：弹窗文案必须含「密码管理员可见，请勿使用你在其他地方用的密码」
PW_MODAL_HTML = tpl.load("partials/pw_modal.html")

# ---------- 按天明细（迭代17 批次A：常显 + 跟顶 + 返回默认全年）----------
# 铁律2：金额显示串全部由 /api/daily 后端算好（*_disp）；前端 JS 已外置 static/js/cockpit.js。
# 排名「其余」弹窗壳（整体页 API 展开 / BU 页本地预渲染展开共用）
RK_MODAL_HTML = tpl.load("partials/rk_modal.html")

# 顶部「看哪段」不动；本面板只改板块③排名（查询才打 /api/daily；跟顶只改日期框）。
DAILY_HTML = tpl.load("partials/daily_panel.html") + RK_MODAL_HTML
