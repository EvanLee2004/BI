# 甲骨易经营看板（智能经营罗盘）

**给财务与管理层用的经营利润驾驶舱** —— 每天自动汇总业务数据，算出税前利润，公司内网电脑和手机都能看。

| 当前版本 | 技术栈 | 生产形态 |
|:---:|:---|:---|
| **v3.7.7**（以根目录 [`VERSION`](./VERSION) 为准 · 2026-08-02） | Python · SQLite · FastAPI · Vue 3 · ECharts | 公司 Ubuntu · nginx · systemd · 候选预热发版 · 定时刷新 |

> 版本历史见 [`CHANGELOG.md`](./CHANGELOG.md)。业务数据与账号密码**不进本仓库**。  
> **现网 / 产品现状 SSOT**：项目根 `progress.md` 顶部 + 本仓 `VERSION` + `git rev-parse HEAD`（勿把下文历史号当真理）。  
> **现网终态（3.7.x）**：看数 **Domain→VM→Vue**；首屏六段；重点客户独立章（双饼 / 三池 / 可取消筛选）；导出走 **kanban_snapshot** + 利润表 Excel（「其他 N 项」可展开 children）；**无** `render_*` 驾驶舱双轨。API 均 **`/api/v1/*`**；会话仅 **`kanban_sid`**。飞书 webhook **已废止**。  
> **3.7.7～3.7.0 要点（摘要）**：桌面 Logo 放大 + theme cache-bust；导出展开「其他 N 项」；凭据不下发；调度只报真问题；抓数短退避 + 48h 新鲜度；HelpPopover；候选端口预热发版（3.7.3）+ 强制备份门闸（3.7.0）；下线「下单未填部门」。  
> **3.6.x 沉淀**：首屏六段与 KC 双饼；CSRF/:8001 Host；金额轴诚实。更早见 CHANGELOG。  
> **LICENSE**：公开仓尚未选型 → 待负责人拍板（勿擅自添加）。

