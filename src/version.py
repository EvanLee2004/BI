#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品版本号 + 面向用户的更新日志（v0.9 起 · 2026-07-12）。

**产品版本号 ≠ git 开发号**：
- 本文件的 `PRODUCT_VERSION` 是给用户/管理层看的「产品版本」：0.9=内部试运行 → **1.0-beta=公测 Beta（周一上线版）** → 去掉 `-beta` 升 1.0=正式版；
  唯一源是程序根目录的 `VERSION` 文件（纯文本一行）。（一键更新比对的是 git 远端提交，不读 VERSION；VERSION 纯展示。）
- git tag（v8.x）是**开发号**，只在代码仓库里用，绝不给用户看，两套号互不干扰。

`PRODUCT_CHANGELOG` 是**人读的大白话更新日志**（从 `软件工程文档/4_管理过程/CHANGELOG.md` 提炼，
不是自动解析）：管理端「版本与更新日志」卡按它渲染。每条=一次面向用户的更新，倒序（最新在上），
用管理层看得懂的话讲「这版能多干啥」，不写代码细节。
"""
from __future__ import annotations

from pathlib import Path

# 程序根（VERSION 与 run.py 同级）；src/ 的上一层
ROOT = Path(__file__).resolve().parent.parent
_FALLBACK_VERSION = "0.9"


def read_version() -> str:
    """读根目录 VERSION（纯文本一行）；缺文件/读不到 → 回退默认。"""
    try:
        v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        return v or _FALLBACK_VERSION
    except OSError:
        return _FALLBACK_VERSION


def product_stage(version: str | None = None) -> str:
    """判阶段：带 `-beta` 预发布标记 → 公测 Beta；否则主版本 <1 → 试运行、≥1 → 正式版。
    （0.9→试运行，1.0-beta→公测 Beta，1.0→正式版）。"""
    v = str(version if version is not None else read_version()).strip()
    base, _, pre = v.partition("-")
    if pre and "beta" in pre.lower():
        return "公测 Beta"
    try:
        major = int(base.split(".")[0])
    except (ValueError, IndexError):
        major = 0
    return "正式版" if major >= 1 else "试运行"


def product_label(version: str | None = None) -> str:
    """给界面/日志用的一行标签，如 `v1.0（公测 Beta）`；预发布号去掉 `-beta` 后缀只显主号。"""
    v = str(version if version is not None else read_version()).strip()
    base = v.partition("-")[0]
    return f"v{base}（{product_stage(v)}）"


PRODUCT_VERSION = read_version()
PRODUCT_STAGE = product_stage(PRODUCT_VERSION)

# 面向用户的更新日志（倒序·最新在上）。每条：date=公开日期、title=一句话标题、items=大白话要点。
# 加新版时在最前面插一条；措辞站管理层角度、别写代码/文件名。
PRODUCT_CHANGELOG: list[dict] = [
    {
        "date": "2026-07-13",
        "title": "公测 Beta v1.0.2：回款数字常显 + 管理端改名",
        "items": [
            "回款图柱顶直接显示每月回款（万）、折线点旁显示回款下单率%；右侧补「月度明细」数字表，宽屏不再空一块。",
            "管理端顶栏：「改数据」→「数据调整」；原「数据调整」页 →「人工填写」（人力/业绩目标）。",
            "修正 H1 业绩目标：仅 1–6 月区间用半年目标（Q1 不再误绑 H1）；毛利率「当前」与达成率同口径。",
        ],
    },
    {
        "date": "2026-07-13",
        "title": "顶栏「更新数据」+ 明细真·导出 Excel",
        "items": [
            "管理端顶栏「立即更新」改名为「更新数据」（抓智云/台账并重算）。",
            "数据调整·明细页支持按当前筛选导出真正的 Excel 文件（.xlsx，最多 5000 行）。",
        ],
    },
    {
        "date": "2026-07-13",
        "title": "去掉部门费用年预算 · 手填改名数据调整 · 金额千分位",
        "items": [
            "按陆总意见下线「部门费用预算执行」：半吊子汇总意义不大，完整「部门×费用类别」预算后置。",
            "回款情况恢复整宽展示（不再为预算卡留半边空列）。",
            "管理端「手填」改称「数据调整」；「业绩目标」优先维护（下单/回款/毛利率）。",
            "金额录入支持千分位显示（如 1,000,000），保存时自动去逗号。",
        ],
    },
    {
        "date": "2026-07-13",
        "title": "陆总现场反馈：KPI 五卡 + 目标进度 + 回款/预算对称 + 改数体验",
        "items": [
            "基本情况改为五项：下单 · 交付金额 · 毛利 · 税前利润 · 回款（去掉「成本费用合计」）。",
            "命名统一：交付金额（智云原数）/ 交付收入（÷1.06）/ 交付成本 / 项目毛利率；税前利润脚注写全公式。",
            "回款与「部门费用预算」始终左右对称；没填预算也显示空态卡，不再把回款图撑满整宽。",
            "可填业务目标（下单/回款/毛利率 · 年+上半年 · 全公司或各 BU），嵌在 KPI 下进度条。",
            "BU 页同样显示基本情况 KPI；管理端改数顶栏编辑、保存 toast、按定位键/订单号搜索、导出 CSV。",
            "下单未填部门可按销售筛选并批量归类；按时间段支持「今日」「本月」快捷。",
            "管理端版本日志默认折叠，点「更新日志」从右侧滑出明细（不撑开设置页）。",
            "暗色默认更强科技感；浅色保持简洁可切换。",
        ],
    },
    {
        "date": "2026-07-13",
        "title": "公测 Beta 上线：可对多人多 BU 发号 + 自动更新更省心",
        "items": [
            "版本进入「公测 Beta」：真实数据小范围试用，欢迎随时反馈。",
            "一个账号可绑定多个 BU：负责人管几块业务，一个号全看，顶部一键切换。",
            "每天可设多个自动更新时间点（如 9:30 / 12:00 / 17:30），数据更新更及时。",
            "管理端「一键更新并重启」：有新版本时点一下即可升级，无需人工换文件（配部署侧看门狗自动重启）。",
            "「收入与毛利结构」板块：按客户 / 按销售看收入与项目毛利、前 5 大集中度。",
            "异常处理更清晰：数据修正 / 配置变更记录分开，改过什么一目了然。",
        ],
    },
    {
        "date": "2026-07-12",
        "title": "试运行首版：经营罗盘全貌 + 管理端版本页",
        "items": [
            "四大板块：基本情况总览、经营利润（含可展开到费用明细的管理利润表）、"
            "收入与毛利结构（按客户 / 按销售）、下单与回款排名。",
            "账号登录分权限：管理员可改数、「整体」账号看全公司、BU 账号只看自己那块。",
            "顶部时间选择器（年 / 季 / 月）一键切换；手机扫码即可看；暗色科技风、可切浅色。",
            "每个数字标注来源（智云 / 台账 / 手填），自带数据体检自检面板。",
            "管理端：改数留痕、异常处理分诊、每日定时自动更新、每日历史快照可回看。",
            "新增本页：管理端可见「产品版本号 + 更新日志」，一眼知道现在是哪一版、每版改了啥。",
        ],
    },
]


def changelog() -> list[dict]:
    """返回更新日志副本（防调用方误改常量）。"""
    return [dict(e, items=list(e.get("items", []))) for e in PRODUCT_CHANGELOG]


def version_info() -> dict:
    """给 /api/version 下发的结构：版本号 + 阶段 + 标签 + 更新日志。"""
    v = read_version()
    return {
        "version": v,
        "stage": product_stage(v),
        "label": product_label(v),
        "changelog": changelog(),
    }
