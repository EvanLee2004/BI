## 3.5.0 · 2026-07-30

### 金额诚实 · 架构收束 · 完整性可见 · reload 真生效
- **重点客户金额折线**：默认共同金额轴（`value_wan` + `amount_axis`），2万与200万不再同高；直接标签读数；可选「节奏指数」非默认且固定说明峰值=100
- 月点语义 `actual|incomplete|missing`；未来月 null 不与实际 0 混画
- 后端 packer 迁 `src/viewmodels/key_customers.py`；`packers.py` 薄门面
- 前端拆 `key-customers/*` + `useKeyCustomers` + `keyCustomersChart`；VM 类型单源 `types/vm.ts`；选择/对比 SSOT
- 首屏 `data_integrity` 条：体检灯/缺月/未来记录/受影响说明；**不造金额、不改手填**
- `reload_kanban.sh`：旧 PID 消失 + 新 PID + health 200 + runtime version/commit；磁盘 VERSION 不算成功
- 证据：`docs/验收证据/3_5_0/` · 测试 `tests/test_key_customers_3_5_0.py`

## 3.4.3 · 2026-07-30

### 重点客户经营作战台（结构条 · 三池 · 临界晋级 · 三客比较）
- 双饼主视觉改为双行 100% 结构条（客户数 / 金额）；六档 count·amount 守恒
- 四摘要卡：全部客户年累计、S+A+B 贡献率、需跟进重点客（S/A/B 静默）、临界晋级（距上级≤10%）
- 三经营池默认重点 S/A/B；培育 C/D；长尾 E；池内全部/需跟进/临界/搜索
- 客户池与洞察固定同高；未选时行动队列；最多 3 客连续月比较（第 4 客人话阻止）
- Domain/VM 下发贡献率、gap、结构条 wo、趋势摘要；前端零金额/档位/占比业务计算
- **未改**六档阈值、自然年下单预估、is_silent、利润/进料/排名
- 证据：`docs/验收证据/3_4_3/` · 测试 `tests/test_key_customers_3_4_3.py`

## 3.4.2 · 2026-07-30

### 重点客户下单分析体验定稿（L-A · 多销售 · 不预选）
- 标题改为「重点客户下单分析 · {年}」
- 布局 **L-A**：上双饼 → 中名单满宽 → 下折线满宽（废除 3.4.1 左名单|右折线）
- 默认六档全部展开 + 档内限高内滚；C/D/E 全开时自动 ensureTier，禁止假空
- **默认不选中**客户；折线空态「点击上方客户查看 1～12 月下单」；点行才画线
- **多销售**：`sales[{name,amount_disp,wo}]` 金额降序；≤3 全写、>3 前三+另有 N 人；去「主销售」UI
- 选中后折线上方可选销售构成小条（后端 wo）；折线加大 + 当前相关月高亮
- 静默文案强调「当前月不计入」；**不改** is_silent / 分级阈值 / ytd / 守恒
- 证据：`docs/验收证据/3_4_2/` · 活体 L1–L9

## 3.4.1 · 2026-07-30

### 重点客户分析 UI 打磨（上双饼 · 下名单+连续月折线）
- 主布局改为：**上**级分布双饼（数量+金额）→ **下**客户名单（六档）+ 连续月追踪折线 1～12
- 顶区 `help_lines`：口径 / 静默定义 / 主销售定义（后端 packer 下发；行内主销售标签+tooltip）
- 默认策略 A：六档全折叠；展开 body 限高内滚见全；禁止 SAB 默认撑成长列表墙
- 进入面板自动选中最高非空档第一客户并画主区折线；点行刷新追踪图；放大弹层可选
- 架构：不改六档阈值/ytd/利润；Domain→VM→Vue；BU cache 清理 + BUPage :key 保留；embed 全档保留
- 证据：`docs/验收证据/3_4_1/` · 活体 L1–L9

## 3.4.0 · 2026-07-30

### 重点客户分析（自然年下单预估六档 S–E + 双饼 + 四底列表/月钻）
- 整体页 + 各 BU 页「四、下单与回款」最底部（RankingsDual 后）新增重点客户分析
- 口径：自然年 · 下单预估本币 · 每年清零；档 S≥200 · A[80,200) · B[30,80) · C[10,30) · D[3,10) · E(0,3) 万（ytd>0 才进）
- 左：六档列表，S/A/B 默认展开，C/D/E 懒加载可展开；点客户 → 1～12 月下单
- 右：级分布双饼（个数+占比 / 金额到万+占比）；与列表同源守恒
- 数据链：`domain/key_customers` 纯函数 → `summary["key_customers"]`（每年一次）→ packers/VM → `KeyCustomersPanel`
- 懒加载 `GET /api/v1/key-customers/tier`（鉴权同 rankings/full）；导出 snapshot embed 全档
- **未改**利润公式、`fetch_zhiyun`、rankings/full / orders_by_customer 语义；日查不带动本块；切月不重算等级
- 测试：`tests/test_key_customers_3_4_0.py`；前端架构守卫仍绿

## 3.3.3 · 2026-07-30

