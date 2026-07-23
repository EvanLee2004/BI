# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 1.1.0，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **版本以根目录 `VERSION` 文件为准。**  
> git tag 只存本地、**不推远端**（数据安全策略；公开仓零 tag 属有意为之）。  
> 素材合并自：`docs/CHANGELOG_stage54系列补记.md`（已删）、`src/version.py` 管理端文案注记（只读抄录）、本地 tag 序列。

---

## [2.3.4] - 2026-07-23

### Changed
- **周期「自定义区间」**：只保留起月 / 止月 + 应用（真·按时间筛选）；**去掉**底下 1-2月、2-3月… 固定快捷组合墙
- 预览仍映射后端已有 `period_keys`（前端不算金额）；起止相同落单月 key
- **BU 页「← 整体」**：仅 `session.can_main`（整体/管理员）或快照整体包显示；纯 BU 账号不渲染，避免点进「无整体驾驶舱权限」
- 服务端 `bu_body.html` 去掉硬编码「← 返回整体」（无会话权限，死链）

### Notes
- 年 / 季 / 月 tab 不变；无利润口径变更；`/api/v1/session` 已有 `can_main` 字段

---

## [2.3.3] - 2026-07-23

### Changed
- **手填项目名（陆总 0723）**：固定运营三项 `房租`→`房租物业`、`物业费`→`其他`（role 仍固定运营；装修费不变）
- **`manual_alloc_category_map` key** 同步为 `房租物业` / `其他` / `装修费`
- **库 key 幂等迁移**：打开/ensure DB 时 `manual_手填` / `manual_手填BU` 旧项目名→新名；冲突则金额整数分相加后删旧；`manual_历史.项目` 字符串一并改

### Unchanged（红线）
- **`manual_alloc_fine_types`** 仍为台账核名 `["房租","物业费","装修费"]`（禁止改成手填新名，否则双计）
- 利润/分摊/去税算法、`fetch_zhiyun` 零改动

---

## [2.3.2] - 2026-07-23

### Changed
- **交付成本构成抽屉**：`系统内部译员`、`直接成本增值税` 两项显示负号（U+2212），与加减方向一致；主表与费用类抽屉不动
- **管理利润表**：标签「管理毛利」改为「毛利」（仍为金额）；其下新增「毛利率」行（读现成 gross_margin_pct，无新计算）
- **毛利率 / 税前利润率** 右侧数值用与税前利润同档绿色强调（霓虹/深色/浅色三主题）

### Notes
- 纯展示层：`src/profit/*` 与核心数字零改动

---

## [2.3.1] - 2026-07-23

### Added
- **霓虹 HUD 面板**：四角角标、clip-path 切角、顶流线、hover 发光（仅 `data-theme=neon`）
- **霓虹空间背景**：网格极慢漂移 + 扫描光带（仅 transform/opacity/background-position）
- **霓虹 KPI**：大数双层光晕、五卡 stagger 入场、hover 上浮、进度条发光
- **图表光效**（`fxLevel===1`）：柱顶高亮帽、折线面积、环形外发光
- **切 BU 转场**（三主题）：淡出→load→淡入 + KPI 重跳

### Changed
- count-up **三主题都播**（仅 `prefers-reduced-motion` 否决）；终帧仍直赋 `value_disp`
- logo 入场改为**每次刷新**填充加载：min 900ms / max 1600ms / 可跳过；admin 与快照不播
- live 主题测改为断言 `data-theme`，并保留 light 下 `theme-light` 兼容断言

### Notes
- ECharts 主包 gzip ~235KB 构成写入交付报告（明昊接受，不开异步拆包）

---

## [2.3.0] - 2026-07-22

### Added
- **三主题体系**：霓虹（默认）→ 深色 → 浅色循环；`data-theme` + 兼容层 `theme-light`
- **霓虹图表闪光**：`fxLevel` 仅在霓虹且非 reduced-motion 开启；暗/亮仍强制 `animation:false`
- **登录入场**：账号密码登录成功后播放甲骨易 logo 放大特效（可跳过；快照/管理端/刷新不播）
- **KPI count-up**：霓虹下数字滚动；中间帧用后端 `value` 插值，终帧直赋 `value_disp`
- **导出快照主题**：pack 含 `theme` 字段；离线可切三主题；密级页脚「内部资料 · 请勿外传」
- ECharts 按需引入瘦包（core + bar/line/pie/heatmap + canvas/svg 双渲染器）
- `/api/health` metrics 写真实 `update_ms` / `fetch_fail_rate`（去掉恒 null 的 `api_p95_ms`）

### Changed
- 主题按钮文案三态：◈ 霓虹 / ◐ 深色 / ◑ 浅色（仍含「深色」「浅色」字样供测试定位）
- 首次升级 `cockpit-theme-v2` 标记强制默认霓虹；之后尊重用户选择
- 管理端恒暗色，不读/不污染看端 localStorage 主题

---

