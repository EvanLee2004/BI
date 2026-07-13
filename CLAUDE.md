# CLAUDE.md — 看板正式程序（经营驾驶舱代码）

> 进这份代码干活前先读本文。**本文只记：架构 / 怎么跑 / 模块地图 / 铁律 / 当前状态 / 文档指针**。
> 运行·打包·部署细节看 `README.md`；进度看项目根的 `progress.md` / `工作日志.md`；需求口径看 `../../方案与文档/软件工程文档/1_需求/01_需求分析_陆总需求台账.md`（唯一权威源）。全套软工文档见 `../../方案与文档/软件工程文档/`（按需求/设计/测试/管理过程四类归档，README 是总索引）。

## 这是什么

给管理层看的**经营利润驾驶舱**：读数据源 → 算到税前利润 → 出自包含 HTML。5 用户内网/手机看，分级=账号分流（看板一个入口 `/`：权限「整体」看全部、权限=BU 名只看本 BU；管理员端 `/admin` 可改数；账号表 `数据/看板账号.json`）。

## 架构（五层单向 · 抓数层／清洗层分开）

```
① 抓数层(采集)  把各源数据搬进进料口：
                智云4源 = ■人工导出xlsx（自动抓=二期待建·未做）
                收单台账 = ◧ingest/fetch.py SMB抓（仅部署机；本机走本地副本）
                手填     = ●管理员表单页(已做)
   └▶ 〔进料口〕 数据/ 文件夹（6源文件+手填库）——抓数层↔清洗层的接缝
        └▶ ② 清洗层  ingest 读原始(readers)→规范化(normalize)→套用调整(adjust)
             └▶ ③ SQLite(数据/看板.db：标准表std_ + 人工表adj_/manual_/meta_)
                  └▶ ④ profit 只读库算 summary ─▶ ⑤ render 出双端HTML
```
- **现状边界（2026-07-10 更新）**：**①抓数层智云自动抓已打通**——下单/回款/项目明细三源可账号密码自动登录+在线抓+只抓当年(config.zhiyun_since)，S2对数已验可替代人工导出；接进 pipeline 但由 `config.zhiyun_auto_fetch`(默认false)控制。**内部译员源仍缺**(亮晶号权限不足、待陆总号)。②清洗~⑤展示已实现(v7.0)。
- **数据库是后端私有资产**：前端(浏览器)只经 HTTP/API 跟后端(FastAPI)要数据，**从不直接碰库**。库=单文件 SQLite，无独立服务进程。
- **契约（接缝=进料口）**：抓数层只负责把数据落进 `数据/`；一切下游只吃 `看板.db`。换数据源/换抓取方式（人工导出→自动抓）只动上游抓数层与 readers，进料口以下不动。

## 怎么跑

```
python run.py            # 更新一次：建库→算→出 HTML/JSON（默认 data_dir=数据/）
python run.py --serve    # 起内网双端服务（用户端 / + 管理员端 /admin），端口见 config
python run.py --scheduled# 供 Windows 计划任务调用
sh tests/run_verify.sh   # 一键验证：语法+端到端+回归红线+全部测试
```
- 部署机起服务用 `看门狗启动.bat`（循环跑 `--serve`，支持一键更新后按退出码 42 自动重启）；`启动看板服务.bat`=不带自动重启的普通版。
- 依赖装在项目 `.venv/`（fastapi/uvicorn/openpyxl，精确版本见 `requirements.txt`）；跑测试/服务用 `.venv/bin/python`。
- 账号口令在 `数据/看板账号.json`（明文、不进 git；缺文件自动 seed；管理员默认账号 `lushasha` / 口令 `kanban2026`）；会话签名密钥存 `数据/管理员密钥.json`（只 cookie_key）。
- 测试/正式数据切换只改 `config.json` 的 `data_dir`，代码不动。

## 模块地图（src/）

| 文件 | 职责 |
|---|---|
| `schema.py` | **全表 DDL + 字段常量唯一源**（建表/可调整字段/归属月字段都从这出）；含只追加的 `manual_配置变更`（C3 留痕）|
| `db.py` | 连接 + 读回层（返回与旧 loaders 同构结构，profit 零改动）+ 明细查询 + 写函数(调整/手填/预算) + `list_salespeople`/`order_stats_by_sales`(A1 归属池+参考) + `log_config_change`/`list_config_changes`(C3)|
| `ingest/` | 更新管道：`readers`(读原始) `normalize`(规范化+行哈希) `fetch`(收单台账SMB抓取) `login_zhiyun`(智云账号密码无头Chromium自动登录换md_pss_id·登录页无验证码·截获接口POST /wwwapi/Login/MDAccountLogin密码RSA) `fetch_zhiyun`(智云三源自动抓：翻页/解析/同名列合并去重/服务器端日期过滤只抓当年/token失效自动重登+回写配置·配置读 数据/智云配置.json 不进git) `migrate`(手填Excel一次性迁移) `adjust`(调整重放+过期校验) `archive`(备份+月末快照) `__init__`(串起来的 pipeline·zhiyun_auto_fetch=true时先在线抓) |
| `profit.py` | **只吃库**算 summary（纯函数，不再扫文件）；`filter_rows_by_sales`(BU 按销售过滤) + `compute_unassigned_orders_by_period`(A3 每周期未归属下单额) + `compute_profit_ranking`(板块③ 收入/毛利按客户·销售+集中度，确认口径)|
| `accounts.py` | **看板账号表**（v8.0·v8.6 多 BU）：`数据/看板账号.json` 读写/seed/鉴权/改密；权限∈{管理员,整体,BU,旧单BU名}；权限=BU 时 `可见BU` 列表；取用走 `bu_names_of`/`can_see_bu`；明文密码；最后登录 |
| `version.py` | **产品版本号 + 面向用户更新日志**（v8.4）：读根目录 `VERSION`（现 0.9）；`product_stage`(主版本<1=试运行/≥1=正式版)/`product_label`/`version_info`/`changelog`(副本)；产品号≠git 开发号 |
| `updater.py` | **一键更新 + 看门狗**（v8.7·v8.7.1 可选远端·v8.7.3 依赖同步+回滚）：`check_update`/`apply_update`(带 `remote` 参数，默认 `config.update_remote`→origin；护栏→`git pull --ff-only <remote>`→**依赖变了 `_run_pip` 装，装失败回滚不重启**→成功写回滚点 `.update_rollback`)/`request_restart`(码 `RESTART_EXIT_CODE=42`)/`{write,read,clear}_rollback_marker`；护栏=只 ff、脏/分叉/非仓库拒绝；配 `看门狗启动.bat`(码 42 重启·更新后启动即崩则据标记自动回滚一次)。部署从 Gitee clone 则 origin=Gitee 默认对标 Gitee |
| `bu.py` | BU 数据归属读写/校验（BU 名+负责人+销售名单；「整体」保留字；**一人一 BU**；无密码字段；真实配置只在 `数据/BU配置.json`）|
| `render.py` | 整体用户端与 BU 独立页 HTML（含自改密码弹窗）| `charts/theme/assets` 渲染件 |
| `server.py` | FastAPI 出口：`/`=看板统一入口（账号权限分流·`_main_with_nav` 注入 BU 入口条+A3 未归属提示）、`/bu/{BU名}`、管理员`/admin`、`/api/accounts` `/api/my_passwd` `/api/sales_pool`(A1) `/api/config_changes`(C3) `/api/daily`(板块④按天) `/api/profit_ranking`(板块③收入/毛利全量·dim=customer/sales·会话闸)、控制台HTML；C3 留痕 diff 与 `_audit` 在各配置写接口就地脱敏落库 |
| `core.py` | generate/summary（run↔server 共用，破循环导入）；`attach_unassigned`(A3 挂 summary.meta.unassigned) + `unassigned_snapshot`(管理端快照)|
| `loaders/columns/periods/validate` | 配置/按表头找列/周期/进门校验（被 ingest 复用的底层）|