### 去掉 KPI「目标待校准」展示文案
- KPI 目标进度条 `pct_disp`：超目标（100<pct<1000）显示真实完成率%；极端（pct≥1000）软顶 `>999%`；条宽仍 cap 100%
- 删除 2.6.1 引入的 KPI 占位提示语（陆总判定无用）
- 仅改展示：`kpi_target_bar` / `_attach_year_budget_bars`；**未改**算账、预算 API、目标数值
- 测试：2.6.1/task57 断言更新 + `test_task_3_3_3_no_target_calibration_label.py` 守卫

## 3.3.2 · 2026-07-30

### 更新诚实态 + 体检浮层可见/可滚
- 管理端 `doRefresh`：完成判定看 `last.finished_at` 相对点击前 baseline 是否推进；禁止空 catch 后用旧秒数弹「更新完成」
- 409：running true → 跟进轮询；running false → 明确「系统忙」失败；连点忽略；同 finished_at 只 toast 一次
- 保留体检绿→「更新成功」/ 非绿→「更新完成」
- 体检浮层 `.health-pop`：`position: fixed`；内滚不关；外滚/Esc/点外仍关
- 409 body 补 `running` bool（`status=busy`）；测试 `test_task_3_3_2_refresh_honesty.py` + 2.6.6 守卫升级
- **未改** profit 算账、定时 schedule success 语义、409 互斥锁、智云抓数

## 3.3.1 · 2026-07-29

### 工程债卫生收口（金额 SSOT + 测试假绿 + 文档对齐）
- 分摊展示路径 `alloc_amounts_by_period` / `apply_alloc_to_pc_view`：金额全程 **int 分** + `mul_rates_fen`/`_share_by_pct`，去掉 float 旁路当真相
- 修炸锚测（render_* / templates/render）；阶段守卫 3.3.1；~16 orphan 处置（进门禁/optional/归档）
- 文档 SSOT / Agent / Runbook / progress 与 VERSION=3.3.1 对齐
- **未改** profit 主公式、双榜、智云抓数、分摊业务开关

## 3.3.0 · 2026-07-29

### 管理端「用户统计」+ 配置变更去访问噪音
- 顶栏一级导航：展示 | 数据调整 | 异常处理 | **用户统计** | 设置；路由 `/admin/users`，group=`users`，仅管理员
- 只读聚合 `manual_配置变更` 访问/登录类：主指标=登录成功；三维按账号 / BU 桶（不拆多计）/ 摘要形态 + KPI + 四图 + 明细
- API：`GET /api/v1/admin/user_stats`、`…/events`；`config_changes` 默认排除 `类别=访问`
- 图表异步复用 `echarts-loader`；未改 profit / 智云抓数

## 3.2.0 · 2026-07-29

### server 薄门面 + 残余废物清零
- `server.py` 薄 composition/re-export；实现落 `app_factory` / `middleware_stack` / `refresh_pipeline` / `app_state`
- 稳定契约：`import server` / `_state` 身份 / 可打桩 `_do_full` / `publish` 关键字参数
- 物理删除 `_empty_html_view_fields` 与 VM/API HTML 僵尸字段；进程态无 `user_html`
- `frontend_mode` 恒 `"vue"`；G8 结构门禁进 SERIAL
- SSOT 墓碑路由（fragments 404）与 3.2.0 状态描述；未改 profit 算账

## 3.1.0 · 2026-07-29

### 工程债清零（零行为）
- 文档 SSOT：归档 fragments 合同；现行 `/api/v1/vm/*` + Vue + kanban_snapshot
- 删除 28 个重复 TestRenderRetired；恢复真 G2；新增 G7 卫生闸
- 删除 api 空壳别名、fragments 路由注册、assemble_export_html 误导名
- publish/state 只发 summary+views；删除 static/js 旧拼装
- 部署：`deploy/linux/reload_kanban.sh` 无交互热加载
- 未改 profit 算账

## 3.0.0 · 2026-07-29

### 物理删除 render 驾驶舱双轨
- `git rm` 全部 `src/render*.py` 与 `static/templates/render/`
- 生产装运仅 JSON/VM + 导出 `kanban_snapshot`；`assemble_export_html` 改走 export_html
- 历史 HTML 组装测退役为「render 不可 import」守卫；契约测 `test_g6_3_0_0_no_render.py`
- 未改 profit 算账

## 2.8.0 · 2026-07-29

### 测试迁出 HTML SHA 架构锁
- 废除 `render_pl_table` 全年 HTML `hashlib.sha256` 金样（`tests/fixtures/pl_table_year_sha.txt` 删除）
- 新契约测 `tests/test_g5_2_8_0_pl_structure_contract.py`：`pl_structure` / packers / extract_numbers 关键行 `*_disp` 对齐
- 为 G6 物理删除 render 扫清 SHA 门禁障碍；未改 profit 算账

## 2.7.9 · 2026-07-29

