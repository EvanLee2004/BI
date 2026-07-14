# 甲骨易智能经营罗盘

**轻量自建经营利润驾驶舱** —— 每天自动抓数、算到税前利润，内网/手机可看。  
Python · SQLite · FastAPI · 手写 SVG 图表 · **无 React / 无 npm / 无重型 BI**

| 版本 | 架构 | 质量 |
|:---:|:---:|:---:|
| **v1.4.0-beta** | 五层单向 · CSS/JS 外置 · JSON API | 回归红线 32 周期 · golden 数字全等 |

```bash
python run.py             # 抓数 → 建库 → 算账 → 出 HTML
python run.py --serve     # 内网双端服务（默认 :8018）
KANBAN_OFFLINE=1 sh tests/run_verify.sh   # 一键全绿验证
```

---

## 这是什么

语言服务公司财务/管理层要用的**实时利润看板**：

- 脱离 Excel，每天自动更新一次即可  
- 管理利润表算到**税前利润**（确认口径比财务记账更前置）  
- 科技风暗色界面（可切浅色），手机连内网就能看  
- **同一入口账号分流**：整体 / 各 BU / 管理员，不是多个裸链接  

| 角色 | 入口 | 能做什么 |
|------|------|----------|
| 管理层（整体） | `/` 登录 · 权限=整体 | 全公司 KPI、利润表、结构、排名；进各 BU；导出 PNG |
| BU 负责人 | `/` 登录 · 权限=某 BU | 只看本 BU（销售名单过滤，**跨 BU 不泄漏**） |
| 财务管理员 | `/admin` | 改明细、手填/分摊/去税、预算、账号、销售归属、一键更新 |

**设计铁律**：前端**不做任何金额运算**。年/季/月/任意区间的数字全部在 Python 预渲染好，浏览器只负责显示切换。

---

## 系统架构

五层单向数据流。换数据源只动抓数层；库只给后端碰；抓失败永不中断管道。

<p align="center">
  <img src="docs/images/architecture.png" alt="系统架构图 v1.5" width="900" />
</p>

<p align="center"><sub>架构图 v1.5 · 对齐产品 v1.4.0-beta · 源文件 <a href="docs/设计图/02_概要设计_系统架构图.svg">SVG</a></sub></p>

### 数据怎么流

```
① 抓数    智云四源自动登录抓 + 收单台账 SMB + 管理端表单手填
    ↓ 进料口：数据/ 目录（6 个 xlsx + 配置，不进 git）
② 清洗    规范化 → 行哈希定位键 → 重放人工调整
③ 存储    SQLite 单文件（std_ 标准表 + 调整/手填人工表）
④ 计算    profit 纯函数 → 32 周期 summary
⑤ 展示    FastAPI · 账号分流页 · static/ 外置 · /api/v1 JSON
```

| 契约 | 含义 |
|------|------|
| 进料口唯一接缝 | 换源/换抓取方式只动 ①，下游不动 |
| 库是后端私产 | 浏览器只经 HTTP，从不直连 SQLite |
| 抓数可降级 | 失败 → 沿用本地副本 + 体检黄，管道继续跑 |

### 每天怎么跑（大白话）

<p align="center">
  <img src="docs/images/howto-run.png" alt="运行逻辑" width="720" />
</p>

---

## 6 个数据源

| 源 | 提供 | 怎么来 |
|----|------|--------|
| 项目明细（智云） | 收入、系统直接成本 | 自动登录在线抓 |
| 内部译员（智云） | 从成本中减出的内部人力 | 自动抓 + 行数护栏 |
| 下单（智云） | 下单额、部门/销售排名 | 自动抓 |
| 回款记录（智云） | 到账额、客户排名 | 自动抓 |
| 收单台账（Excel） | 五类期间费用 | SMB 共享盘（不可达用本地副本） |
| 手填与调整 | 人力/生产成本补充等 | 管理端表单（**当月未填 = 0**） |

仓库不含业务数据：`数据/` 整目录 gitignore。

---

## 利润怎么算

`config.json` 是税率与费用分类的唯一配置源。

```
收入(不含税)  = 交付额 ÷ 1.06
生产成本      = 系统直接成本 − 内部译员 + 手填 − 直接成本增值税(默认0)
毛利          = 收入 − 生产成本
五类期间费用  = 手填人力 + 台账费用（营销/管理/固定运营/研发/财务）
附加税费      = 增值税 × 12%（增值税 = 不含税收入 × 6%）
税前利润      = 毛利 − 五类费用 − 附加税费 + 其他损益
```

要点：

- **调整可重放**：改明细 = 写指令，不改原始；每次重抓后自动重放  
- **公共费用按月分摊**到 BU（合计可 &lt; 100%，残留留公司层）  
- **费用去税率**按类别手填（空 = 不去税）  
- 每轮更新有数据体检（绿 / 黄 / 红）

**每日更新 / 改数时序**