**运维入口速查** → [下方「生产运维」](#生产运维) · 详方 [docs/Runbook.md](docs/Runbook.md)

---

## 一分钟看懂它是做什么的

语言服务公司日常要盯：**下了多少单、交付了多少、毛利怎样、费用花在哪、回款到账了没有、税前还剩多少**。

以前这些数散在智云系统、收单台账 Excel、手填表里，对一遍很慢。  
这个系统把它们接到一起，按统一规则算完，做成一页驾驶舱：

- **管理层**看全公司，也能进各业务线（BU）
- **业务线负责人**只看自己线的数，看不到别人的
- **财务管理员**在后台改明细、填人力/分摊、对异常、一键更新程序

金额全部在服务端算好；浏览器只负责展示和切换年/季/月。  
页面上的数字是**管理确认口径**（比完整财务记账更前置），方便日常经营讨论，不是替代总账/报税。

---

## 界面长什么样

下面截图来自本仓库 **`_golden_data` 脱敏演示数据**，本机 `KANBAN_PROFILE=dev KANBAN_OFFLINE=1` 跑通后的真实页面（合成客户名「示例客户*」/「员工*」，**非生产客户数据**）。

### 登录

![登录页](docs/images/ui/01_login.png)

同一套入口：输入账号后，系统按权限进入「整体 / 某业务线 / 管理端」。

### 三套主题

| 主题 | 定位 | 截图 |
|------|------|------|
| **霓虹**（默认） | 演示 / 投屏 | 见下「看端首页」 |
| **深空** | 日常办公 | ![深空](docs/images/ui/02_viewer_home_dark.png) |
| **晨光** | 白天 / 打印 | ![晨光](docs/images/ui/02_viewer_home_light.png) |

顶栏主题钮循环：**霓虹 → 深空 → 晨光 → 霓虹**（文案含「深色」「浅色」字样以兼容自动化定位）。发布后 theme 带 `?v=` + 产品版本（3.7.7）。

### 看端 · 基本情况与经营利润

![看端首页（霓虹·默认）](docs/images/ui/02_viewer_home_neon.png)

> **截图状态（2026-08-03 · v3.7.7 全量）**：`docs/images/ui/*`、用户手册截图、工程拓扑 PNG 均已按 **3.7.7** 重采/重渲（golden 脱敏，**无真实客户**）。

顶栏：年份/周期、**数据更新至**、版本角标、主题、导出、改密、退出。桌面 Logo 约 42px。五张 KPI：下单、交付金额（「含税」+ 副行「不含税 · ÷1.06」）、毛利率、税前利润、回款。

**首屏六段（整体=BU 同序 · 自 3.6.1 定型、现网 3.7.7 仍用）**：

| 序号 | 区块 | 要点 |
|------|------|------|
| 一 | **基本情况** | 五张 KPI |
| 二 | **下单与回款** | 日查（含「昨天」）→ 双榜 → 柱图 |
| 三 | **重点客户下单情况追踪** | 六档、双饼、三池、连续月折线（自然年） |
| 四 | **经营利润** | 趋势 + 管理利润表 |
| 五 | **收入与毛利结构** | 按客户 / 销售排名 |
| 六 | **费用明细** | 热力 + 台账表 |

![重点客户 · 多客金额对比折线](docs/images/ui/05_key_customers_compare.png)

上图为点名单「对比」后的作战台（golden 合成客户）：左池 S/A/B 名单；右为 **对比 N 客** 标签 + **金额对比** 折线（1～12 月下单预估，多色叠线）。未点对比时右侧为需跟进/临界晋级行动队列。

![重点客户 · 默认作战台](docs/images/ui/05_key_customers.png)

默认态：双饼 + 名单 + 行动队列（同上脱敏数据）。

![看端利润区](docs/images/ui/03_viewer_profit_section.png)

左：收入 / 成本 / 毛利率趋势；右：管理利润表（「查看构成」；导出 Excel「其他 N 项」展开 children · 3.7.6）。

### 看端 · 结构与费用

![看端结构区](docs/images/ui/04_viewer_structure_section.png)

![费用明细](docs/images/ui/12_viewer_expense_section.png)

### 手机

![看端手机](docs/images/ui/06_viewer_mobile.png)

内网手机竖屏可扫 KPI；390 宽已适配。复杂操作建议电脑。

### 管理端 · 控制台与设置

![管理端控制台](docs/images/ui/07_admin_console.png)

管理员进入 `/admin`：嵌看驾驶舱、「更新数据」、体检灯（绿=该抓的都抓到；红=有源本次未抓到；黄=抓齐仍有业务提醒，如手填缺月）。未到点定时槽只算「待执行」，不误报漏跑（3.7.5）。

![管理端设置](docs/images/ui/08_admin_settings.png)

账号、智云连接、备份与版本更新等集中在设置页。**智云密码 / 账号密码接口永不回显明文**；留空=不改已存值；重置须手输新密码（3.7.5）。

### 管理端 · 日常维护

| 场景 | 截图 |
|------|------|
| 异常总览 · 费用未分类等 | ![异常总览](docs/images/ui/09_admin_order_dept.png)（3.7.2 起「下单未填部门」已下线；文件名历史保留） |
| 人工填写 · 人力/分摊/去税 | ![人工填写](docs/images/ui/10_admin_manual.png) |
| 数据调整 · 明细改数 | ![数据调整](docs/images/ui/11_admin_detail.png) |

更细的操作步骤见 [用户手册](docs/用户手册/)。

---

## 谁用、能做什么

| 角色 | 怎么进 | 能做什么 |
|------|--------|----------|
| 管理层（整体） | 登录 · 权限「整体」 | 全公司 KPI、利润表、结构、排名；进入各 BU；顶栏导出 **HTML 快照**；利润表可导出 **Excel** |
| 业务线负责人 | 登录 · 权限「BU」+ 可见名单 | 只看绑定的业务线（可多个，顶栏「我的 BU」切换；**无「← 整体」**）；本 BU 快照 / 利润表 Excel |
| 财务管理员 | `/admin` | 改明细、手填与分摊（含公共费用两轴）、预算、异常处理、**用户统计**、销售归属、账号、检查更新 / 一键更新 |

> 全员只发两个根链接即可（见 [生产运维 · 访问入口](#1-访问入口只发这两个)），用各自账号登录；系统按权限自动进整体或业务线。

---

## 数从哪来

| 数据源 | 主要提供什么 | 怎么进系统 |
|--------|--------------|------------|
| 项目明细（智云） | 交付收入、系统直接成本 | 自动登录抓取 |
| 内部译员（智云） | 从成本中减出的内部人力 | 自动抓取（有行数护栏） |
| 下单（智云） | 下单额、部门 / 销售排名 | 自动抓取 |
| 回款记录（智云） | 到账额、客户相关排名 | 自动抓取 |
| 收单台账（Excel） | 营销 / 管理 / 固定运营 / 研发 / 财务等期间费用 | 共享盘；已配置但不可达时用本机副本并标红（本次未抓到） |
| 手填与调整 | 人力等成本补充、公共费用分摊比例、去税率等 | 管理端表单；**当月没填按 0** |

仓库里**没有**真实经营表；部署时把文件放进 `数据/`（说明见 [数据/README.md](数据/README.md)）。字段级说明见 [docs/数据来源说明.md](docs/数据来源说明.md)。

---

## 利润怎么算（摘要）

税率与费用分类以 `config.json` 为准。管理利润表主干可以记成：

```text
收入（不含税）  = 交付额 ÷ 1.06          （按整单交付日期归月）
生产成本        = 系统直接成本 − 内部译员 + 手填 − 直接成本增值税（默认 0）
毛利            = 收入 − 生产成本
期间费用（五类）= 手填人力 + 台账费用（营销 / 管理 / 固定运营 / 研发 / 财务）
附加税费        = 增值税 × 12%            （增值税 ≈ 不含税收入 × 6%，管理估算）
税前利润        = 毛利 − 期间费用 − 附加税费 + 其他损益
```

日常还需要知道：

- **改明细**写的是可重放的调整指令，不会改坏源头文件；重抓后会自动套上  
- **公共费用**可按月比例分到各 BU（合计可以不到 100%，剩下的留在公司层）  
- **费用去税**按类别手填税率；不填 = 不去税  
- 结构板块里的「项目直接毛利」未含内部译员 / 手填，所以分项加总可能与利润表总毛利略有差别——这是展示口径不同，不是算错  
- 每轮更新有数据体检（绿=抓齐无提醒 / 黄=抓齐有业务提醒 / 红=有源本次未抓到或硬故障）

对不上 Excel 时，先对齐时间段和是否同一口径，再查手填是否保存。常见问答：[docs/用户手册/FAQ.md](docs/用户手册/FAQ.md)。

---

## 快速开始（本机）

```bash
# GitHub
git clone https://github.com/EvanLee2004/BI.git && cd BI
# 国内镜像（Gitee）
# git clone https://gitee.com/Lee157/oracleeasy--bi.git && cd oracleeasy--bi

python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium   # 智云自动登录；兼容路由 /export.png 截图（看端主路径导出走 HTML 快照，无需 Playwright）

# 将 6 个数据文件放入 数据/（仓库不带业务数据，见 数据/README.md）
python run.py             # 抓数 / 建库 / 算账 一次
python run.py --serve     # 起服务，默认 http://127.0.0.1:8018
```

| 项 | 说明 |
|----|------|
| 端口 | 环境变量 `KANBAN_PORT` 可改 |
| 离线预览 | `KANBAN_OFFLINE=1 python run.py --serve`（不依赖外网抓数时） |
| 默认账号（仅初次种子） | 管理员 `lushasha` / `kanban2026`；查看类账号初始密码见种子逻辑，**上线务必改掉** |
| 账号文件 | `数据/看板账号.json`（不进 git；缺失时会自动生成种子） |
| 智云账号 | 管理端 → 设置 中配置 |
| 全量自检 | **必须用项目 `.venv`** + `KANBAN_OFFLINE=1 sh tests/run_verify.sh`（脚本会先 `materialize_offline_fixtures` 物化脱敏进料；判绿看真实退出码，勿 `| tail`） |
| 本地冒烟 | `KANBAN_OFFLINE=1 sh scripts/smoke_cockpit_local.sh`（结构守卫；若 :8028 已起服则 login→主题钮 探活。**非** CI Playwright 全路径） |

### 开发时前后端分开

| 模式 | 做法 |
|------|------|
| 后端 API | `python run.py --serve` |
| 前端热更新 | 另开终端：`cd frontend && npm run dev`（Vite 把 `/api` 代理到 8018） |
| 生产 | 只发构建好的 `frontend/dist`，由 nginx 托管，**不在生产装 Node** |

---

## 系统怎么串起来

生产链路可以记成：

**浏览器 / 手机 → nginx(:80) → Vue 静态页 + API → 算账引擎 → SQLite**  
数据进来：智云 / 共享盘台账 / 管理端手填 → 清洗与调整重放 → 入库 → 预计算好各周期数字 → 看端用接口取「已经算好的结果」。

### 0. 一图读懂（Mermaid）

```mermaid
flowchart LR
  subgraph sources [数据源]
    ZY[智云四源]
    LD[收单台账 Excel]
    MF[管理端手填/调整]
  end
  subgraph app [看板正式程序]
    IN[抓取与清洗]
    DB[(SQLite 分整数)]
    ENG[算账引擎]
    API[FastAPI]
    VU[Vue 看端/管理端]
  end
  subgraph edge [入口]
    NGX[nginx :80]
  end
  ZY --> IN
  LD --> IN
  MF --> DB
  IN --> DB
  DB --> ENG
  ENG --> API
  API --> VU
  NGX --> VU
  NGX --> API
```

- **BU 利润表**：每个业务线一张「缩小版公司表」——只汇总该线销售名下的收入/成本/费用（经销售→BU 映射）。  
- **口径一句话**：**当期生产交付即确认收入**（按整单交付日期归月），方便经营讨论，不是总账/报税口径。  
- **三源**：智云在线抓 + 台账共享盘 + 管理端手填；金额只在服务端算，浏览器只展示 `value_disp`。

### 1. 逻辑架构

![系统架构](docs/images/architecture.png)

### 2. 部署拓扑（公司机）

![部署拓扑](docs/images/deploy.png)

- 进程：`systemd` 服务 `kanban`（`Restart=on-failure` + StartLimit；开机自启）  
- 入口：首选 **`http://dash.besteasy.com:8001`**（须带端口）；nginx 托管 `frontend/dist` 并反代 API；**根路径 `/` 必须反代后端**（见运维节）  
- 应用主进程默认 **`127.0.0.1:8018`**；发版可用 **`:8019` 候选预热** 再切主（3.7.3）  
- 定时：进程内 ScheduleLoop 日更 + cron 体检 / 备份  

装机步骤：[docs/Ubuntu部署手册.md](docs/Ubuntu部署手册.md) · **日常运维见下方 [生产运维](#生产运维)** · 排障处方：[docs/Runbook.md](docs/Runbook.md)

### 3. 模块关系

![模块组件](docs/images/modules.png)

### 4. 登录与权限

![登录分流](docs/images/auth.png)

### 5. 每天怎么跑（白话）

![运行逻辑](docs/images/howto-run.png)

### 6. 关键时序与数据模型

![关键时序](docs/images/sequence.png)

![数据库 ER](docs/images/er.png)

库内存金额用「分」整数，避免浮点误差；账号与 BU 配置在 JSON 文件里，不在业务库表中。图注与文件清单见 [docs/images/FIGURES.md](docs/images/FIGURES.md)。矢量源在 [docs/设计图/](docs/设计图/)。

---

## 目录导读

```text
run.py                 更新管道 / 启动服务
config.json            税率、文件名、刷新时刻等出厂默认（机器差异写 数据/本地配置.json）
VERSION                当前产品版本号（管理端展示读这里）
CHANGELOG.md           变更记录
frontend/              Vue 源码与构建产物 dist/
src/                   抓数、库、算账、HTTP 路由、一键更新等
static/                登录页、主题、导出用 HTML 模板等
数据/                  本机业务数据与账号（gitignore，不进仓库）
tests/                 回归与契约测试
docs/                  使用手册、部署、API、设计图、界面截图
deploy/linux/          nginx / systemd 模板
```

一键更新（管理端「检查更新」）：对配置的 git 远端 `fetch`，落后时 `git pull --ff-only`，依赖变化会装包，再由看门狗重启服务。工作区被改脏会拒绝更新，以免覆盖人工改动。  
**注意**：若本次变更含 `deploy/linux/nginx-kanban.conf`，一键更新**不会**自动改系统 nginx——须运维手动同步 conf 并 `reload`（见下节）。

---

## 生产运维

> 本节 = 生产机日常要看的「说明书首页」。故障逐步处方仍以 [docs/Runbook.md](docs/Runbook.md) 为准；装机从零见 [docs/Ubuntu部署手册.md](docs/Ubuntu部署手册.md)。

### 1. 访问入口（只发这两个）

| 场景 | 地址 | 说明 |
|------|------|------|
| **公司办公区（内网）** | `http://192.168.30.46` | 有线/无线办公网用这个 |
| **内外网统一（2026-07-30 起首选）** | `http://dash.besteasy.com:8001` | 海鹏映射；**必须带 `:8001`**；内外网同一入口 |
| **公司外 · 旧公网 IP** | `http://101.254.102.94:8001` | 过渡期；**办公区内用旧公网 IP 打不开是正常的**（NAT 回流） |

- **登录页（唯一）**：`/login`（未登录访问 `/`、`/admin` 也会到这里）  
- **管理功能**：登录管理员账号后进入 `/admin`（**没有**单独的管理员登录网址）  
- **不要**给业务负责人发 `/admin` 或一长串 `/bu/…`——根地址 + 各自账号即可  
- 外网 IP/端口由 IT 防火墙映射固定；**改机 IP 或 nginx 监听端口前先问 IT**，否则外网入口会断  

### 2. 生产机长什么样

| 项 | 值 |
|----|-----|
| 代码目录 | `/opt/kanban/看板正式程序`（git，跟踪 `main`） |
| 应用进程 | `systemd` 单元 **`kanban`** · User=`lee` · 主端口 **`127.0.0.1:8018`** |
| 对外 | 首选 **`dash.besteasy.com:8001`**；nginx 静态 `frontend/dist` + 反代 API（Host 须带端口，见 CSRF 铁律） |
| 日更 | 进程内 **ScheduleLoop**（时刻以管理端 `schedule_times` 为准） |
| 发版 | `deploy/linux/publish_kanban.sh --pull`：强制库备份 → 可选 **:8019 候选预热** → health/runtime 对齐后切主；失败回退主进程（3.7.0+ / 3.7.3） |
| 其它 cron | 小时 healthcheck、每日备份（**不要**靠 cron `run.py --scheduled` 刷新页面内存） |
| 远程运维 | 家：`ssh kanban-home`；公司内网：`ssh kanban-lan`（密钥与跳板见工作区「公司电脑（部署机）」档案，**不进本仓**） |

### 3. 日常命令（在部署机上）

```bash
# 是否活着
systemctl is-active kanban nginx
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/api/v1/health
curl -s http://127.0.0.1/api/v1/health   # 看 built_at / 灯色

# 版本
cd /opt/kanban/看板正式程序 && cat VERSION && git rev-parse --short HEAD

# 拉代码（无脏工作区）
cd /opt/kanban/看板正式程序 && git pull --ff-only
# 应用自愈：向主进程发 SIGTERM，systemd 会拉起（或 sudo systemctl restart kanban）

# 日志
journalctl -u kanban -n 80 --no-pager
# 应用/前端错误：数据/日志/ 、数据/前端错误.log
```

管理端也可：「更新数据」（重跑管道写内存）、「检查更新 / 一键更新」（git 升级程序）。

### 4. nginx 铁律（2.4.3 · 必守）

**根路径 `location = /` 必须 `proxy_pass` 到后端**，禁止：

```nginx
# ❌ 错误：dist 有 index.html 时永远不走后端
location = / { try_files /index.html @backend; }
```

正确形态见仓库模板 [`deploy/linux/nginx-kanban.conf`](deploy/linux/nginx-kanban.conf)：

- `location = /` → `proxy_pass http://kanban_api`（后端对纯 BU 会话 **303 → `/bu/xxx`**）  
- `location /` 仍可 `try_files` 托管其它 SPA 资源  
- `/api` `/admin` `/login` `/bu` `/export.*` 反代后端  

**改完 conf 必须落地并 reload**（一键更新不会替你做）：

```bash
cd /opt/kanban/看板正式程序
sudo cp deploy/linux/nginx-kanban.conf /etc/nginx/sites-available/kanban
sudo nginx -t && sudo systemctl reload nginx
# 核：应见 proxy_pass，不应在 location = / 里出现 try_files /index.html
grep -A12 'location = /' /etc/nginx/sites-enabled/kanban | head -15
```

前端另有双保险：纯 BU 打开 `/` 或整体 cockpit **403** 会回流本账号业务线（仍建议 nginx 层一次做对）。

### 5. 发版后浏览器

- `index.html` 为 `no-store`；带 hash 的 `/app/assets/*` 长缓存；**theme.css 带 `?v=` 产品版本**（3.7.7）  
- 管理端发版后若白屏 /「Failed to fetch dynamically imported module」：让用户 **强制刷新**（Ctrl/Cmd+Shift+R）或换浏览器清缓存  
- 标准发版：部署机 `bash deploy/linux/publish_kanban.sh --pull`（可选 `--nginx-cutover`）；细节见 Runbook  


### 6. 坏了先看哪

| 现象 | 先查 |
|------|------|
| 完全打不开 | `systemctl status kanban nginx`；`curl` 本机 `:80` / `:8018` |
| 业务线「第一次能进、再开根地址进不去」 | nginx `location = /` 是否仍 `try_files index`（§4）；前端是否已是 2.4.3+ |
| 页面数据不随「到点」变 | `/api/v1/health` 的 `built_at`；日志是否有 `schedule_loop`；管理端是否点过「更新数据」 |
| 体检黄/红 | 管理端控制台详情；手填缺月 / 未抓到源等（黄≠服务挂了） |
| 一键更新被拒 | 工作区是否脏（如把日志写进了代码目录） |

完整处方卡 → [docs/Runbook.md](docs/Runbook.md)。

### 7. 敏感信息边界

- **本 README / 本公开仓**：可写内网 IP、外网入口形态、命令模板  
- **不可写入本仓**：sudo 口令、SSH 私钥、智云/看板业务密码、真实金额与客户表  
- 口令与跳板细节只放工作区本地「公司电脑（部署机）」档案（gitignore / 不上云）

---

## 文档地图

| 你想… | 去读 |
|--------|------|
| **线上运维 / 入口 / nginx** | **本节 [生产运维](#生产运维)** · [docs/Runbook.md](docs/Runbook.md) |
| 给同事讲怎么点页面 | [docs/用户手册/](docs/用户手册/)（看板 · 管理端 · FAQ） |
| 弄清六源字段与进料 | [docs/数据来源说明.md](docs/数据来源说明.md) |
| 在 Ubuntu 上装 / 升级 | [docs/Ubuntu部署手册.md](docs/Ubuntu部署手册.md) |
| 看端 API / 渲染约定 | [docs/api-v1-cockpit.md](docs/api-v1-cockpit.md) · [docs/api/](docs/api/) |
| 接口与库表清单 | [docs/softeng/](docs/softeng/) |
| 为什么这样设计 | [docs/madr/](docs/madr/) |
| 系统教学向总览 | [docs/系统教学说明_甲骨易经营看板_v1.md](docs/系统教学说明_甲骨易经营看板_v1.md) |
| 文档总索引 | [docs/README.md](docs/README.md) |

---

## 模块地图（代码）

| 路径 | 职责 |
|------|------|
| `src/ingest/` | 智云/台账抓取与清洗（**`fetch_zhiyun.py` 业务降级点勿改**） |
| `src/db*` / `src/domain/` | 入库、金额「分」、领域计算 |
| `src/routes/` | HTTP：登录、驾驶舱、管理端、导出 |
| `src/notify.py` + `src/alert_store.py` | **本机**告警（零外发） |
| `frontend/src/` | Vue 看端 + 管理端 |
| `tests/run_verify.sh` | 一键门禁：语法 + 回归红线 32 周期 + 全量测试 |
| `deploy/linux/` | systemd / nginx 模板 |

## 质量与发布约定

- 核心数字有回归基准：库内计算结果与基准 JSON 对齐；多周期金额一致性有自动化检查  
- 前端展示串由后端给出，避免浏览器自行做金额运算导致口径漂移  
- 发布只走 `main`；推远端前会检查是否误带真实金额、客户名、账号口令等敏感内容  
- 公开仓库**不推送** git tag / GitHub Release（版本以 `VERSION` + `CHANGELOG` 为准）  
- 全量自检：在项目根、**优先 `.venv/bin/python`**（`run_verify.sh` 自动选用），`KANBAN_OFFLINE=1 sh tests/run_verify.sh`；启动时会跑 `scripts/materialize_offline_fixtures.py` 写入脱敏 `_golden_data`/`数据/`。判绿看真实退出码，勿用 `| tail` 假绿

---

## 许可证与数据安全

本仓库代码用于甲骨易内部经营看板。  
**请勿**把 `数据/` 下的真实 Excel、数据库、账号文件提交进 git 或发到公开渠道。演示截图仅使用本地 golden / 离线样例数据生成。