## [2.2.9] - 2026-07-22

### Changed
- **导出主路径 = 方案 A 自包含静态可交互快照**：`/export.html`、`/api/export.html`、`/bu/{name}/export.html` 下载单文件 HTML，内嵌 `kind=kanban_snapshot` 数据包 + Vue 播放器（`frontend/dist-snapshot`）；`file://` 可离线打开，可切周期、展开利润表、看期间费用等图；整体包含全部已发布 BU 可切换，BU 包仅本 BU
- **禁止残壳假成功**：`KANBAN_OFFLINE=1` 或 Playwright 不可用时仍出真快照；装配失败 → HTTP 503；退役 `capture_vue_export_html` / `fallback_export_html` 作为成功主路径（`/export.png` 与 `/?archive=` 保留）
- **顶栏今日日期**：在线整体页与 BU 页版本号左侧显示本机 `YYYY-MM-DD`（`tb-today`）

### Added
- `export_html.assemble_export_pack` / `build_snapshot_export_html`；前端 `snapshotMode` + 快照 banner；`vite.snapshot.config.ts` + `dist-snapshot/`
- tests `test_task_2_2_9.py`

---

## [2.2.8] - 2026-07-22

### Changed
- **行数对账容差**：智云翻页抓完后，`|实际行数 − 接口 total| ≤ max(5, ceil(total×0.5%))` 时接受（解决并发多/少几行误拒，如 total=23498 实际 23501）
- **体检灯色方案 B**：绿=本轮应抓源都抓到且无业务提醒；红=有源本次未抓到（local_fallback/no_source）或硬故障；黄=抓齐后仍有业务提醒（手填缺月/未归属 BU/调整过期/骤降警告等）
- **横幅文案**：「今日未抓到」→「本次未抓到」+ 短原因 + 本地文件 as_of（含时分）
- **同名日期控件**：只记 info，不进 warnings、不驱动黄/红
- **未配置台账 share**：有本地文件时标 `fetched`，开发机不因无共享天天红；已配置但不可达仍 `local_fallback`→红
- **zhiyun_auto_fetch 关**：不因智云未在线抓而红（管道不写 fetch_zhiyun 键）

### Added
- `ROW_TOTAL_ABS_TOL` / `ROW_TOTAL_REL_TOL` / `row_total_tolerance()`；tests `test_task_2_2_8.py`

### Fixed
- 生产误黄：内部译员因多 3 行对账失败 → local_fallback 横幅

---

## [2.2.7] - 2026-07-22

### Changed
- **三合一 Vue 皮**：日常展示 / 历史回看 / 导出带走统一为同一套 Vue 经营看板界面
- **历史 = 数据时点存档**：`generate` 成功后写 `数据/备份/vm_YYYYMMDD.json`（同天覆盖）；管理端「打开」→ `/?archive=YYYYMMDD` Vue 只读横幅；**停写** `页面_*.html`
- **导出主路径 HTML**：`/export.html`、`/bu/{name}/export.html`（鉴权矩阵与原 PNG 一致）；前端 `TopBarActions` 默认 `.html`；`/export.png` 兼容保留
- **管理端去掉顶栏「浅色」**（登录页主题钮一并去掉）；展示 iframe 内 `ThemeToggle` 保留

### Added
- `GET /api/history/{day}/vm`：管理员读归档 VM
- `snapshot_vm` / `list_vm_archives` / `load_vm_archive`；`export_html` 模块（Playwright 抓 Vue 优先，失败降级壳）
- tests `test_task_2_2_7.py`

### Removed
- 历史列表对 `页面_*.html` 的依赖；旧 `GET /api/history/{day}` HTML 回看 → **410**

---

## [2.2.6] - 2026-07-21

### Changed
- **下单未填部门批量 UX**：去掉顶栏「本页销售筛选」；筛选只在表头（销售/下单日期）；批量只处理**本页 × 表筛结果**；确认框明示「仅当前页」+ 筛选条件 + 笔数 + 金额合计 + 归入部门
- 换页时重置列筛选（避免旧筛挂在新页）

### Added
- `POST /api/adjust/batch`：预检全过再写、同一事务多条调整、**一次** `recompute`（策略 A）
- tests `test_task_2_2_6.py`

---

## [2.2.5] - 2026-07-21

### Changed
- **管理端长列表翻页**：配置变更/数据修正/费用未分类/下单未填部门/历史快照日表/异常总览/数据调整 统一上一页/下一页，每页 50；筛选或刷新归第 1 页；表单类视图不加分页
- **「看」→「展示」**：管理端顶栏页签及用户可见「看」措辞改为展示/显示；`group:'see'` 与产品名「经营罗盘」保留
- **`/api/version`**：任意登录会话可读（展示端顶栏版本号）

### Added
- 展示页顶栏甲骨易 logo（`import` → `/app/assets/*.png`，兼容 nginx 只缓存 assets）+ 产品版本号（拉 `/api/version`）
- tests `test_task_2_2_5.py`（含构建产物 PNG 门禁）；`useClientPager` 客户端分页 composable