### JSON/VM 路径去除 import render
- 生产 recompute/generate/build_bu_pages 只装 build_json_views（format）；HTML build_cockpit_views 退出生产路径
- 生产业务代码（非 `render*.py`）静态闸：`rg "import render|from render"` 零命中
- 显示辅助 `_esc` / `_rank_amt` / `attach_monthly_to_dual` 等迁至 `viewmodels/format`
- `api_v1.rankings_view_for_period`、packers、data_api 日查双榜、domain 门面不再依赖 HTML 装运层装 JSON
- domain 分包去掉 HTML re-export（算账/结构函数保留）；HTML 兼容路径仍经 `render*.py`（G5/G6 再物理删）
- 契约测 `tests/test_g4_2_7_9_no_import_render.py` 进 run_verify SERIAL
- 未改 profit 算账；无永久 dual flag

## 2.7.8 · 2026-07-29

### 导出 HTML 与 PNG 同源 kanban_snapshot
- PNG 与 HTML 共用 `assemble_export_pack` → `build_export_html`（`kanban_snapshot` 播放器）
- 删除 PNG 路由对 `assemble_export_html` / `render_dashboard` / `render_bu_page` 的依赖
- `export_png.screenshot_png`：快照页用临时 file:// 打开以执行 ES module，等 KPI 文案后再截
- 契约测 `tests/test_g3_2_7_8_export_same_pack.py`；run_verify SERIAL

## 2.7.7 · 2026-07-29

### 刷新停建 HTML 驾驶舱碎片 + 废止 fragments API
- 刷新/重算（`do_recompute` / `do_full` / publish / `core.generate` / `build_bu_pages`）不再调用 `build_dashboard_fragments` 全量装配；运行态 `html=""`、BU `fragments={}`
- `GET /api/v1/cockpit/fragments` 与 `GET /api/v1/cockpit/bu/{name}/fragments` 恒 **404**（detail 指向 `/api/v1/vm/*`）
- 看数唯一链：Domain→packers→`/api/v1/vm/*`→Vue；前端 `frontend/src` 对 fragments 零调用；无永久 feature flag 双轨
- 导出/遗留 assemble 链仍可按需 `build_dashboard_fragments`（G3 再收）；未改 profit 算账
- 契约测 `tests/test_g2_2_7_7_no_html_fragments.py`；相关历史测改为 404/空 fragments/按需 assemble
- run_verify EXIT:0；回归 32 周期零 diff；浏览器两轮 overall+≥2 BU+管理端

## 2.7.6 · 2026-07-29

### VM 数字契约锁死
- 契约测 `tests/test_g1_2_7_6_vm_numbers_contract.py`：全年 KPI / PL 关键行 / ranking total / trend 样本点与 `extract_numbers` 一致
- 只比数字与 `*_disp`，禁止新增 HTML SHA 作架构锁；未改算账、未删 render
- 历史 VERSION 钉死测改为跟 tip / 不低于里程碑，避免每升一版全红

## 2.7.5 · 2026-07-29

### 口径标注方案 A（含税 / 不含税小字）
- 交付金额卡小字「含税」；副行「不含税 · ÷1.06」（数值仍为后端 `revenue_net`）；峰值「全年峰值 · {月} · 含税」
- 趋势标题/图例「收入(不含税)」；整体+全部 BU 同源 packers→Vue
- 未改算账公式；前端不自除 1.06；未删 render；未动导出
- run_verify EXIT:0；回归 32 周期零 diff；浏览器两轮截图自检

## 2.7.4 · 2026-07-28

### 设置页双列上下对齐
- 管理端「设置」四张中卡改为真正的两列堆叠：左列自动更新→运行日志，右列备份清理→智云账号；两列顶对齐

## 2.7.3 · 2026-07-28

### 更新/重启可见维护页 + 全链路清理
- 一键更新 / systemctl 重启 / 冷启动窗口：用户端稳定显示「系统正在更新中」维护页（自动刷新，Cache-Control: no-store）
- 维护标志 `数据/maintenance.flag`（gitignore，防一键更新 dirty）+ 超时 10 分钟强制关闭并写告警
- nginx：页面入口 flag/502/504 出维护 HTML；`/api/` 禁止 intercept 劫持 JSON；保留 location=/ 反代
- 管理端一键更新文案说明用户端将显示维护页；Runbook/部署手册写死 pull 后 nginx 三步

## 2.7.2 · 2026-07-28

### API 写路径与卫生收官
- adjust* / refresh / refresh_status / my_passwd / update/apply / health 全部 `/api/v1/*`；旧路径 404
- 前端 + healthcheck.sh + 测试对齐；同 handler 不复制业务逻辑
- 文档 Agent API 全表；债台账写路径已清；VERSION=2.7.2
- 回归 32 周期零 diff；活体可看可调

## 2.7.1 · 2026-07-28

### 干净目标态接力
- 会话：只认 `kanban_sid`；删旧 cookie 读与 21 天窗；登录 delete 旧名；旧 cookie 不能登录（须重登）
- 业务读：仅 `/api/v1/*`；旧业务 GET 路由删除 → 404
- 前端：只 vue；删 `frontend_mode==legacy` HTML 建造
- 文档：progress/Agent/Runbook/文档SSOT指针 = 2.7.1
- 回归 32 周期零 diff；浏览器 live 可看

