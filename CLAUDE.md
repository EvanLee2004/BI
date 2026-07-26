# CLAUDE.md — 看板正式程序（经营驾驶舱代码）

> 进这份代码干活前先读本文。**本文只记：架构 / 怎么跑 / 模块地图 / 铁律 / 当前终态 / 文档指针**。
> 运行·打包·部署细节看 `README.md`；进度看项目根 `progress.md` / `工作日志.md`；需求口径看 `../../方案与文档/软件工程文档/1_需求/`。
> **重写前全文存档**：`docs/历史批次/CLAUDE_重写前存档_20260719.md`（永久可回查）。

## 这是什么

给管理层看的**经营利润驾驶舱**：读数据源 → 算到税前利润 → 看端 Vue SPA + 管理端 Vue SPA。5 用户内网/手机；账号分流（`/` 看板：整体/BU；`/admin` 管理端改数）。

## 架构（五层单向 · 终态）

```
① 抓数  智云四源自动抓 + 台账 SMB + 管理端表单
   └▶ 〔进料口〕 数据/
        └▶ ② 清洗  src/ingest/
             └▶ ③ SQLite 看板.db（金额 INTEGER 分）
                  └▶ ④ domain + profit → summary / viewmodels
                       └▶ ⑤ 展示
                            · 看端 frontend/（Vue3+ECharts+SciFi）→ dist 由 nginx 或 /app
                            · 管理端 frontend/src/admin/（Element Plus · 深空主题）
                            · 后端 FastAPI：src/server.py 装配 + src/routes/* 分模块
```

| 层 | 终态落点 |
|----|----------|
| 领域/展示串 | `src/domain/`（expense/pl/ledger/rankings/…）· `src/viewmodels/` |
| 算账 | `src/profit/`（子包；口径禁区） |
| 库访问 | `src/db/`（detail/loaders_std/…）+ `db_write.py` / `schema.py` |
| HTTP | `src/routes/{auth,cockpit,data_api,manual,export,admin_pages,config_*}.py` |
| 渲染碎片 | `src/render_*.py`（expense/pl/receipts/assemble/widgets） |
| 前端 | `frontend/src/components/*` · `frontend/src/admin/views/*` |

- **契约**：换抓取方式只动上游与 readers；进料口以下不动。
- **浏览器只经 HTTP**；库是后端私有资产。

## 当前状态（2.6.7 · 2026-07-27）

- **版本**：`VERSION` = **2.6.7**（验收回修 + 顶栏统一 + 存量清零）。其上：2.6.6 体检黄条；2.6.5 三层统一；2.6.0 `kanban_sid`；2.5.0 `/login`。
- **会话**：`src/session_ctx.py` 唯一 resolve；权限只看账号表；退出清 sid+两旧名；MADR-0023。
- **看端顶栏（2.6.7）**：唯一横排 主题｜导出｜密码｜退出；无 ⋯；管理员无密码/退出；退出 DataModal 确认；红条下线、黄条保留。
- **看端首包**：`vue-runtime` 分片 + echarts 异步；板块五懒加载；deps **无** element-plus；**首屏 gz ≤90.8KB**。
- **工程**：`KANBAN_OFFLINE=1 sh tests/run_verify.sh` 判绿（**禁管道吞退出码**）；`KANBAN_PROFILE=dev|staging|prod` 已实现。
- **部署**：Ubuntu 唯一主线；nginx 发 dist + 反代；运维 `docs/Runbook.md` §0。
- **红线**：核心数字零未授权 diff；32 周期回归；**前端零金额运算**；只推 main 不推 tags。

### 前端三层铁律（2.6.5+ · 守卫 `tests/test_frontend_arch_guards.py`）