### Fixed
- logo 路径：禁止裸 `/logo.png`（Vite base 写成 `/app/logo.png` 时 nginx 回 SPA html）；改为 assets 指纹路径

---

## [2.2.4] - 2026-07-21

### Changed
- **① 时间选择器左上**：整体页/BU 页 `PeriodPicker` 归 `.tb-left`（标题旁）；主题/退出/导出在右上
- **B 毛利率卡**：KPI「管理毛利」→ 标题「毛利率」、大数字=`gross_margin_pct`%、毛利额副行（key 仍 `gross_profit`）
- **D 回款卡改名**：「回款情况」→「下单/回款情况」
- **A 装修费归固定运营**：`manual_alloc_category_map` 装修费→固定运营费用（重分类中性·total/pretax 不变）
- **F 管理端退出**：顶栏移除；设置页底部「退出登录」

### Fixed
- **C 回款基准线**：`ReceiptsCard` y 轴 `axisMaxCover` 纳入 `budget_month`，游戏等低量 BU 虚线不再被裁
- **E 公共费用总额**：`manual.py` `_alloc_month_payload` 显示前分÷100 转元
- **G 进入门槛**：数据源缺失/未配置不再硬拦 `run.py`；无 summary 返回友好空态（保留登录鉴权）

### Added
- **② 手填三类进三视图**：`inject_manual_alloc_into_breakdowns`；利润中心/部门组「人工分摊(公共)」
- **③ 导出 PNG 按钮**：`TopBarActions` → `/export.png` / `/bu/{name}/export.png`（后端截图链路不动）
- tests `test_task_2_2_4.py`、`test_expense_zhuangxiu_alloc.py`

---

## [2.2.3] - 2026-07-21

### Changed
- **期间费用三态交互**：按类别 / 按利润中心 / 按部门 由左右分栏（及行内嵌展开）改为「进度条列表 + 点击行右侧抽屉展开明细」，复用管理利润表同套抽屉；口径/数据零改

### Added
- tests `test_expense_drawer.py`（抽屉门禁）

### Removed
- tests `test_expense_md_unified.py`（master-detail 门禁下线；本版未入库）

---

## [2.2.2] - 2026-07-21

### Fixed
- **收入与毛利结构左右顺序**：左「按销售」、右「按客户」，与「下单与回款」双卡一致（此前左右反了）
- **点费用「按部门」误弹红条**：全局错误上报忽略 Chrome 无害 `ResizeObserver loop…`；ECharts resize 经 rAF 合并降噪

### Added
- tests `test_ui_sales_customer_order_and_ro_filter.py`（顺序 + 过滤 + dist 门禁）

---

## [2.2.1] - 2026-07-21

本地 tag：`stage66_ship`（只本地不推 tags）。**性质：2.2.0 生产封板（`stage66_debtfree` / `9e50868`）之后的收尾补丁包**——封板后又叠加 9 个 commit 但版本号一直停在 2.2.0，本次收口为 2.2.1，让版本号与代码一一对应。

### Added
- **看端费用明细表头筛选**：Excel/数据调整式可选值多选（`filters.in` + `/api/v1/vm/ledger/values`），不再盲输
- tests `test_ledger_excel_filter.py`；API `GET /api/v1/vm/ledger/values`

### Changed
- **生产加固**：nginx 入口安全头继承修复 + `systemd` 模板 `User=lee` 沙箱；`StartLimit*` 移入 `[Unit]`（新版 systemd 兼容）
- 明细筛选 number/date 列 `filters.q` 走 `CAST LIKE` 收窄；空串 `in` 可筛、text 列多选

### Fixed
- **nginx `X-Frame-Options` DENY→SAMEORIGIN**：恢复管理端「看」页 iframe（之前 DENY 把内嵌看端挡了）
- stage66 skeptic 缺口：随机重算等价、`_log_run` 真路径、文档七图重导可见 2.2.0 内容

---

## [2.2.0] - 2026-07-21

本地 tag：`stage66_debtfree`（只本地不推 tags）

### Changed
- **A 金额整数化**：split_tax / 去税 / 附加税费 / 手填入口 Decimal 分上 ROUND_HALF_UP；golden 对账数值零 diff
- **B 增量重算**：源指纹未变时手填跳过 std 重建；调整类 `rebuild_std=True`
- **C VM 契约**：`scripts/gen_vm_ts.py` 生成字段清单；verify `--check` 防漂移
- **D 抓数护栏**：登录连败冷却 24h（体检红）；7 日行数基线；Worksheet 探活；1 月 0 行信息级
- **D 回款重复口径（明昊拍板）**：定位键重复不判黄，体检 `info` 展示

### Added
- MADR 整数分 / 增量重算 / VM 生成 / 回款黄灯口径
- tests `test_task66_stage66_batch_{a,b,c,d}`

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