## 铁律（违反就出错，必守）

1. **智云导出 xlsx 绝不 `read_only=True`**（`<dimension>` 不可信，老坑）；**列按表头找、不按位置**；**必需列缺失即报错，不静默算 0**。
2. **前端不做金额运算**（tests 守卫）；求和/口径都在 profit。
3. **回归红线**：改动后页面所有数字须与 `v6-final` 一分不差——动 loaders/计算前先跑/写 `tests/regress_db_vs_files.py`（从库算==从文件算）。
4. **每改必补测试 + 跑 `run_verify.sh` 全绿**（现有 test_cockpit/datalayer/adjust/server/admin_edit/fetch_zhiyun/budget/expense_views/bugfix_0711/auth/bu…）。
5. **`数据/` 目录内容绝不进 git**（.gitignore 已挡 看板.db/备份/快照/csv/xlsx/`*.json`）；**代码/测试/日志/样例不出现真实金额、客户名与真实人名**（账号样例用合成名）。
6. **发布安全**：分支已理成单主分支（2026-07-09）——**`main`=唯一主分支**（开发+推 GitHub 都在它上）；`archive-本机完整历史-禁推`=旧 master 改名的只读历史档案（**历史含真实数据**，pushRemote=no_push 永不推，tags v1.0~v7.0 挂在它上**绝不 push --tags**）；**推公开仓库前肉眼核 manifest：真实金额/客户名/账号密码/cookie 绝不进库**。⚠口径更新（2026-07-13 明昊拍板）：**智云内网 base_url + app_id + 四表 worksheetId、收单台账共享盘 UNC 路径（config.json `ledger_share_path` 出厂默认）允许进公开库**（部署开箱即抓、免拷模板/免手填），不再当违禁品；后期换路径走设置页覆盖层，别改 config.json。
7. **收单台账 fetch**：路径可达才拉、不可达走数据目录本地副本 + 体检黄，**不中断管道、不 mock**。
8. **智云全字段抓：同名控件必须合并去重**（`rows_to_records` 空值不覆盖有值）——智云可有多个同名控件（尤其 type30 他表字段），后出现的空值会把有值清掉。2026-07-10 踩坑：两个"整单交付日期"→抓下来全空→**看板收入归不到月**。改前端字段/日期口径时留意此坑。
9. **智云抓失败不中断**：登录失败/token失效/抓失败一律降级 `local_fallback`(体检黄)，永不抛异常中断管道；token 失效(HTTP200但state==0含"登录/退出")自动重登一次。
10. **台账/调整来的自由文本进 HTML 必转义**（2026-07-11 排查定）：正文与属性统一走 `render._esc` / `charts.esc`；`data-tip` 走 getAttribute+innerHTML 两层解码→名称须**双层转义**（`esc(_tip(...))`，`<br>` 是自己拼的富文本放行）；前端按 data-cat 找元素用 `CSS.escape`。新增渲染出口先想"这段文本是谁填的"。
11. **theme.py 同优先级选择器靠后的赢**：给某类元素开豁免（如排名卡不限高 `.rk-list{max-height:none}`）必须**提权重**（`.ev-list.rk-list`），否则会被后面的通用规则（`.ev-list{max-height:300px}`）静默覆盖——v7.4 排名加（未填）行到 12 行才现形（置底行被裁掉）。改主题通用规则时全局搜一遍豁免类。
12. **BU 页严格隔离**：BU 渲染只可吃该 BU 已过滤的 summary，禁止接入整体页动态出口（`/api/daily`、`/export.png` 等——它们只认整体/管理员会话）；未知 BU 名一律 404；看板明文密码只经管理员会话 `/api/accounts` 下发。新增 BU 字段或出口必须补“他 BU 名称/人员/客户不泄漏”测试。
13. **口令比较一律 bytes**：`hmac.compare_digest` 传 str 遇非 ASCII（用户输中文密码）直接抛 TypeError→接口 500——比较前先 `.encode()`（2026-07-11 v7.8 踩坑，test_auth 中文密码用例锁死）。
14. **账号与 BU 解耦（v8.0）+ 一账号可绑多 BU（v8.6）**：登录账号在 `看板账号.json`，BU 归属在 `BU配置.json`；权限字段绑「能看什么」，一 BU 可多账号、**一账号可绑一组 BU**（权限=BU + `可见BU` 列表；旧权限=单 BU 名兼容）。**判可见范围一律走 `accounts.bu_names_of`/`can_see_bu`，别再直接读 `权限` 当单个 BU 名**。多 BU 账号 BU 页顶部切换条只列其绑定 BU（`_bu_switcher_html`，铁律12 延伸：绝不列他 BU）。管理员端登录无身份下拉。自改密码弹窗必须提示「密码管理员可见，请勿使用你在其他地方用的密码」。
15. **销售名一把尺（v8.1·A1）**：归属界面「列出的销售名」与 BU 页「过滤用的销售名」必须走**同一个规范化**（`.strip()`；`db.list_salespeople` 的 `TRIM` == `profit.filter_rows_by_sales` 的 `str().strip()`）。别为界面另写一套清洗，否则会出现「界面显示已归属、过滤却没生效」的对不上数（测试 `test_pool_names_match_filter` 锁死：池里每个名直接喂 filter 必须过滤到）。
16. **配置留痕绝不落敏感值（v8.1·C3）**：`manual_配置变更` 只存人读摘要，密码类只记「账号X改密码」、智云账号只记「已更换」，绝不写密码/token 明文；`/api/config_changes` 仅管理员会话（含人名，BU/整体会话拿不到）。**未归属提示只在整体页/管理端出现，BU 页绝不渲染**（只走 `_main_with_nav`，铁律12 延伸）；提示金额随周期预渲染、前端零运算（铁律2）。
17. **`position:fixed` 弹窗/浮层必须挂 `<body>` 直下（v8.2.2 踩坑）**：任何 `transform`/`filter`/`perspective`/`will-change:transform` 的祖先都会成为 `position:fixed` 的**包含块**——浮层于是相对该祖先（可能整页高）定位，跑到页面中部而非视口居中。排名弹窗 `#rkModal` 曾落在 `#periodSync`（v8.2.1 切周期淡入淡出用 `will-change:transform`）内被困；修法=`document.body.appendChild(modal)` 移出。新增弹窗/抽屉/tooltip 一律 body 直下（pwModal/drawer/tip 本就在 wrap 外，安全）。**flex 纵向滚动配套**：滚动列表在 `flex-direction:column` 盒子里必须 `min-height:0`（+`flex:1 1 auto`），否则 `min-height:auto` 让它撑破盒子、首行溢出被表头裁掉（`.rkm-list` 踩过）。
18. **一键更新只认 fast-forward + 护栏 + 依赖同步 + 自动回滚（v8.7·v8.7.3 扩）**：`updater.apply_update` 只跑 `git pull --ff-only`（绝不合并/变基/产生冲突）；工作区脏、本地与远端分叉、非 git 仓库→一律拒绝并提示人工，绝不强拉覆盖。**拉取后依赖自动同步**：`requirements.txt` 变了就用当前解释器 `pip install`（`_run_pip`，装进同一 venv）；**装失败→`git reset --hard` 回滚这次拉取、返回 ok=False 不重启**（更新期自愈）。**成功则写回滚点标记 `.update_rollback`（更新前 commit，gitignore）**；重启靠看门狗——拉取成功后进程以退出码 `RESTART_EXIT_CODE=42` 退出，`看门狗启动.bat` 据码用新代码重拉起（42 两处必须一致）。**坏版本自愈**：看门狗遇非 42 崩溃时若 `.update_rollback` 仍在=更新后启动即崩→自动 `git reset --hard <标记commit>` 回滚一次再起（只一次，删标记后再崩走 5 次停下报警）；服务正常起 20s 后 `server.serve` 调 `clear_rollback_marker` 清标记=确认这版没崩。改更新逻辑别绕过护栏、别在无看门狗时指望自动重启，`.update_rollback` 写/清/回滚三处语义要对齐。