## 2.7.0 · 2026-07-28

### 架构双源 / 文档 SSOT / 算账旁路 / 前端 v1+token
- B1/F1：`GET /api/v1/rankings/profit` + 兼容旧 path（2.7.1 已删旧 path）；ProfitStructure 主路径 v1
- B2：`/api/v1/admin/detail`；Agent 写清 detail vs ledger
- B3：render=导出/碎片辅助；fragments 冷启动懒构建已有保底
- B4/B5：单 worker；legacy cookie 窗（2.7.1 已关）
- C1/C2：core/structure 金额 int 分
- F2：Toast/BUPage/密码层 z-index 走 tokens
- O5：progress/Agent/Runbook/债台账 + `docs/文档SSOT指针.md`
- 回归 32 周期零 diff

## 2.6.13 · 2026-07-28

### 算账金额 SSOT 与双路径统一（int 分）
- U-01：`expense_totals_from_man_led` → `dict[str,int]`；`build_period` / `_apply_expense_and_pretax` 只调 SSOT + `pretax_profit_fen`；删内联五行与 `round(float(exp…))`
- U-02：台账 by_cat / fine / group / 月矩阵金额桶 int 分
- U-03：BU 分摊 `mul_rates_fen` + led 写回 int 分
- 回归 32 周期零 diff；用户可见数字与 2.6.12 同库同口径

## 2.6.12 · 2026-07-28

### 完整排名月钻统一 + 密码自由化 + 排查收口
- F-01：`RankList` 完整排名弹层与主列表同 click 契约（`onItemClick` + `mkey`）→ 弹层内点人名可开 1～12 月下单/回款
- F-02/F-03：密码非空即可（取消至少 8 位）；`_write` 禁止空密静默变 8888
- F-04：月末快照仅 `_SNAPSHOT_OK` 算 exists（半截可补做）
- F-05：利润排名 total_rev 改分项去税再加总（1 分守恒）
- F-06：PRODUCT_CHANGELOG 补 2.6.11 + 2.6.12；VERSION=2.6.12
- F-07：费用双路径本单不做

## 2.6.11 · 2026-07-28

### 全站展开层 + 真 bug 清零
- B-01：管理利润表抽屉 `drawerOpen` 即挂载，无 detail 显示空态「这条暂时没有构成明细」（禁静默）
- B-02/B-05：`structure_for_vm` 透传 `expandable`+递归 `children`；单测锁 VM 链路
- B-03：抽屉基座 CSS 写入 SPA `tokens.css` 并进 dist（`.drawer{` + `z-index:var(--z-drawer`）
- B-04：去掉 drawer `z-index:60`；统一 `var(--z-drawer, 80)`；theme 与 tokens 不双源同名 class
- R-01：`#periodSync` 去掉常驻 `will-change:transform`（仅 `.is-period-switching` 瞬间）
- ExpenseSection 对齐空态；活体 L1–L6（整体/BU/admin iframe）

## 2.6.10 · 2026-07-27

### 看端体验（用户视角）
- V-1：看端去掉「未归属 BU」橙色技术提示（管理端体检黄条保留）
- V-2：利润排名弹层 items 补 `bar_w`，条有颜色与长短
- V-3：管理端「更新完成，但有问题」→「更新完成」
- V-4：看端原生 alert 清零，改站内 Toast 人话
- V-5：401 按状态码进登录；统一 ErrorState + 出口；错误文案不透 HTTP 码
- 金额与利润口径不变

## 2.6.9 · 2026-07-27

### 看端 / 管理端
- S7：theme.css 与 components 双源 class 冲突清零（SPA 唯一源 + 守卫测试）
- S3：删 IntroSplash / BU 页「← 整体」；空状态文案统一「暂无数据」；管理端 MessageBox/霓虹主题；margin_disp→cost_pct_disp
- S1：人工填写多列并排（全公司+BU）
- S2：业绩目标金额录入/显示统一「元」（库内分不动）
- S4：账号可看整体页显式标志（行为兼容）
- S5：智云 0 行本地文件 stale 保留，禁止 unlink
- S6：存量重复调整较晚空操作 id 标已撤销（保留较早真实变更）
- S8：删除死端点 `/api/v1/admin/budget_depts` 等

# Changelog

## 3.6.0 — 2026-07-31

### 完美收口
- 可信离线门禁 + offline_seed；runtime skip=0
- 启动安全：install_state、LKG、TERM 非崩溃、reload_verify、Excel 稳定复制、备份 manifest
- 持久调度账本 + 四层健康
- 密码 PBKDF2、禁明文回显、CSRF Origin、安全响应头
- 重点客户选中系列共同零轴、最多五客
- 老板看端中性新鲜度（无橙色 technical yellow 全宽条）

