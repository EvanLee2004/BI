# CLAUDE.md — 看板正式程序（经营驾驶舱代码）

> 进这份代码干活前先读本文。**本文只记：架构 / 怎么跑 / 模块地图 / 铁律 / 当前状态 / 文档指针**。
> 运行·打包·部署细节看 `README.md`；进度看项目根的 `progress.md` / `工作日志.md`；需求口径看 `../../方案与文档/软件工程文档/1_需求/01_需求分析_陆总需求台账.md`（唯一权威源）。全套软工文档见 `../../方案与文档/软件工程文档/`（按需求/设计/测试/管理过程四类归档，README 是总索引）。

## 这是什么

给管理层看的**经营利润驾驶舱**：读数据源 → 算到税前利润 → 出自包含 HTML。5 用户内网/手机看，分级=不同人给不同链接（用户端只读、管理员端可改）。

## 架构（五层单向）

```
原始导出(智云4源+收单台账)
  └▶ 进料口文件夹(数据/)
       └▶ ingest 读→洗→规范化 ─▶ SQLite 数据库(数据/看板.db：标准表std_+人工表adj_/manual_/suspect_/meta_)
                                      └▶ profit 只读库算 summary ─▶ render 出双端HTML
```
- **数据库是后端私有资产**：前端(浏览器)只经 HTTP/API 跟后端(FastAPI)要数据，**从不直接碰库**。库=单文件 SQLite，无独立服务进程。
- **契约**：一切下游只吃 `看板.db`；换数据来源只动"进料口"（readers），下游不动。

## 怎么跑

```
python run.py            # 更新一次：建库→算→出 HTML/JSON（默认 data_dir=数据/）
python run.py --serve    # 起内网双端服务（用户端 / + 管理员端 /admin），端口见 config
python run.py --scheduled# 供 Windows 计划任务调用
sh tests/run_verify.sh   # 一键验证：语法+端到端+回归红线+全部测试
```
- 依赖装在项目 `.venv/`（fastapi/uvicorn/openpyxl，精确版本见 `requirements.txt`）；跑测试/服务用 `.venv/bin/python`。
- 管理员默认口令 `kanban2026`（可环境变量 `KANBAN_ADMIN_PW` 覆盖）；密钥存 `数据/管理员密钥.json`（不进 git）。
- 测试/正式数据切换只改 `config.json` 的 `data_dir`，代码不动。

## 模块地图（src/）

| 文件 | 职责 |
|---|---|
| `schema.py` | **全表 DDL + 字段常量唯一源**（建表/可调整字段/归属月字段都从这出）|
| `db.py` | 连接 + 读回层（返回与旧 loaders 同构结构，profit 零改动）+ 明细查询 + 写函数(调整/手填/可疑单)|
| `ingest/` | 更新管道：`readers`(读原始) `normalize`(规范化+行哈希) `fetch`(收单台账SMB抓取) `migrate`(手填Excel一次性迁移) `suspects`(diff分级+可疑单) `adjust`(调整重放+过期校验) `archive`(备份+月末快照) `__init__`(串起来的 pipeline) |
| `profit.py` | **只吃库**算 summary（纯函数，不再扫文件）|
| `render.py` | 用户端驾驶舱 HTML | `charts/theme/assets` 渲染件 | `export_book` 导出 |
| `server.py` | FastAPI 双端：用户端`/`只读、管理员端`/admin`密码会话、`/api/*` 编辑接口、控制台HTML(`_ADMIN_CONSOLE`) |
| `core.py` | generate/summary（run↔server 共用，破循环导入）|
| `loaders/columns/periods/validate` | 配置/按表头找列/周期/进门校验（被 ingest 复用的底层）|

## 铁律（违反就出错，必守）

1. **智云导出 xlsx 绝不 `read_only=True`**（`<dimension>` 不可信，老坑）；**列按表头找、不按位置**；**必需列缺失即报错，不静默算 0**。
2. **前端不做金额运算**（tests 守卫）；求和/口径都在 profit。
3. **回归红线**：改动后页面所有数字须与 `v6-final` 一分不差——动 loaders/计算前先跑/写 `tests/regress_db_vs_files.py`（从库算==从文件算）。
4. **每改必补测试 + 跑 `run_verify.sh` 全绿**（现有 test_cockpit/datalayer/adjust/server/admin_edit）。
5. **`数据/` 目录内容绝不进 git**（.gitignore 已挡 看板.db/备份/快照/csv/xlsx）；**代码/测试/日志不出现真实金额与客户名**。
6. **发布安全**：本地 `master` 设 `pushRemote=no_push`、永不推；发 GitHub 只走 `gh-clean` 流程（README 有）；**推公开仓库前肉眼核 manifest + 内网路径(ledger_share_path)脱敏成占位符**（真实路径只留部署机本地）。
7. **收单台账 fetch**：路径可达才拉、不可达走数据目录本地副本 + 体检黄，**不中断管道、不 mock**。

## 当前状态（2026-07-08）

- 分支 `refactor-datalayer`；**刀0–4（数据层+双端改造）已完成并自测通过**，建议打 tag **v7.0**（架构大版本）。回归红线一分不差、49 测试全绿。
- 数据是**测试造数**（真客户名+假金额，7×复制），非真实经营数——不能拿数字给陆总看。
- **下期 v7.1**：可见层打磨（KPI趋势/回款下单率/周期下拉/控制台体验/分级收口）——见 `../../方案与文档/需求与方案/20260708_下期迭代计划_可见层与分级收口.md`。
- **顺延（未做）**：部署上线、接真实数据、**智云四源自动抓数**（现全靠人工导出放文件夹，P4/二期大工程）。

## 关键文档指针

- 运行/打包/部署/发布流程 → 本目录 `README.md`、`docs/Windows部署手册.md`
- 需求口径(权威) → `../../方案与文档/软件工程文档/1_需求/01_需求分析_陆总需求台账.md`
- 架构/详细设计 → `../../方案与文档/软件工程文档/2_设计/`（02概要设计 / 03详细设计_数据层与双端改造 / 04设计变更_定位键策略）
- 测试/版本/迭代 → `软件工程文档/3_测试/05_测试说明`、`4_管理过程/CHANGELOG.md` + `06_迭代计划_v7.1`
- 进度快照/历史 → 项目根 `progress.md` / 甲骨易实习根 `工作日志.md`