19. **程序绝不写 config.json + 机器专属设置走本地覆盖文件（v8.7.4·F-01 修复）**：`config.json`=出厂默认（git 追踪、只读）；**部署机专属/会在管理端改的设置（收单台账 `ledger_share_path`、`schedule_times`、`backup_keep_days`、`zhiyun_auto_fetch`、可选 `update_remote`）一律落 `数据/本地配置.json`（gitignore）**，`loaders.load_config` 读 config.json 后叠加覆盖（非 None 值胜出）。`save_settings` 只调 `loaders.write_local_config`、**绝不回写 config.json**。理由：config.json 一旦被改，部署机 `git status` 永久脏→一键更新的"工作区脏就拒绝"护栏恒生效→按钮变摆设（F-01）。新增写设置的接口/字段：想持久化就走覆盖文件，别碰 config.json；`test_config_json_never_dirtied_by_settings` 锁死。

## 当前状态（2026-07-14）

- **v8.7.6 首次部署引导页修 F-02 + requirements 补 python-multipart（2026-07-14·部署日实战两坑）**：① `/admin` 完整页只在首次取数成功后生成，而设置页长在里面→空机器"数据尚未生成"鸡生蛋卡死；修复=`admin_html` 为空时管理员登录出**自包含引导页** `_BOOTSTRAP_HTML`（填智云账号→保存→触发 `/api/refresh`→轮询→成功自动进完整管理端；未登录仍登录页）。② `requirements.txt` 补 `python-multipart==0.0.32`（部署机实测 FastAPI Form 缺它启动崩；**一键更新依赖自动安装靠此文件，漏=每台新机必踩**）。⚠部署机绝不改源码（工作区脏=一键更新废）——当天绕行=手工写 `数据\智云配置.json`+`更新看板.bat` 首跑；修复经 push 由部署机一键更新接收。另记：cmd GBK 打不出 `⚠`→直跑 `python run.py` 崩，必须经带 `chcp 65001` 的 .bat。`test_admin_edit` +1（bootstrap 三态），**312→313 全绿+回归红线 32 不变**。