### 热修 · KPI 五卡（产品拍板撤回利润主卡）
- **仅**恢复 `KpiCards` 为 `kpi-grid kpi-5` 五卡并排 + 卡内 BU 进度（与 3.5 一致）
- 撤回 `kpi-host--hero` / 通栏税前利润主卡 / `kpi-bu-strip`；中性新鲜度等其它 3.6.0 能力不动
- 守卫：`tests/test_g5_boss_ui_3_6_0.py` 改为断言五卡、禁止 hero



## 2.6.8 · 2026-07-27

后端数据正确性与台账可信度（**数字口径零变化，回归红线守住；不改 DDL**）：

- **T1 台账降级说人话**：`local_fallback` 告警/体检/黄条点名源 + 本地副本时间 + 数据止于；禁止「体检红：红」；`business_gaps.ledger_fallback*` + 管理端缺口块。
- **T2 费用定位键含「事项」**：仍撞则稳定 `#n` 后缀；旧唯一键 adj 经 `db_write.remap_adj_locators` 迁新键（业务层零裸 SQL）。
- **T3 调整幂等 + 撤销撤净**：同(表,定位键,字段) 生效只保留一条；撤销时同键兄弟一并已撤销。
- **T4 共享盘短重试**：`ledger_share_retries`/`ledger_share_retry_delay_sec`；fstab 步骤单只写不执行。
- **T5 双轨 API 契约测试**：`/api/v1/rankings/profit`↔`/api/v1/rankings/full`、`/api/v1/admin/detail`↔`/api/v1/vm/ledger` 鉴权与行数契约（不删旧端点）。
- **T6 历史不记空操作**：manual 手填/分摊比例/去税率/预算 新旧相等跳过历史（存量不删）。

## 2.6.7 · 2026-07-27

验收回修 + 存量问题清零 + 顶栏统一（**数字口径零变化，回归红线守住**）：

