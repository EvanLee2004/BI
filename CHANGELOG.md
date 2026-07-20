# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 1.1.0，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **版本以根目录 `VERSION` 文件为准。**  
> git tag 只存本地、**不推远端**（数据安全策略；公开仓零 tag 属有意为之）。  
> 素材合并自：`docs/CHANGELOG_stage54系列补记.md`（已删）、`src/version.py` 管理端文案注记（只读抄录）、本地 tag 序列。

---

## [2.1.0] - 2026-07-20

本地 tag：`stage65_clean` / `stage65_clean_fix`（只本地不推 tags）

### Changed
- **L1 管理端 Vue 单轨**：删除 legacy `static/admin/admin.js` / `admin.html.legacy` / `admin.css`；`/admin` 仅 Vue SPA + 首次引导 bootstrap；`/admin/app.js` 恒 410
- **L2 渲染按需（含 fix）**：`publish()` 不预装 `user_html`；`has_data` 显式标志；`/export*.png` 按需 `assemble_export_html`（同 `built_at` 缓存）；**`build_bu_pages` 刷新路径不再调用 `assemble_bu_dashboard_html`**（仅 summary/fragments/views；导出/历史快照按需装配）；主页历史快照仍在 `generate()` 内装一次
- **L4 架构守卫**：routes 不得直连 import server；static/admin 白名单

### Fixed
- skeptic 回修：L2 成本目标（刷新零 BU 整页装配）；诚实 `assemble_export` 单测；PNG 与同 HTML 连截噪声同量级证据

### Removed
- legacy 管理端静态骨架与双轨分支 `_admin_is_vue`

---

## [2.0.3] - 2026-07-20

本地 tag：`stage64_ship`（完成后打；只本地不推 tags）

### Changed / Security
- **批次 P**：密码口径回退明文（管理员可见可改，MADR-0020）；`chmod 0o600` 私密写盘；保留防爆破/12h 会话/改密踢会话/审计不记明文
- **批次 D**：备份 VACUUM INTO；std 索引；`_state` 原子发布；normalize 业务线走配置；Vue 全局错误条；golden 重锚脚本；清理死 golden；nginx/systemd/healthcheck 加固；工程一致（create_all 一次、routes 共享 server helper、package 钉版本）
- **批次 E**：智云跨年年度归档 + 台账跨年 SOP 文档

### Fixed
- 外部审查 H-05 按产品拍板回退并如实记录「风险已知悉、接受」

---

## [2.0.2] - 2026-07-20

本地 tag：`stage63_security`（完成后打；本段随 A/B/C 批次累加）

### Security / Fixed
- **批次 A**：批量手填/预算原子提交（F-02）；分摊比例/去税率写删追加历史表（H-04）；调整撤销/坚持/批量撤销可选理由 + 配置审计（H-03）；测试依赖迁入 `requirements-dev.txt`（M-02）
- **批次 B**：账号密码 PBKDF2 哈希存储；明文自动迁移备份；`/api/accounts` 不下发密码；`POST …/reset_passwd` 管理员重置；会话 TTL 12h（H-05）
- **批次 C**：前端金额字面量守卫改为显式白名单；去掉 `1e-4` 规避写法（M-01）

---

## [2.0.1] - 2026-07-20

本地 tag：`stage61_beta201`

### Changed
- 回款卡：删「尚待回款 / 年标签 / 回款占下单 / 黄回款率线」；文案改「本年下单 / 本年回款」；年目标进度条有则显
- 月度图 x 轴裁到当前系统月（尊重 `period_pin`）；删除费用月度趋势折线卡 ExpenseTrend
- 排名双卡：前 N 名标注、「其余」完整弹层；**按下单额降序**
- 管理端 / 看端列筛选；期间费用「按部门」master-detail
- 人工填写分摊对齐 `/api/alloc_ratios` + `ratios`
- 房租 / 物业费 / 装修费：台账默认口径剔除 + 人工按 BU×月分摊（未填=0）
- BU 公共分摊重算保留三类人工分摊（mac）

---

## [2.0.0-rc13] - 2026-07-20

本地 tag：`stage60_prod_fix`

### Changed
- 每日到点自动更新改为服务进程内 ScheduleLoop，页面数据随到点刷新
- 同浏览器管理员 / BU / 整体登录 cookie 互清，身份以最后一次登录为准
- 生产：Ubuntu systemd `kanban` + nginx:80 发 dist + 反代