<p align="center">
  <img src="docs/images/sequence.png" alt="关键流程时序图" width="820" />
</p>

**数据库结构**

<p align="center">
  <img src="docs/images/er.png" alt="数据库 ER 图" width="820" />
</p>

---

## 页面长什么样

**用户端四段**

1. **基本情况** — 收入 / 毛利 / 税前利润 / 下单 / 回款 KPI  
2. **经营利润** — 趋势图 · 管理利润表（可下钻）· 费用构成 · 回款  
3. **收入与毛利结构** — 按客户 / 按销售 + 集中度  
4. **资金与回款** — 回款情况 + 下单/回款排名（支持任意日期段）

顶部：年 / 季 / 月日历切换 · 深浅色 · 体检徽章 · 整页 PNG 导出  

**管理端**：明细改数 · 手填/分摊/去税 · 预算 · 异常处理 · 销售归属 · 账号权限 · 一键更新  

**一键更新**：`git pull --ff-only` → 依赖变了自动 pip（清华镜像）→ 看门狗重启；坏版本自愈回滚。用 `看门狗启动.bat` 起服务。

---

## v1.4 前后端怎么拆的

搬家不装修：观感对齐 v1.3.1，**无 React、无 npm**，部署机无需 Node。

```
static/css/theme.css       主题
static/js/cockpit.js       整体页交互
static/js/cockpit-bu.js    BU 页
static/shell.html          登录后壳 → fetch 视图

GET /api/v1/cockpit            驾驶舱 JSON（numbers ≡ golden）
GET /api/v1/cockpit/view       像素级 HTML
GET /api/v1/cockpit/bu/{name}  单 BU JSON
```

说明：[交付说明](docs/v1.4前后端分离交付说明.md) · [API 契约](docs/api-v1-cockpit.md)  
回退：`KANBAN_LEGACY_INLINE=1 python run.py --serve`

---

## 快速开始

```bash
git clone https://github.com/EvanLee2004/BI.git && cd BI
# 国内镜像：git clone https://gitee.com/Lee157/oracleeasy--bi.git && cd oracleeasy--bi

python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium   # 导出 PNG + 智云自动登录

# 把 6 个数据文件放进 数据/（见 数据/README.md；仓库不带数据）
python run.py             # 更新一次
python run.py --serve     # 起服务（KANBAN_PORT 可覆盖端口）
```

| 项 | 说明 |
|----|------|
| 默认账号 | 管理员 `lushasha` / `kanban2026`；查看账号初始 `8888` → **上线前改掉** |
| 账号文件 | `数据/看板账号.json`（明文、不进 git；缺则自动 seed） |
| 智云账号 | 管理端 → 设置页填写 |
| Windows 装机 | [docs/Windows部署手册.md](docs/Windows部署手册.md) |
| 测/正式切换 | 只改 `config.json` 的 `data_dir` |

---

## 代码地图

```
run.py / config.json / VERSION
static/                 # v1.4 外置 CSS/JS/壳
src/
  ingest/               # 抓数 + 清洗管道
  profit.py             # ★ P&L 纯函数
  api_v1.py             # 驾驶舱 JSON
  db.py / schema.py     # SQLite
  render.py / server.py # 页面 + FastAPI
  accounts.py / bu.py   # 账号与 BU 归属
  updater.py            # 一键更新 + 看门狗
tests/  docs/  golden/
```

---

## 质量与发布

- **回归红线**：库算 == 文件直算，32 周期数字一分不差  
- **golden 全等**：`/api/v1/cockpit` 的 `numbers` 与基准 JSON 全等  
- **前端不算数**：产物里出现 `toFixed` / `parseFloat` 即测挂  
- 铁律全文见 [CLAUDE.md](CLAUDE.md)  
- 分支：`main` 唯一发布线；push 前核无真实金额 / 客户名 / 账号进库  

---

## 文档与设计图

| 资源 | 说明 |
|------|------|
| [architecture.png](docs/images/architecture.png) | 系统架构（README 主图，GitHub / Gitee 均可渲染） |
| [howto-run.png](docs/images/howto-run.png) | 每天怎么跑（大白话） |
| [sequence.png](docs/images/sequence.png) | 每日更新 / 改数时序 |
| [er.png](docs/images/er.png) | 数据库 ER |
| [docs/设计图/](docs/设计图/) | 矢量源 SVG（编辑用） |
| [Windows 部署手册](docs/Windows部署手册.md) | 装机 · 计划任务 · 看门狗 |
| [数据来源说明](docs/数据来源说明.md) | 六源字段与口径 |
| [v1.4 交付说明](docs/v1.4前后端分离交付说明.md) | 分离动机 · 回退 · 边界 |

> 需求台账、详细设计、迭代计划等在项目本地文档库（含业务口径，不随公开仓发布）。

---

**产品阶段**：公测 Beta（`1.4.0-beta`）→ 去掉 `-beta` 即为 1.0 正式版。