1. **Layer 1** `frontend/src/styles/tokens.css`：颜色/间距/圆角/字号/动效/阴影/z-index；三主题各一套；**硬编码色值只许出现在 tokens.css 与 admin/styles/admin.css**（F-2；扫 `components/**` `admin/**` `views/**`，vendor 除外）。
2. **Layer 2** `frontend/src/components/base/`：`RankBar` / `RankList` / `DataModal` 等只认 props，样式只用 token。
3. **Layer 3** `frontend/src/components/*.vue`：**禁止 `<style>` 块**（F-1）；只做取数 + 组装 Layer 2。
4. **动效时长** 必须 `var(--dur-*)`（F-3）；禁止 `transition: .3s` 字面量。
5. **RankBar 副数值列** 无 `metaLabel` 不许渲染（F-4）；收入榜系统成本率列头小字 + 悬浮解释「项目成本 ÷ 交付收入」。
6. **排名弹层** 逻辑只收敛在 `RankList`（按需 fetch / 加载中 / 失败）；禁止业务组件各自读 `full_items` 无兜底。
7. **`/api/profit_ranking`**：未登录 401；已登录无权限 403；有 `bu` 须能看该 BU 且只返回本 BU 销售过滤行。
8. **切 BU 过场**：1s、文案「正在计算 XX BU 数据……」、可跳过、reduced-motion；过场中 KPI 不 count-up 连播。
9. **「整体」导航按钮**：仅 `can_main`/管理员可见。
10. **ECharts** 只留给真正图表（趋势/费用/热力）；排名条用 CSS RankBar。
11. **顶栏（2.6.7）**：禁止 `tb-actions-narrow` / `tb-more-*`；退出须 DataModal 确认。

### 历史铁律（2.6.3 起仍生效）


1. **私密文件必原子写**（同目录 tmp → chmod 0o600 → `os.replace`）；账号表坏 JSON **隔离不 seed**。
2. **`db_path` 只写相对 data_dir**（如 `看板.db`）；首段等于 data_dir 末段 → 抛错，不静默纠正。
3. **本地配置禁止覆盖** `data_dir` / `db_path` / `profiles`；坏文件 → 黄+告警，不许 `except: pass`。
4. **新鲜度只认业务时间戳**（`built_at` / 运行日志），禁止用 `看板.db` mtime。
5. **定时刷新**：过点且今日未成功 → 补跑；busy 排队不丢；漏跑黄+告警。
6. **跨年归档**：`.partial` 全成功再 rename + `_ARCHIVE_OK`；半截不当 exists。
7. **缺当年台账 sheet**：空集+红+横幅「收单台账缺 &lt;年&gt; 页，找亮晶建」，管道继续。
8. **管理端写库与刷新互斥**；忙 → **409**「更新进行中，请稍后再保存」，绝不 500 半条脏写。
9. **看端首包禁止依赖 element-plus**；Vue/echarts 分片或异步。
10. **登录锁定按账号+IP**；新密码下限 8 位（明文存储口径不变·MADR-0020）。

### 历史版本索引（一行一版 · 细节见 CHANGELOG）

| 版本/tag | 要点 | 指针 |
|----------|------|------|
| 2.0.1 / stage61_beta201 | 回款卡整改·BU目标·三类人工分摊·筛选·分摊fix | `docs/20260720_任务书61交付报告.md` |
| rc13 / stage60_prod_fix | 进程内定时刷新+cookie互清·**曾上生产** | 工作区 `…/20260720_任务书60交付报告.md`（不进产品仓） |
| rc12 / stage58_ui | 费用明细日期统一+本月·首次上生产 | （施工归档） |
| rc11 / stage57_gold | 无限打磨收官 | `docs/20260719_任务书57交付报告.md` |
| rc10 / stage56_final | 清尾 R-40~R-46 | `docs/20260719_任务书56交付报告.md` |
| rc9 / stage55_final | 55 终局封板 | `docs/历史批次/` · CHANGELOG |
| rc8 / stage55_rc8 | 费用图剔成本+热力 | 54.15 |
| rc7 / stage55_rc7 | 工程拆分收官 | 54.13 |
| rc6 / stage55_rc6 | 人审二轮+工资全隐 | 54.12 |
| rc5 / stage55_rc5 | 主题·弹层·热力 | 54.14 |
| rc1~rc2 | 封板交接 / 人审一轮 | 54.10~54.11 |
| stage54p* | Vue 重构·美学·文档 | `docs/CHANGELOG_stage54系列补记.md` |

完整条目：`docs/CHANGELOG_stage54系列补记.md`。