---

## [2.0.0-rc12] - 2026-07-19

本地 tag：`stage58_ui`

### Changed
- 费用明细：日历起止（收单日期日级）+ 查询 / 本月 / 返回本年
- 「下单与回款·按时间段查询」加「本月」快捷

---

## [2.0.0-rc11] - 2026-07-19

本地 tag：`stage57_gold`

### Changed
- 无限打磨收官：友好网络错误、交接包终版、domain 覆盖与全量复验

---

## [2.0.0-rc10] - 2026-07-19

本地 tag：`stage56_final`

### Changed
- 终局清尾 R-40~R-46：C901 收敛、vulture 死码清零、费用明细默认期间费用视图 +「显示全部」

---

## [2.0.0-rc9] - 2026-07-19

本地 tag：`stage55_final`

### Changed
- 终局封板：友好网络错误、交接包终版、`run_verify` 全绿

---

## [2.0.0-rc8] - 2026-07-19

本地 tag：`stage55_rc8`

### Changed
- 费用折线 / 热力公共白名单剔「成本」「非利润表」；热力 tooltip 不裁切

---

## [2.0.0-rc7] - 2026-07-19

本地 tag：`stage55_rc7`

### Changed
- 工程完美收官：render/server/db/profit 拆分、domain 覆盖量化

---

## [2.0.0-rc6] - 2026-07-19

本地 tag：`stage55_rc6`

### Changed
- 人审二轮：工资全隐、空态引导、卫生清零、友好错误页

---

## [2.0.0-rc5] - 2026-07-19

本地 tag：`stage55_rc5`

### Changed
- 主题即时切换、图表不裁切、费用热力图、弹层 z-index token

---

## [2.0.0-rc2] - 2026-07-19

本地 tag：`stage55_rc2`

### Changed
- BU 入口、两段式时间选择、弹层不叠字

---

## [2.0.0-rc1] - 2026-07-18

本地 tag：`stage55_rc1`

### Added
- 可上线人审版：看端 / 管理端统一、手册与健康检查、上线交接包

---

## [2.0.0-beta] - 2026-07-17 ~ 2026-07-18

本地 tag 线：`stage54` … `stage54p9`（Vue 重构与 SciFi 阶段）

### Added / Changed
- Vue 看端 + 管理端 SPA、安全底座、口径配置引擎（公测 Beta v2.0）
- SciFi 皮肤、去 Windows 部署线、B-01 查询原位、美学与终验自修
- 界面翻新：图表 / 明细更清晰、可退出登录

---

## [1.6.0] - 2026-07-16

### Changed
- 费用明细更清晰；支持 Ubuntu 部署；登录与月度下钻更稳
- 上线终检：看板打开更快、跨年更稳、从零部署手册
- 智云抓数修边界日；抓不全会报警；排名「按月看」加载更轻

---

## [1.5.0] - 2026-07-15

### Changed
- 管理端前后端分离（全系统拆完，界面与数字不变）

---

## [1.4.0] - 2026-07-15

### Changed
- 看端前后端分离（界面像素级不变，数字同一套）

---

## [1.3.x] - 2026-07-14

### Added / Changed
- 费用去税率手填（房租等按不含税还原）+ 完整/精简视图
- 修好费用去税录入表显示；业绩目标跟随顶部筛选

---

## [1.2.x] - 2026-07-14

### Changed
- 陆总过盘反馈：系统成本率、分摊沿用最近月、按 BU 看
- 看板扫读做减法；回款 / 排名统一按 BU；管理端浅色
- 补齐「直接成本增值税」填写入口

---

## [1.1.x] - 2026-07-14

### Added / Changed
- 公共费用可按月分摊到 BU；回款板块重排
- 回款图跟选中月份高亮；台账归属写错会提醒

---

## [1.0.0-beta] - 2026-07 公测

### Added
- 公测 Beta 主线：登录账号分流、管理利润到税前、内网双端

---

## [0.9.x] - 2026-07 试运行

### Added
- 内部试运行：抓数管道、SQLite、预渲染看板

---

## 说明

- **未发布条目**：无。
- **对比链接**：本仓因安全策略不推 tag 到远端，GitHub 上不展示 tag 列表；请以本文件 + 本地 `git tag` 为准。