- **v8.7.5 智云连接配置内置默认（2026-07-13·明昊拍板·消灭部署初始文件包）**：`fetch_zhiyun.ZHIYUN_DEFAULTS`（内网 base_url/app_id/四表 worksheetId + inhouse min_rows:1000）随代码进公开库；`_load_zhiyun_cfg`=默认←`数据/智云配置.json` 合并（文件非空值胜出、tables 逐源合并、文件缺失也可用）；`_save_session` 缺文件也创建（token 持久化）；设置页「智云账号」卡新增折叠区改服务器/四表ID（`save_zhiyun_conn`：同默认=删覆盖、异默认=写覆盖、换服务器清会话；`/api/settings` GET 加 `zhiyun_conn`；C3 只记「已更改」）。**账号/密码/cookie 仍绝不进库**（铁律6 口径同步更新）。**同日追加：收单台账真实共享盘路径也进 config.json 当出厂默认**（明昊拍板"懒得折腾"，`\\192.168.10.151\财务部\lara.zhao\收单台账.xlsx`，2026-07-08 部署机实测直读可用；换路径走设置页覆盖层）。**部署机 clone 完只需设置页填智云账号密码这一样**。测试 **308→312 全绿+回归红线 32 不变**（TestZhiyunDefaults 3 例+conn 设置 1 例+2 例改语义）。
- **v8.7.4 配置分离修 F-01：一键更新在部署机可用 + 台账路径进设置页（2026-07-13·明昊拍板）**：**上线前最终排查发现的高危问题 F-01**——部署机改 `config.json` 的 `ledger_share_path`→git 工作区永久脏→一键更新护栏恒拒→整套一键更新在真实部署机开箱即废。修法=**配置分离**：① 新增 `数据/本地配置.json`（gitignore）机器本地覆盖层，`loaders.load_config` 读 config.json 后叠加它（+`local_config_path`/`read_local_config`/`write_local_config`）；② `save_settings` 全部改写覆盖层、**绝不再写 config.json**（更新时间/备份/自动抓也一并改到覆盖层）；③ **收单台账路径挪进管理端「设置→智云账号·台账路径」界面填**（`sLedgerPath`，落覆盖层，C3 只记"已更改"不落含内网名的值）。部署机 config.json 永不被程序动→git 干净→一键更新可用。删死代码 `_config_file`。铁律19 固化。`test_schedule` +2（含 F-01 守卫 `test_config_json_never_dirtied_by_settings`）、`test_admin_edit`/`test_auth` 断言改覆盖层，**306→308 全绿+回归红线 32 不变**。部署手册/checklist/首次部署 doc/config.json note 全改成"设置页填、别碰 config.json"。CHANGELOG v8.7.4。
- **v8.7.3 一键更新补齐：依赖自动安装 + 坏版本自动回滚（2026-07-13·对标标准更新流程）**：补上更新机制原缺的两块。① **依赖自动安装**：`apply_update` 拉取后若 `requirements.txt` 变了→用当前解释器 `_run_pip` 装进同一 venv（`_requirements_changed` 比对更新前后决定装不装）；**装失败→`git reset --hard` 回滚这次拉取、返回 ok=False 不重启**（防新包缺失重启崩溃，更新期自愈）。② **坏版本自动回滚**：成功时写回滚点 `.update_rollback`(更新前 commit·gitignore)；`server.serve` 起服务 20s 后清标记=确认没崩；`看门狗启动.bat` 遇非 42 崩溃时若标记仍在=更新后启动即崩→自动回滚一次再起（`setlocal enabledelayedexpansion`+读标记 `git reset --hard`），删标记后再崩才落到既有"5 次停下报警"。`test_update.py` +4（依赖装/装失败回滚/无变化跳过/标记读写），**302→306 全绿+回归红线 32 不变**。⚠ .bat 逻辑开发机不实测（Python 侧桩测覆盖），部署机验一次（部署手册复验清单已加）。铁律18 已扩。
- **v8.7.2 产品升「公测 Beta」+ code review 修 #1（2026-07-13·周一上线版）**：① **产品版本 0.9 试运行 → `1.0-beta` 公测 Beta**（`VERSION` 文件；`version.py` 加 beta 阶段识别：带 `-beta` 预发布标记→"公测 Beta"，label 去后缀显主号 `v1.0（公测 Beta）`；纯展示、不参与一键更新比对；管理端 pill/版本卡/verNext 文案同步）。产品阶段链：0.9 试运行→1.0-beta 公测 Beta→去 -beta 升 1.0 正式版。② **code review 修 #1**：[`periods.ledger_row_date`](src/periods.py) 收单月份退回分支加**月份范围校验**（"13"/"0"/越界→返 None，被体检按 date_bad 判黄），此前造出 `(year,13,1)` 无效日期被 `date_in_range` 静默剔除却不报警——违背"坏值不静默消失"原则；**红线中性**（这些行本就不计入任何周期，数字不变），只多一条诚实告警。`test_expense_views.py` +4（`TestLedgerRowDateMonthGuard`）、`test_version.py` 改断言，**298→302 全绿+回归红线 32 不变**。code review 其余发现（#2 adjust `now[:4]` 耦合／#3 台账定位键撞键已被 len>1 防御／#4 硬编码手填键／#5 nit）均非可复现 bug、记台账不改码。
- **v8.7.1 一键更新可对标 Gitee + 部署质量抬档（goal 块1~3·纯发布卫生/文档，无口径改动）**：`updater.check_update`/`apply_update` 加 `remote` 参数（默认 `config.update_remote`→origin；部署机从 Gitee clone 则 origin=Gitee 零配置对标 Gitee），返回 `remote`=远端名、`remote_rev`=远端短哈希（原 `remote` 字段改名，前端 `d.remote_rev` 同步）。`test_update.py` +1（`test_custom_remote_gitee`），**297→298 全绿+回归红线 32 不变**。commit `5797e0d` 推 GitHub。**独立只读 bug 排查+离线 `--serve` 活体探针**：护栏/鉴权隔离/多BU切换/XSS 优先区无真 bug（探针实证 BU 账号只看本 BU、全公司出口与管理端全 401、`/api/update/check` 有远端返回合理），记 `11_bug台账` 第二轮（1 处非可利用潜在脆弱点 N-01·不改码）。`docs/Windows部署手册.md` 对齐 v8.7 + 新增 `docs/周一部署checklist.md`（两件必验=看门狗+一键更新 pull 重启，commit `a79463d`）。**Gitee 双推已配好（2026-07-13）**：本机 `gitee` remote（`https://gitee.com/Lee157/oracleeasy--bi.git`）与 `origin`(GitHub) 均已配置且与本地 HEAD 同步；推送鉴权用明昊生成的 Gitee 个人访问令牌，存在本机 **macOS Keychain**（`git credential-osxkeychain`，非明文文件/非 git 仓库），`git push` 到两端均已可用、无需再手动输密码。
- **v8.7 一键更新按钮 + 安全看门狗（明昊·下一批④·本批收官）**：管理端加**一键更新**（检测代码仓库新版本→安全快进拉取→看门狗自动重启，**部署侧 `看门狗启动.bat` 才完全激活**）。`src/updater.py`：`check_update`（git fetch+比对 HEAD 与 origin/分支）、`apply_update`（护栏复检→`git pull --ff-only`）、`request_restart`（后台延时以退出码 `RESTART_EXIT_CODE=42` 退出）。**护栏**：只认 fast-forward、工作区脏/分叉/非仓库→拒绝、git 命令带超时不交互挂起。接口 `GET /api/update/check`、`POST /api/update/apply`（仅管理员，apply 成功才重启+C3 留痕「更新」）。`看门狗启动.bat` 循环跑 serve、码 42=更新重启、非 42 连续 5 次停下报警。管理端设置版本卡加「检查更新」。新增 `test_update.py` 11 例（真实临时 git 仓库测五态+接口），**286→297 全绿+回归红线不变**；⚠真正 pull+重启开发机不实测（部署机验，见部署手册）。**下一批 4 件（①②③④）收官。**
- **v8.6 账号可绑定多个 BU（明昊·下一批③）**：登录账号可见范围「单个 BU/整体」→**可绑一组 BU**（整体=全部；也能给某几个 BU 子集）。权限模型（accounts.py）新增类型 `BU`（`PERM_BU`）+ 字段 `可见BU`（列表）；统一走 `bu_names_of`（管理员/整体→[]、BU→列表、旧单名→[该名]）+ `can_see_bu`；**旧账号权限=单个 BU 名完全兼容**；`public_row` 下发 `可见BU`。看板路由：`/` 多 BU 账号落第一个绑定 BU + 顶部「我的 BU」切换条（`_bu_switcher_html` **只列绑定且仍存在的 BU、绝不列他 BU**·铁律12·单个不出条），`/bu/{name}` 同；BU 账号 `_can_view_main` 仍 False。管理端账号「权限」列→类型下拉（管理员/整体/按 BU）+ BU 复选框组（`acctSetType`/`acctToggleBu`，旧单名编辑自动固化为 BU 平滑迁移）。新增 `test_multibu.py` 12 例，**274→286 全绿+回归红线不变**。
- **v8.5 多次更新时间（明昊·下一批②）**：自动更新从"每天一个固定时间"→**可增删多个时间点**（09:30/12:00/17:30，各到点各跑一次）。配置新增 `schedule_times`（列表·canonical），旧 `schedule_time`=列表首个镜像（兼容 .bat/读单值）；`server.normalize_schedule_times`/`get_schedule_times` 校验+推导（缺列表从旧单值、坏值兜底 09:30、`MAX_SCHEDULE_TIMES=6`）。**Windows 计划任务=多任务**：首个=主名 `经营驾驶舱每日更新`（**铁律不变**）+ 其余 `_2.._n`；`_win_sync_schedule` 保存 best-effort 同步（Change/Create/删多余，**try/except 永不打断保存**，失败提示重跑 .bat）；`注册每日更新.bat` 升级读 `schedule_times` 循环注册全部。管理端设置「自动更新」卡→多时间点编辑器；`/api/settings` GET/POST 走 `schedule_times`（兼容旧单值）。`run.py --scheduled` 不变、计算/渲染/数据层零改动。新增 `test_schedule.py` 15 例，**259→274 全绿+回归红线不变**。
- **v8.4 产品版本号 + 管理端更新日志页（明昊·下一批①）**：给经营罗盘加**产品版本号**（面向管理层，**≠ git 开发号 v8.x**）+ 管理端「版本与更新日志」页，为一键更新（④）打地基。新建根目录 `VERSION` 文件（纯文本一行，现 `0.9`）+ `src/version.py`（`read_version`/`product_stage`/`product_label`/`version_info`/`changelog`）：**主版本 <1=试运行、≥1=正式版**（正式上线才把 VERSION 改 1.0）；产品号与 git tag 两套并行、git tag 不给用户看。管理端顶栏版本 pill（`v0.9 · 试运行`，点击跳设置版本卡）+ 设置页 `full` 宽「版本与更新日志」卡（大号版本号+阶段徽章+大白话日志倒序，从 CHANGELOG 人工提炼）；接口 `GET /api/version`（**仅管理员会话**，`changelog()` 返副本防常量被改）。**计算/渲染/数据层零改动**（回归红线不变）。新增 `test_version.py` 9 例纳入 run_verify，**250→259 全绿+回归红线 32 周期一分不差**。（本批②多次更新时间/③账号多 BU/④一键更新按顺序做，都不依赖陆总口径。）
- **v8.3.6/v8.3.7（明昊）**：v8.3.6 异常处理改名（`调整台账`→「数据修正」/`操作记录`→「配置变更记录」/`经手人`→「操作账号」，纯 UI 文案、底层不动）；v8.3.7 板块③「毛利率」→「项目毛利率」防误读（`_margin_meta`+弹窗 `_mg`，`.pr-grid .rk-meta` 84→104px）。均 **250 全绿+回归红线不变**。
- **v8.3.5 产品改名「甲骨易智能经营罗盘」（明昊）**：显示名「经营驾驶舱」→「甲骨易智能经营罗盘」（顶栏「罗盘」accent）。改所有显示位（整体/BU 顶栏+页脚+浏览器 title + 登录页/控制台 title + FastAPI title + 导出 PNG 名）；**内部标识保持不动**——`SCHTASK_NAME="经营驾驶舱每日更新"`（须与 `注册每日更新.bat` 一致）、`output_html/output_json` 文件名默认值、docstring 不改（改了会连累已注册的计划任务/部署脚本）。`test_structure` 加名字守卫，250 全绿+回归红线不变。
- **v8.3.4 logo 放大 + 回款/预算两卡等高对称（明昊）**：① `.tb-logo` 26→40px；② 回款+预算网格加 `.rb-grid`（`.grid-2e`+`align-items:stretch`）拉两卡等高，矮卡内容纵向居中不留底空白（回款图外包 `.rc-body` flex 居中、预算 `.bud-list` flex 居中，卡头恒顶）；空预算时回款仍整宽（rb-grid 不生效、rc-body 无副作用）。测试 `TestReceiptsBudgetLayout` GRID 常量随类名更新，**250 全绿+回归红线 32 周期一分不差**。
- **v8.3.3 板块③ 集中度放大突出 + 计算逻辑公式条 + 小字统一放大（明昊）**：① 卡头「前5大占收入 X%」拆成 `.tag`「确认口径」+ `.conc`（百分数 17px·accent 青·800 粗；`_conc_tag` 返回结构化 span，`_profit_rank_card` 卡头不再外包 `.tag`）；② `#profitRankViews` 后新增静态 `.pr-formula` 描边条，标三条口径公式（收入=交付额÷1.06·毛利率=毛利÷收入·集中度=前5大收入÷期内总收入）；③ 板块③小字统一放大 **scoped 到 `.pr-grid`**（名次/名称/金额13px、毛利率/口径/点开12~12.5px、固定列宽随字号加宽），**不影响板块④**，移动端 `@media` 同步给 `.pr-grid` 收窄列宽防溢出。测试 `test_profit_ranking` 集中度断言改结构化 + `test_cockpit` +1（`test_profit_formula_strip`），**249→250 全绿+回归红线 32 周期一分不差**（纯 CSS/结构、数字未变）。
- **v8.3.2 回款情况+部门费用预算执行 改左右两列并排缩小（明昊）**：`render_dashboard` 里两卡从上下整宽堆叠→**同一个 `.grid-2e` 两列并排**（回款左·预算右各半宽，复用板块③的 grid-2e：1fr 1fr·手机端自动单列）；回款图 SVG 响应式随半宽等比缩小、预算横条自适应，图表本身不改。**空预算兜底**：预算卡管理员填了才渲染，没填→回款独占整宽（`period-receipts` 整宽包裹）不留半吊空列；`render_dept_budget` 去掉自带 `margin-top:16px`（改由 grid 容器统一间距）。**只动 `/` 主渲染**=用户端整体页 + 管理端「看」（iframe 内嵌同一 `/`）天然一起改，BU 页无此两卡不涉及。测试 `test_cockpit.py` 16→18（`TestReceiptsBudgetLayout`），**247→249 全绿+回归红线 32 周期一分不差**（纯布局、数字未变）。
- **v8.3.1 板块③「其余」可展开 + 名称悬浮显全名（明昊实测）**：① 两卡「其余 N 个」→ `.pr-more`「点开看明细 ›」→ 新接口 **`GET /api/profit_ranking`**（`dim=customer|sales`·确认口径全量·`_can_view_main` 会话闸·纯只读·显示串后端下发铁律2）→ 复用 `#rkModal`（`PROFIT_JS`；已在 body、复用关闭）；② `.ev-name` 加 `data-tip`（`#tip` 即时浮层·双层转义铁律10）+ title 兜底，弹窗行同带（`render._pname`）。测试 `test_profit_ranking.py` 10→16，**241→247 全绿+回归红线不变**；实测客户展开全349家/销售29人/名称悬浮出全名/无报错。
- **v8.3 新增板块③「收入与毛利结构」**：用户端加 **收入·按客户 / 收入·按销售** 两卡（`.grid-2e` 对称两列/手机单列），确认口径按整单交付日期归属、每行 收入+毛利率、卡头集中度「前5大占收入%」、长尾「其余N个」合计、未填置底；原「下单与回款排名」顺延为板块④。数据层 `profit.compute_profit_ranking`（收入=交付额÷1.06、毛利=收入−项目成本=**项目直接毛利**未含内部译员/手填→与利润表总毛利有差异；守恒 items+others+unfilled==total+集中度），`build_period` 每周期多算 `profit_rankings`；render `render_profit_rankings`（随 `.pv`/周期切、前端零运算、口径写 footer、不带弹窗）。新增 `test_profit_ranking.py` 10 例，**231→241 全绿+回归红线 32 周期一分不差**。
- **v8.2.2 管理端删自改密码 + 排名弹窗修复（明昊实测）**：① 管理员会话看整体页/BU 页隐藏「🔑密码」自改入口（`_HIDE_PW_STYLE` 注入；管理员改密走 /admin 设置页，看的人仍保留自改；总账号 lushasha 永久不可删未动）；② 排名「完整排名」弹窗第 1 名被表头盖住——`.rkm-list` 补 `flex:1 1 auto;min-height:0` + 弹窗 `appendChild` 到 body 直下脱离 `#periodSync` 的 will-change 祖先（见铁律17）。测试 227→231（`test_auth` +4 `TestHidePwForAdmin`）全绿+回归红线。
- **v8.2.1 UI 收口（迭代17 后实测）**：用户端 `#periodSync` 切周期统一淡入淡出 + 利润表 stretch 同高 + wrap≈1680；管理端 sec 铺满视口、iframe 加高、设置智云|账号并排、「＋加 BU」在分摊上、分摊**无总开关·全空=不分摊**（`bu.save_bu_config` 推导启用）。不碰回归红线数字。
- **v8.2 板块③按天时段常显跟顶 + 公共费用分摊（迭代 17·A 改口 + A2）已完成**：**批次A** 顶部「看哪段」不动；板块③日期区默认展开（无 dailyBtn）、起止默认跟顶（初始全年）、查询才 `/api/daily`、**返回默认（年）** 回全年预渲染；BU 页仍禁 daily（铁律12）。**批次B** `BU配置.json` 增加 `公共费用分摊启用` + 每 BU `分摊比例`；全空=关、齐填合计100%=开；台账 5 类×比例守恒；C3 类别「分摊」。测试 **223→227** 全绿+回归红线 32 周期。
- **v8.1 销售归属自助 + 未归属提示 + 配置留痕已完成（迭代 16·A1+A3+C3）**：**A1** 管理端「BU 数据归属（销售归属）」卡升级——每个销售芯片带当年下单笔数+金额参考串（`/api/sales_pool` 服务端算好，铁律2），支持**勾选多人→选 BU→批量指定**（`buPicked`/`buApplyBatch`，与拖拽并存），保存即重算；销售名扫描与过滤共用同一 `.strip()` 规范化（`db.list_salespeople`/`profit.filter_rows_by_sales`，界面列出=过滤生效，测试守卫）。**A3** 未归属显式提示——整体页 BU 入口条下一行小字「另有未归属 BU 的业务 ¥X（N 名销售待配置归属）」，X 随周期预渲染成 pv 块前端只切显示（`core.attach_unassigned`→`summary.meta.unassigned.by_period`，含销售空行=精确差额），N=0 或未配 BU 时不渲染；管理端归属卡顶同款提示 + 顶栏体检未归属>0 判黄带短原因（`api_health` 合入 `meta.unassigned.count`）；**BU 页绝不出现**（只在 `_main_with_nav`，测试守卫）。**C3** 配置变更留痕——新表 `manual_配置变更`（只追加、永不清空、不存密码明文），覆盖全部管理端配置写接口（销售归属/BU/账号/设置/自改密码），管理端「异常处理→操作记录」页倒序看+类别筛（`/api/config_changes` 仅管理员）。测试 **209→223**（新增 `test_iter16.py` 14 例）全绿+回归红线 32 周期一分不差；8024 实测：批量指定→保存重算→整体页金额随周期变→移回还原→操作记录出现对应条目。
- **v8.0 账号权限重构 + 管理端优化已完成（迭代 15）**：统一 `数据/看板账号.json`（明文；缺文件 seed；样例合成名）；`/` 登录按权限分流（管理员→/admin、整体→整体页带 BU 条、BU→本 BU；一 BU 多账号）；`/admin` 账号+密码（lushasha）；看的人右上自改密码；设置页「账号与权限」卡（明文👁/最后登录/初始黄标/就近保存）+ BU 卡瘦身数据归属 + 栅格重排/无全局保存/体检黄带短原因/更新完成 toast。测试 **207** 全绿+回归红线 32 周期。
- **v7.9 看板账号制（已被 v8.0 取代）**：看的人一个入口 `/`、账号=「整体」或 BU 名、密码集中管理（看的人不能自改）。测试 196。
- **v7.7 按 BU 分页先行批次已完成**：探查结局②=项目明细/内部译员/回款源头均有「销售」列，清洗层补进 `std_收入明细/std_回款/std_内部译员`（下单原已具备）；BU 配置=`数据/BU配置.json`（缺失即功能关闭，真名/token 不进 git），`/bu/{token}`独立只读页仅渲染该销售名单的完整利润表与下单/回款排名，公共费用/手填项明确待补不伪装成零；管理员「设置」可增改名单、换 token、保存即重算。测试 **182** 全绿+回归红线 32 周期不变；待周一细则=分摊比例/映射定稿/BU 手填填法。
- **v7.6 排名全量明细弹窗 + 按时间段看精简**（明昊二轮实测反馈）：排名卡「其余 N 个」可点→弹窗全量排名（预渲染卡带 data-start/end=P[key]['range']，点击调 /api/daily?top=2000，top 服务端钳 1~2000）；「按时间段看」去掉逐日表，只剩日期+一行合计+三卡切换（看一天=同日起止，起始日联动）。管理员端「看」=内嵌用户页，两端天然一致（8020 旧版本是别的会话的服务）。测试 165。
- **v7.5 按天明细（迭代计划13批次B）已完成**：用户端板块③「按时间段看」入口（v7.5.1 交互重做：**单套排名卡模式切换**——默认跟全局周期，查询后同位置换成区间卡并标注区间，逐日表点行=只看那天，三条还原路径；缘由=明昊实测指出两套卡并存口径混乱+无返回）→ `GET /api/daily`（公开**纯只读**·入参严格校验·任意区间≤366天）实时算逐日下单/回款+排名；显示串后端下发（*_disp，原始数值与total不下发）=铁律2零运算；这是**第一个非预渲染数据口**。九点RPA对数：当日总额一分不差、部门系两套口径（RPA=组织架构三分类 vs 看板=智云部门字段），**替代拍板与RPA退休待陆总/明昊定**，对数记录见 `3_测试/06_对数记录_九点RPA_vs_看板按天明细_20260711.md`。测试 164 全绿。
- **v7.4 异常处理中心（迭代计划13批次A）已完成**：管理端「复核」改名「异常处理」+新「总览」计数卡片页（EXC_CARDS 可扩注册制·R4冲突卡留位）+新「下单未填部门」页签（行内选部门→写调整，源头后补自动变过期疑似=闭环）+「未填分类」改名「费用未分类（台账）」；用户端排名（未填）单拆置底灰显⚠（`compute_ranking` 返回 `unfilled`，total 守恒）；新接口 `/api/exceptions`、`/api/order_depts`（均需会话）；口径常量 `db.UNFILLED_DEPT_WHERE` 清单与排名共用。测试 155 全绿+回归红线。（批次A收口时批次B尚未开工，同日已完成，见上条。）
- 分支 **`main`=唯一主分支**（2026-07-09 由 gh-clean 改名+设 GitHub 默认分支；旧 master→`archive-本机完整历史-禁推`，含真实数据历史+tags v1.0~v7.0，**永不推、绝不 push --tags**）。
- **v7.2 已完成并推 GitHub**（`77d4042`+hidden修复`25f5b39`）：年度预算手填（全公司下单/回款→回款图预算线+完成率）+ 费用构成三态视角（按大类|按部门|按利润中心，横条+抽屉，守恒锁死=分组合计==台账白名单合计）+ 部门费用预算执行卡（<80%青/≤100%橙/超支红置顶）+ 清洗层补`预算归属部门`软列（老台账缺列降级）。测试 94 全绿。
- **二期抓数 S1b/S1c 已打通（2026-07-10）**：`login_zhiyun`(账号密码无头登录)+`fetch_zhiyun`(在线抓三源·只抓当年·同名列去重·token自动重登)+接进 pipeline(config.zhiyun_auto_fetch 默认false)。**S2对数已验**：三源行级0漏抓、逐字段仅新鲜度差(用"最近修改时间"证明)、可替代人工导出。测试 22（原16+新6：同名去重/日期过滤/token失效判定/登录守卫）。**内部译员源仍缺**(亮晶号权限、待陆总号)。**部署机需 `playwright install chromium`**（待写进部署手册）。
- **⚠数据现状=混合态（跑过在线抓后变化）**：收单台账=真实(2026·仅本机)；**智云下单/回款/项目明细=真实2026数据(已被在线抓覆盖·仅本机)**；智云内部译员=旧测试数据(local_fallback)；手填+15部门年预算=测试/假数据。**页面数字混合、不能直接当真给陆总看**；要恢复纯测试数据从 `原始素材/测试数据套装/` 拷回。
- **立即更新已异步化 + 设置页（2026-07-10）**：`/api/refresh` 改后台线程立即返回、`/api/refresh_status` 轮询进度（前端按钮显示耗时/在线抓提示/打开页面自动跟进）；管理端「设置」顶层页三卡片=每日自动更新时间（win32 保存即 `schtasks /Change` 计划任务 `经营驾驶舱每日更新`）+ 备份清理（config 新键 `backup_keep_days` 缺省30，`archive.backup_db` 读它滚动清 `数据/备份/`；月末快照不清；/api/settings 返回 backup_stats）+ 数据来源只读标注表。设置保存=改运行中 cfg+重写 config.json。端口可用环境变量 `KANBAN_PORT` 覆盖（本机多会话调试用，config 默认 8018 不变）。
- **抓数=必选常开（2026-07-10 明昊拍板）**：更新固定两路抓数（共享盘台账+智云四源），无界面开关；`zhiyun_auto_fetch` 默认 **true**（config 留作应急后门）；`fetch_all` 先 5 秒连通性探测、不可达整体快速降级；**`KANBAN_OFFLINE=1` 强制跳过在线抓**（run_verify.sh 默认导出——测试/回归不碰网络不动进料口）。**内部译员已接**：智云配置 inhouse=「任务」表 `654da962f9460e517040a9f0` + `min_rows:1000` 行数门槛（账号行级权限不足抓到异常少行→降级不覆盖现有文件；换全量权限账号自然全绿）。测试 112。
- **设置页可管理智云账号（2026-07-10）**：「🔑智云账号」卡=账号/密码密文显示+👁切换+可改；保存**改了才写** `数据/智云配置.json` 并清旧会话（md_pss_id/account_id 置空→下次更新强制重登）；`login_zhiyun.login` 返回 `(token, account_id)`——account_id 从页面全局 `md.global.Account.accountId` 自动取（实测可得），**换账号只填账号密码、GUID 零配置**；`_save_session` 把两者一起回写。部署流程=装程序→界面填账号密码→保存→立即更新。测试 113。
- **日历月区间 + 排名板块③（2026-07-10）**：周期选择器=日历面板（全年/季度快捷段+12月网格，点两月=自选区间）；`periods` 生成全部连续月区间合成周期、整页预渲染 pv 块前端只切显示（铁律2；月份索引一元加号避 parseInt 守卫）；`parse_date_parts` 带缓存。板块③=下单按部门/销售、回款按客户排名（`profit.compute_ranking`，前10+其余）；**std_下单加 部门/销售、std_回款加 客户**（DDL+ALTER+normalize+读回+明细列）。回归红线覆盖 32 周期。测试 116。⚠HTML 1.66MB/首建约55s，年底约3MB/2min，嫌大再做懒加载。
- **历史快照（2026-07-10）**：每次更新存当日页面 `数据/备份/页面_YYYYMMDD.html`（同天覆盖=留当天最后一次，`backup_keep_days` 默认365天滚动；月末那份另存快照存档永久=年末档天然覆盖）；管理端复核→「历史快照」**年→月→日级联**回看（/api/history）。测试 118。**口径备忘：快照=数据版本维度、时间区间=业务期间维度，不重复；按天任意日期区间已拍板挂起**（费用/手填按月切不出按天利润，等真实场景再按"只显示按天算得准的"方案做）。已 push GitHub main `0a55145`（2026-07-10）。
- **费用构成横条加"构成›"提示（2026-07-10）**：按部门/按利润中心每条点开抽屉看细类本就有（v7.2），补可点提示。排名负数金额统一全角"−"。**计算逻辑复查（2026-07-10）：无算错数字 bug**；设计点非bug清单见 progress 顶部（未分类不计入/附加税简化口径/（未填）=源头质量/导出无区间/区间无环比）。
- **⚠上线前待办（非阻塞但要做）**：① Playwright 在 --serve 进程内(线程池)跑登录**尚未端到端实测**，开 flag 上线前需验一次；② 账号密码+token 明文存 `数据/智云配置.json`(gitignore·仅部署机·既定设计)。
- **R0+R1 已完成（2026-07-10）**：R0 **可疑单整套删除**（suspect_待确认表/suspects.py/diff分级/接口/控制台页签/相关测试；存量库连接时自动 DROP 清表；页面数字一分不变）；R1 **调整全字段可调=黑名单制**（`schema.ADJUSTABLE_FIELDS` 从各 std 表 DDL 自动推导"全部列−黑名单"，黑名单=`NON_ADJUSTABLE`：id/定位键/归属月/原值_*/已删除；管理员端字段下拉改由 `/api/adjust_fields` 服务端下发；改日期连带重算归属月、重放/过期校验机制不变）。测试 96 全绿+回归红线。
- **v7.3.1 bug修复批次（2026-07-11）**：第二双眼睛独立排查确认 1P1+4P2 全修（台账：`4_管理过程/11_bug排查与修复台账_20260711.md`）——①渲染层 HTML 转义全覆盖（铁律10 由此定）；②附加税措辞四处统一"增值税×12%"（代码数值本就对=net×6%×12%，⏳待陆总口头确认口径）；③调整定位键失配单列 `missing` 计数→判黄+管理端原因提示（剔除不再悄悄复活）；④`parse_date_parts` 全分支 `_valid_ymd` 月日合理性校验；⑤`/export.png` 加 `_EXPORT_LOCK` 互斥连发429。**测试 132**（新增 test_bugfix_0711.py 11例）+回归红线 32 周期。本地 commit `a8d51f3`（未push）。
- **v7.3.2 过期疑似批量处理（2026-07-11）**：调整台账页=「只看过期疑似」筛选+**一键听源头新值**（批量撤销，前端确认条两步：点按钮→确认保存）+**坚持我的数**（逐条 rearm：原值刷成源头现值→重新生效→立即重算）。不对称设计有意：批量只给"听源头"方向，批量坚持会废掉报警。接口 `/api/adjust/expired/revoke_all`、`/api/adjust/{id}/rearm`（均要会话）。测试 136（admin_edit 24→28）。**R2~R4 暂缓**（2026-07-11 复核后建议、明昊未再推进：现有每日备份+过期疑似/missing 报警够用，等真实运维痛点触发再启，计划存 `4_管理过程/迭代计划/12_R2R4改造施工与测试计划_20260711.md`）。
- **下一步 = R2~R4**（`4_管理过程/迭代计划/10_迭代计划_数据库分层改造R系列.md`）：R2 raw_批次层 / R3 std改读批次+final_视图 / R4 冲突待确认清单+audit确认表+操作记录页——与二期抓数连做。四层架构合同与冲突策略（智云冲突→陆总确认、台账冲突→自动听新Excel、默认用系统值）以 10 号计划为准。

## 关键文档指针

- 运行/打包/部署/发布流程 → 本目录 `README.md`、`docs/Windows部署手册.md`
- 需求口径(权威) → `../../方案与文档/软件工程文档/1_需求/01_需求分析_陆总需求台账.md`
- 架构/详细设计 → `../../方案与文档/软件工程文档/2_设计/`（02概要设计 / 03详细设计_数据层与双端改造 / 04设计变更_定位键策略）
- 测试/版本/迭代 → `软件工程文档/3_测试/05_测试说明`、`4_管理过程/CHANGELOG.md` + `4_管理过程/迭代计划/16_迭代计划_BU分页.md`
- 进度快照/历史 → 项目根 `progress.md` / 甲骨易实习根 `工作日志.md`