## 怎么跑

```
python run.py            # 更新一次：建库→算→出 HTML/JSON
python run.py --serve    # 内网双端（用户 / + 管理 /admin）；进程内 ScheduleLoop 按 schedule_times 刷新
python run.py --scheduled# CLI 离线批跑（不写 serve 内存；生产勿靠 cron 当页面更新）
sh tests/run_verify.sh; echo EXIT:$?   # 一键验证（禁 | tail 判绿）
```

- 部署：`docs/Ubuntu部署手册.md` · `docs/上线交接包/`
- 依赖：`.venv/` + `requirements.txt`；开发工具见 `requirements-dev`（若有）/ bandit/vulture 等
- 账号：`数据/看板账号.json`（不进 git）；会话密钥 `数据/管理员密钥.json`

## 模块地图（src/ · 拆分后）

| 路径 | 职责 |
|------|------|
| `schema.py` / `money.py` | DDL·SCHEMA_VERSION·元↔分 |
| `db/` + `db_write.py` | 连接/读回/明细 query_detail/手填预算写 |
| `ingest/` | fetch→normalize→重建→adjust→运行日志 |
| `profit/` | **只吃库**算 summary（口径禁区） |
| `domain/` | 展示用领域：费用白名单、PL 结构、排名… |
| `viewmodels/` | 看端 VM 打包（显示串） |
| `routes/` | FastAPI 路由注册壳 + 业务 handler |
| `server.py` | `create_app` 装配中间件/静态/异常页 |
| `authz.py` / `accounts.py` / `bu.py` | 鉴权·账号·BU 归属 |
| `render_*.py` / `charts.py` | 服务端 HTML/SVG 碎片（兼容与导出） |
| `settings_io.py` / `audit_diff.py` | 设置落盘·配置 diff/横幅 |
| `updater.py` / `version.py` | 一键更新·产品版本 |

前端：`frontend/src/components/`（看端）· `frontend/src/admin/`（管理端）· 构建产物 `frontend/dist/`。

## 完美主义（2026-07-18 明昊拍板）

生产封板 = PERF 全量 DoD；禁止「差不多先上 / 以后再说」打折。批次可排序，标准不可私下砍。见根工作区 `CLAUDE.md` #11。

## 铁律（违反就出错，必守）

1. **智云导出 xlsx 绝不 `read_only=True`**；**列按表头找**；**必需列缺失即报错**。
2. **前端不做金额运算**；求和/口径都在 profit/domain。
2-extra. **主题＝三值枚举** `neon|dark|light`；`theme-light` class 为兼容层不许删（light 仍加）。
2-extra2. **count-up 终值必须直赋 `value_disp`**；中间帧只用后端 `value` 插值，禁止从 disp 反解。
2b. **看端费用明细列走白名单** `VIEW_EXPENSE_COLUMNS`；管理端数据调整仍全列。
2c. **平台=Linux 单线**；禁 `.bat`/schtasks/win32；看门狗 `deploy/linux/start_with_rollback.sh`（退出码 42）。
2d. **业务层零裸 SQL**（只许 `db*`/`schema`）；守卫 `test_task43_arch`。
2e. **飞书 webhook 告警功能已删除（2026-07-25）**：无配置项、无 HTTP 外发、无设置页入口。`notify.py` 仅写本机 logging。**严禁**用公司大群 /「财经新闻」机器人 / 每日新闻通道做任何测试或告警（本仓及工作区其它项目一律禁止）。
2f. **共享盘只读**（fetch copy2 本地，绝不回写）。
3. **回归红线**：`tests/regress_db_vs_files.py` 从库算==从文件算，32 周期。
4. **每改必补测试 + `run_verify.sh` 全绿**。
5. **`数据/` 不进 git**；代码/测试无真实金额/客户名/真人名。
6. **发布安全**：只推 `main`；**绝不 push --tags**；公开库禁密码/token/真实客户金额（智云 base_url/app_id/表ID/台账 UNC 出厂默认允许）。
7. **台账 fetch** 已配置 share 可达才拉，否则 local_fallback→**体检红**（本次未抓到）；未配置 share 且有本地→fetched（不红）。不中断管道。
8. **智云同名控件合并去重**（空不盖有）；同名只 info、不黄不红（2.2.8）。
9. **智云抓失败不中断**（local_fallback→方案 B **红**）；行数对账容差 max(5,0.5%)；`zhiyun_auto_fetch` 关不因智云红。
10. **自由文本进 HTML 必转义**（双层 data-tip）；Vue 禁 `v-html` 自由文本。
11. **CSS 同优先级靠后赢**——豁免须提权重。
12. **BU 页严格隔离**；他 BU 数据/名称不泄漏。
13. **口令比较一律 bytes**（`hmac.compare_digest`）。
14. **账号与 BU 解耦**；可见范围走 `bu_names_of`/`can_see_bu`。
15. **销售名一把尺**（strip 与过滤同源）。
16. **配置留痕不落敏感值**。
17. **`position:fixed` 弹窗挂 body**；Vue 用 `Teleport to="body"` + mask fixed。
18. **一键更新 ff-only + 依赖同步 + `.update_rollback` 自愈**。
19. **程序绝不写 `config.json`**；机器设置走 `数据/本地配置.json`。
20. **验证只认真实退出码**，禁 `| tail`/`| head` 管道判绿。
21. **std 重建单事务**（BEGIN IMMEDIATE → 一次 COMMIT）。
22. **金额库内整数分**；显示层才 fmt。