- **A 门禁**：三主题定义 `--orange` 后去掉 BuNav 兜底；F-2 扩扫 admin/** 并清硬编码；五处 `or True` 改成真断言；管理端四页签独有文本重测；skip 清单 + `run_verify` 打印位点计数。
- **B 顶栏**：全站横排 主题｜导出｜密码｜退出；删除 ⋯；管理员无密码/退出（设置页最下唯一退出）；退出 DataModal 二次确认；红色告警横幅 + `/api/alerts/ack` + health.alerts 下线（告警仍写 告警.log）；黄条不动。
- **C P0/P1**：智云 0 行 vs 缺列拆分支（0 行不沿用旧 xlsx）；publish 无 clear 空窗；定时 success 只在管道真成功后登记；匿名 health 脱敏；bu_config 刷新中 409；月末快照 .partial；导出 VM 失败显式抛错。C-8 证同可收敛、C-9 证不同→待拍板。
- **D P2**：generate finally；CLI 缺年 sheet soft；空密码不填 8888；BU/本地配置原子写；login_guard 过期淘汰；BU pl.xlsx 先鉴权；admin form 登录审计；prune 用 localtime；401/403 分离。D-9/D-11 待拍板。
- **E**：PRODUCT_CHANGELOG 补 2.6.1–2.6.7；税率公式取配置；progress 生产/本地 HEAD 分写。

## 2.6.6 · 2026-07-26

六项深度体检 + 发现即修（**不改金额/口径/智云抓取**）：

- **T1 数据完整性**：生产实测手填缺 1–5 月、定位键重复 19 组等；报告 `…/3_测试/20260726_数据完整性体检/`。
- **T1/T2 黄条**：`/api/v1/health` 增 `business_gaps`（缺月/影响/谁补/未归属）；管理端展开 + **滚动/Esc/点外收起**；整体 VM 挂 `unassigned` 差额标注。
- **T3** 本地空机灾难演练 + `Ubuntu部署手册` 附录恢复步骤 + 跑路清单。
- **T4** 新人文档可用性审计 + 最短启动/告警/禁碰。
- **T5** 真·全量 `server.refresh` 叠库压测 1/3/5/10× = 21/61/104/215s（≪300s；台账年页 `2026` 保留；无产品码性能补丁）。
- **T6** 《数字口径说明书》给业务方。

## 2.6.5 · 2026-07-26

前端三层统一 + 排名弹层修复 + 全量体验（**不改金额/口径/智云抓取**）：

- **A-1 弹层**：`ProfitStructure` 按需拉 `/api/v1/rankings/profit`；端点支持 `bu=` + BU 隔离（不放宽）；整体/BU 弹层 items>0；先红后绿测试。
- **三层架构**：`styles/tokens.css` → `components/base/{RankBar,RankList,DataModal}` → 业务组件无 `<style>`；F-1~F-4 守卫；四处排名 CSS 统一（非 ECharts）；收入榜「系统成本率」列头+解释。
- **切 BU 过场**：1s、「正在计算 XX BU 数据……」、logo/字放大、扫描线、可跳过、reduced-motion；过场期间抑制 KPI count-up 连播。
- **「整体」按钮**：BU 导航首项；仅 `can_main`/管理员可见；BU 账号不可见。
- **体积**：板块五懒加载；首屏 gz ≤90.8KB。
- **补丁 `979e964`（skeptic gap-fill）**：ECharts 图卡经 `cssColor()` 解析为实色（禁 `var(--*)` 进 canvas，消 SyntaxError/红条）；Playwright 18 组真 hook `console.error`+pageerror+拒红条；F-3/export 证据齐全；生产 HEAD=`979e964` built_at=11:44:58。

## 2.6.4 · 2026-07-26


本机告警闭环 + 失效模式守卫（**不改金额/口径/智云抓取**）：

- **内建告警**：`alert_store` 写 `数据/日志/告警.log` + 已读水位；`notify` 只落盘/logging，**零 HTTP 外发**（飞书已废止）。
- **管理端**：`/api/v1/health` 管理员会话附 `alerts` 未读摘要；`POST /api/alerts/ack` 写水位；管理端顶栏未读横幅。
- **守卫**：`tests/test_failure_mode_guards.py` + `test_alert_store_2_6_4.py`；开工检查单 `docs/新功能开发检查单.md`。
- **UI · D1 过场**：切 BU 时全屏 **甲骨易 logo + 目标 BU 名**（`BuTransitionOverlay`）；`transitionToBu` 延时 120+200ms≤800、点击/Esc 可跳过、`prefers-reduced-motion` 降级；无数字改动。

## 2.6.3+ 紧急 · 删除飞书 webhook 告警功能（2026-07-25）

- **硬令**：禁止再向公司大群/「财经新闻」机器人发任何消息（含测试）；本功能从产品中移除。
- 删除：`feishu_webhook_url` 配置与 API/设置页字段；`post_feishu` HTTP 外发；healthcheck 飞书调用。
- 保留：`notify.py` **仅本机 logging**（管道红/看门狗仍写本地日志，不影响主流程）。
- 生产 `本地配置.json` 无 webhook 键。将来告警须单独群+书面批准。

## 2.6.3 · 2026-07-25

全方位隐患清零（20 项 · 排查基线 2.6.2）：

- **A 止血**：账号表原子写 + 损坏隔离不 seed 出厂口令；`db_path` 双拼明确抛错；本地配置危险键白名单；坏本地配置体检黄+告警；空密码 400。
- **B 沉默失败**：healthcheck 新鲜度改 `/api/v1/health` 的 `built_at`；定时刷新补跑+跑批台账；月末漏月补快照；跨年归档 `.partial`+`_ARCHIVE_OK`；缺当年台账 sheet 降级空集+体检红+横幅。
- **C 并发**：管理端写路径持锁，忙时 409「更新进行中，请稍后再保存」；`_BUSY_TIMEOUT_MS=90s`；publish 一次引用替换；`generate` 贯通 `root`。
- **D 门面**：看端首包拆 `vue-runtime` + echarts 异步，看端 deps 不再含 element-plus，首屏 gz 约 90KB（≤260KB）；登录锁定账号+IP；新密码下限 8 位；鉴权先于存在性；**实现** `KANBAN_PROFILE` 读 env 套 `config.profiles`；health 版本/info 仅登录后；pre-restore 纳入清理。

## 2.6.2 · 2026-07-25

- **手机端响应式（B1–B4）**：≤520px 消除整页横溢；台账表容器内横滑；顶栏「⋯」收纳导出/退出/密码；KPI 两列紧凑；趋势图/排名窄屏减标签密度
- **桌面不变**：≥1100 仍五卡 KPI、顶栏横排工具、无 media 外全局改布局
- **测试**：`tests/test_task_2_6_2_mobile_layout.py`（CSS 契约 + 390 活体 overflow/顶栏）

## 2.6.1 · 2026-07-25

- **本地测试数据（R0）**：BU 销售归属补齐；台账「多语营销」映射到营销；年目标量级校准（仅本机 `数据/`，不上生产覆盖）
- **KPI 展示（R1）**：目标进度超 100% 主文案改为「目标待校准」，禁止吓人 `>999%`
- **包体（R2）**：排名默认不 embed `full_items`；新增 `GET /api/v1/rankings/full` 按需加载
- **观测（R4）**：`/api/v1/health` metrics 始终含 version/built_at/update_ms 等真值字段
- **工程（R7）**：`fetch_zhiyun` → `fetch_zhiyun_pure.py`；`manual` 校验辅助 → `manual_helpers.py`（语义零变更）
- **测试（R6）**：`run_verify` SERIAL 锁 2.6.1；Playwright `scrollIntoView(#rankViews)` 后断言 canvas 挂载
- **体积实测**：export HTML 14.8MB→9.3MB；cockpit 仍 ~13MB（monthly_data 占大头，诚实记录）


本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 1.1.0，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **版本以根目录 `VERSION` 文件为准。**  
> git tag 只存本地、**不推远端**（数据安全策略；公开仓零 tag 属有意为之）。  
> 素材合并自：`docs/CHANGELOG_stage54系列补记.md`（已删）、`src/version.py` 管理端文案注记（只读抄录）、本地 tag 序列。

---

## [2.6.0] - 2026-07-25

### Changed
- **单会话 cookie**：登录只写 `kanban_sid`（HttpOnly + SameSite=Lax；不硬开 Secure）
- **统一 resolve**：`session_ctx.resolve_session`；权限仍只看账号表
- **遗留兼容 21 天**：可读旧 `kanban_session`/`kanban_view` 并静默升级；锚点 `数据/session_legacy_compat_since.txt`
- **退出**：清 sid + 两旧名

### Unchanged
- 2.5.0 统一登录与角色分流；2.4.3 BU 根路径；金额/智云未动

参考：OWASP Session Management Cheat Sheet；MDN Set-Cookie。

---

## [2.5.0] - 2026-07-24

### Changed
- **统一登录入口**：全员只使用 `/login`；删除管理端独立登录 UI（`admin/views/LoginView.vue`）
- **按账号分流**：管理员→`/admin`；整体→`/`；BU→`/bu/{可见BU}`（`src/login_redirect.py`）
- **兼容**：`/admin/login`、未登录 `/admin` → 303 到 `/login?next=…`；`next` 白名单防 open redirect（BU 不可 next 进管理端）
- **退出**：管理端 logout 落到 `/login`
- **static 登录皮收口**：`view_login.html` 透传 URL `next`/`redirect` 进 `/api/v1/login`；`admin_login.html` 与 `templates/login.html` 改为跳转壳（无「管理员端登录」表单）；`_admin_login_file` 303 到统一登录

### Unchanged（红线）
- 权限模型与双 cookie 互清；2.4.3 根路径 BU 回流；金额/智云未动

---

## [2.4.3] - 2026-07-24

### Fixed
- **BU 根路径二次进不去 / 403 空壳**：`location = /` 改为强制 `proxy_pass` 后端（禁止 `try_files /index.html` 绕过 `GET /` 对纯 BU 的 303→`/bu/xxx`）
- **前端双保险**：根路径 + 纯 BU 会话先 `fetchSession` 再跳业务线；`loadMain` 遇 cockpit 403「无整体…」自动回流 `/bu/...`
- **退出登录 cookie**：`delete_cookie` 与 set 一致带 `path=/` + samesite，降低身份残留

### Docs
- 用户口径只推荐两个根链接（内网 / 外网）；Runbook 补 nginx conf 同步 reload

### Unchanged（红线）
- BU 隔离与整体 cockpit 鉴权不削弱；智云抓数 / 金额口径未动

---

## [2.4.2] - 2026-07-24

### Fixed
- **时间选择下拉裁切**：左上 PeriodPicker 面板由 `right:0` 改为 `left:0`（随 2.2.4 归左上后右对齐会把 320px 面板推出视口左侧，裁切「自定义区间」等）
- **窄屏夹紧**：打开/resize/切 tab 时 `clampPanelInViewport` 把面板限制在视口内（左右各 ≥8px）
- rebuild `frontend/dist` + `dist-snapshot`

### Unchanged（红线）
- 周期 key/算账/鉴权/导出逻辑未动；仅定位样式 + 视口夹紧

---

## [2.4.1] - 2026-07-24

### Changed
- **管理利润表导出金额 = 元**：`export_pl_xlsx` 改走全量 `pl_structure` 的 `impact`（分）→ `money.fen_to_yuan`，Excel 数字列 `#,##0.00`；百分比行仍 `%`；数据区金额串无「万」；抬头口径「金额单位：元（页面看板仍为万元展示）」
- **导出按钮暗色适配**：`theme.css` 补全 `button.ghost` / `button.mini`（对齐 `.toggle`）；`.pl-export-btn` 青描边强调；rebuild frontend dist
- 死代码：`packers._amt_disp` / `_abs_amt_disp`（零调用）；导出侧 `_safe_sheet_name` 简化为固定 sheet 名「管理利润表」
- 测试：`test_task_2_3_6_pl_xlsx` 断言改为无万 + 元换算 + 百分比 + HTTP 保留

### Unchanged（红线）
- 页面 KPI/利润表仍万元；`src/profit/*`、鉴权/文件名、顶栏 export.html 未动

---

## [2.4.0] - 2026-07-23

### Added
- **管理利润表导出一页化**：单 sheet「管理利润表」；大类加粗 + details 内嵌缩进浅灰；抬头块（产品/VERSION/范围/周期/时间）；去掉「构成_*」「导出说明」多 sheet
- **公共费用统一分摊（两轴模型）**
  - 数据：`manual_公共明细金额覆盖`(+历史)、`manual_分摊_明细规则`(+历史)；`manual_分摊比例` 语义=默认层
  - 计算：月×明细池（金额覆盖优先）→ 精配比例/金额 → 默认层 → 归回 5 大类；超额报错；余额留公司；`alloc_added_details` 明细级
  - 管理端：默认比例 + 公共明细表（比例/金额切换、房水电可手填覆盖）+ 底部汇总
  - 看板：BU 下钻「分摊自公共·明细项」；前端「其他N项」可展开 children
- 测试：`test_task_2_3_6_pl_xlsx` 单 sheet；`test_task_2_4_0_{schema,calc,admin,display}`

### Unchanged（红线）
- 公司层 total/pretax/毛利/收入/成本 32 周期零 diff；`fetch_zhiyun.py` 未动；前端不做金额运算

---

## [2.3.6] - 2026-07-23

### Added
- **管理利润表 Excel 导出（陆总）**：整体页 + 各 BU 页 `PLTable` 面板「导出 Excel」
  - `GET /api/v1/export/pl.xlsx?blk=`（整体；双挂 `/export/pl.xlsx`）
  - `GET /bu/{name}/export/pl.xlsx?blk=`（该 BU；越权 403）
  - 跟随当前筛选 `blk` + scope；主表大项整行加粗 + 各 `构成_*` 明细 sheet（数据行不加粗）+ `导出说明`
  - 纯函数 `export_pl_xlsx.build_pl_xlsx_bytes` 复用 `pack_pl_by_period`，金额只写 `amt_disp`
- 顶栏 HTML 快照导出**不动**；snapshot 模式隐藏 Excel 按钮

### Unchanged（红线）
- 利润/费用/分摊算法、`src/profit/*`、前端金额运算均未改

---

## [2.3.5] - 2026-07-23

### Changed
- **产品名 UI（陆总）**：全站用户可见名统一为 **「甲骨易经营看板」** / **「经营看板」**（顶栏、登录、入场、页签 title、导出文件名、管理端标题等）；功能与口径不变

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
- `/api/v1/health` metrics 写真实 `update_ms` / `fetch_fail_rate`（去掉恒 null 的 `api_p95_ms`）

### Changed
- 主题按钮文案三态：◈ 霓虹 / ◐ 深色 / ◑ 浅色（仍含「深色」「浅色」字样供测试定位）
- 首次升级 `cockpit-theme-v2` 标记强制默认霓虹；之后尊重用户选择
- 管理端恒暗色，不读/不污染看端 localStorage 主题

---

## [2.2.9] - 2026-07-22

### Changed
- **导出主路径 = 方案 A 自包含静态可交互快照**：`/export.html`、`/api/v1/export.html`、`/bu/{name}/export.html` 下载单文件 HTML，内嵌 `kind=kanban_snapshot` 数据包 + Vue 播放器（`frontend/dist-snapshot`）；`file://` 可离线打开，可切周期、展开利润表、看期间费用等图；整体包含全部已发布 BU 可切换，BU 包仅本 BU
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
- `GET /api/v1/history/{day}/vm`：管理员读归档 VM
- `snapshot_vm` / `list_vm_archives` / `load_vm_archive`；`export_html` 模块（Playwright 抓 Vue 优先，失败降级壳）
- tests `test_task_2_2_7.py`

### Removed
- 历史列表对 `页面_*.html` 的依赖；旧 `GET /api/v1/history/{day}` HTML 回看 → **410**

---

## [2.2.6] - 2026-07-21

### Changed
- **下单未填部门批量 UX**：去掉顶栏「本页销售筛选」；筛选只在表头（销售/下单日期）；批量只处理**本页 × 表筛结果**；确认框明示「仅当前页」+ 筛选条件 + 笔数 + 金额合计 + 归入部门
- 换页时重置列筛选（避免旧筛挂在新页）

### Added
- `POST /api/v1/admin/adjust/batch`：预检全过再写、同一事务多条调整、**一次** `recompute`（策略 A）
- tests `test_task_2_2_6.py`

---

## [2.2.5] - 2026-07-21

### Changed
- **管理端长列表翻页**：配置变更/数据修正/费用未分类/下单未填部门/历史快照日表/异常总览/数据调整 统一上一页/下一页，每页 50；筛选或刷新归第 1 页；表单类视图不加分页
- **「看」→「展示」**：管理端顶栏页签及用户可见「看」措辞改为展示/显示；`group:'see'` 与产品名「经营罗盘」保留
- **`/api/v1/version`**：任意登录会话可读（展示端顶栏版本号）

### Added
- 展示页顶栏甲骨易 logo（`import` → `/app/assets/*.png`，兼容 nginx 只缓存 assets）+ 产品版本号（拉 `/api/v1/version`）
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
- **批次 B**：账号密码 PBKDF2 哈希存储；明文自动迁移备份；`/api/v1/admin/accounts` 不下发密码；`POST …/reset_passwd` 管理员重置；会话 TTL 12h（H-05）
- **批次 C**：前端金额字面量守卫改为显式白名单；去掉 `1e-4` 规避写法（M-01）

---

## [2.0.1] - 2026-07-20

本地 tag：`stage61_beta201`

### Changed
- 回款卡：删「尚待回款 / 年标签 / 回款占下单 / 黄回款率线」；文案改「本年下单 / 本年回款」；年目标进度条有则显
- 月度图 x 轴裁到当前系统月（尊重 `period_pin`）；删除费用月度趋势折线卡 ExpenseTrend
- 排名双卡：前 N 名标注、「其余」完整弹层；**按下单额降序**
- 管理端 / 看端列筛选；期间费用「按部门」master-detail
- 人工填写分摊对齐 `/api/v1/admin/alloc_rates` + `ratios`
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