### 54~57 新增铁律

23. **disp 单位约定**：后端下发 `*_disp` 已是「万」展示串时，前端**禁止**再拼「万」（`withWanUnit` / ExpenseSection 守卫）。
24. **弹层 z-index token**：周期/排名/遮罩统一走 CSS token，禁止魔法数字压盖顶栏。
25. **图表白名单单一来源**：费用折线与热力只调 `domain.expense.chart_whitelist`；禁止 area/heat 各写一份。
26. **任务前置自检**：托管任务书要求 `git tag` 含指定基线 tag；不满足只写停止说明、不施工。
27. **C901 豁免仅限纯分发壳**：`routes/*/register` 与 `create_app`；业务函数须拆到 ≤10。
28. **看端明细默认期间费用口径（R-45）**：`/api/v1/vm/ledger` 默认 `show_all=0` 叠加白名单大类；开「显示全部」才出成本/非利润表；导出随视图。

## 关键文档指针

| 用途 | 路径 |
|------|------|
| 断点续跑 | `docs/57_总控勾选.md` |
| 任务书 57 | `docs/20260719_任务书57_无限打磨_托管总单.md` |
| 交付/CHANGELOG | `docs/20260719_任务书56交付报告.md` · `docs/CHANGELOG_stage54系列补记.md` |
| 交接包 | `docs/上线交接包/` |
| 用户手册 | `docs/用户手册/` |
| 部署 | `docs/Ubuntu部署手册.md` · `docs/Runbook.md` |
| MADR | `docs/madr/` |
| 验收证据 | `docs/验收证据/` |
| 旧 CLAUDE 全文 | `docs/历史批次/CLAUDE_重写前存档_20260719.md` |

## 任务书65 铁律补充

- **删除必须有全仓零引用证据**（grep 结果进交付报告；存疑不删）。
- **文档「现状/已删/已建」必须与代码一致**（验收可抽查）。
- 管理端唯一路径=Vue；渲染整页 HTML 仅按需服务导出/历史快照。

## 改动前自检（2.6.4 · 抄自失效模式清单开工 10 问）

每个代码改动批次开工前**逐条在脑子里答一遍**（写进 commit/任务书更好）：

1. 需求口径谁定？ 2. 数据够不够/覆盖率？ 3. 影响既有口径吗？ 4. 回归红线还绿吗？
5. 手机端？ 6. BU 隔离？ 7. 失败谁会知道（告警.log/管理端）？ 8. 非交互卡死？
9. 谁验收？ 10. 是不是拍板结果（先 grep CHANGELOG/MADR）？

详见 `docs/新功能开发检查单.md` 与 `AI开发规范/失效模式清单/失效模式清单_开工必读.md`。
