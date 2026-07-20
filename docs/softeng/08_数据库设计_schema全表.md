# 08 · 数据库设计（对齐 `src/schema.py` · 任务书33 修订）

> **产品 v2.2.0**（2026-07-21）· 唯一 DDL 源：`src/schema.py`  
> **SCHEMA_VERSION = 3**（金额库内 INTEGER **分**；算账路径 Decimal ROUND_HALF_UP，见 MADR-0022）  
> **统计**：标准表 **5** + 人工/元数据表（含历史表）以 schema 为准。  
> **库文件**：`数据/看板.db`（gitignore）。无独立 DB 服务。  
> 配图：`docs/images/er.png`。

## 一、三类哲学

| 前缀 | 含义 | 重建策略 |
|------|------|----------|
| `std_` | 程序从进料口规范化后的**标准事实** | 每次更新**全量重建**，永不手改 |
| `adj_` | **调整指令**（改值/剔除），只追加 | 重建不清；重抓后重放 |
| `manual_` / `meta_` | 手填、预算、分摊、去税、配置留痕、运行日志、schema 版本 | 重建不清 |

无物理外键：调整用 `(目标表, 定位键, 字段)` 逻辑关联 std 行。

## 二、金额：INTEGER 分（SCHEMA v3）

| 规则 | 说明 |
|------|------|
| 存储 | 金额列 **INTEGER，单位：分** |
| 进料 | xlsx 元值 → `decimal.Decimal` → `ROUND_HALF_UP` → 分（`src/money.py`） |
| 算账 | `db.load_*` 返回 **int 分**；`profit` **全程分整数**；仅显示层 `fmt_wan` 等分→万元串 |
| 禁止 | `float × 100` 直乘入库；库内分再 `yuan_to_fen`（双×100） |
| 迁移 | `migrate_money_to_fen_if_needed`：版本门控、幂等、迁移前备份 `*.bak-fen-*` |
| 定位键 | **normalize 用元算哈希**，再转分入库 → 哈希不因分存储漂移 |
| adj 原值/新值 | 金额字段库内为 **分整数字符串**；`list_adjustments` 管理端展示转回**元**；重放 `_values_match` 兼容未迁存量元文本 |
| 预算比率 | 毛利率/税前利润率目标 **≠ 钱**：存**百分位点**（35%→3500），`budget_value_to/from_store`，**绝不用** `yuan_to_fen` |

**非金额 REAL 不动**：分摊比例、去税率仍为百分数 REAL。

## 三、连接与事务边界

| 项 | 约定 |
|----|------|
| WAL | `PRAGMA journal_mode=WAL`（写不挡读） |
| 忙等 | `busy_timeout=5000` ms |
| 同步 | `synchronous=NORMAL` |
| std 重建 | **单事务**：`BEGIN IMMEDIATE` → 清表 + 全表 INSERT → `COMMIT`；失败 `ROLLBACK` 保留旧数据 |
| 中间 commit | 重建链路上**禁止**清表后单独 commit |
| 完整性 | 管道末 `PRAGMA quick_check`；失败 → 运行结果**红** |
| 备份 | 每日滚动 `数据/备份/看板_YYYYMMDD.db`；失败入 `run_reasons` |

## 四、标准表 std_*（5）

| 表 | 主键 | 关键金额列（分） | 定位键 |
|----|------|------------------|--------|
| `std_收入明细` | id | 交付额、项目成本 | SOD 自然键优先 |
| `std_下单` | id | 下单预估额 | 订单号优先 |
| `std_回款` | id | 到账金额 | 回款ID 优先 |
| `std_内部译员` | id | 结算金额 | 任务ID 优先 |
| `std_费用明细` | id | 含税金额 | 行哈希（含金额**元**字符串等） |

日期 TEXT ISO；归属月 `YYYY-MM`；`已删除=1` 软删。

### 定位键重复（A4）

两行内容完全相同 → 同定位键。

| 场景 | 行为 |
|------|------|
| 写调整 `add_adjustment` | 命中 >1 行 → **拒绝** |
| 重放 `apply_adjustments` | 命中 >1 行 → **过期疑似**、不套用 |
| 体检 | `audit_duplicate_locators` 有重复 → **黄** |

## 五、人工表

| 表 | 金额列 | 说明 |
|----|--------|------|
| `adj_调整记录` | 原值/新值 TEXT | 金额字段存**分**整数字符串；非金额仍为原文。管理端录入元→写入前转分 |
| `manual_手填` / `manual_手填BU` | 金额 INTEGER 分 | 当月未填=0 |
| `manual_历史` | 旧值/新值 分 | |
| `manual_预算` / `manual_预算历史` | 金额：分；比率：百分位点 | 见 `BUDGET_RATE_METRICS`；`get_budget` 金额→元、比率→百分数 |
| `manual_分摊比例` | 比例 REAL | 非金额 |
| `manual_分摊比例历史` | 旧值/新值 REAL | 任务书63·H-04：写/删只追加；删除记 新值=NULL；生效表仍可 DELETE |
| `manual_费用去税率` | 税率 REAL | 非金额 |
| `manual_去税率历史` | 旧值/新值 REAL | 任务书63·H-04：写/删只追加；删除记 新值=NULL |
| `meta_schema` | key/value | `version`=SCHEMA_VERSION |
| `meta_运行日志` | 体检JSON | 含 backup / db_check / duplicate_locators |
| `manual_配置变更` | — | 不存密码；任务书63·H-03 起含调整撤销/坚持/批量撤销理由 |

## 六、库外配置（非 SQLite）

| 文件 | 内容 |
|------|------|
| `数据/看板账号.json` | 登录账号（gitignore） |
| `数据/BU配置.json` | BU + 销售名单 |
| `数据/智云配置.json` | 智云凭据/覆盖 |
| `数据/本地配置.json` | 机器专属；程序不写 `config.json` |

## 七、mermaid ER（简化）

```mermaid
erDiagram
  std_收入明细 ||--o{ adj_调整记录 : "定位键逻辑关联"
  std_下单 ||--o{ adj_调整记录 : "定位键逻辑关联"
  std_回款 ||--o{ adj_调整记录 : "定位键逻辑关联"
  std_内部译员 ||--o{ adj_调整记录 : "定位键逻辑关联"
  std_费用明细 ||--o{ adj_调整记录 : "定位键逻辑关联"
  manual_手填 ||--o{ manual_历史 : "变更流水"
  manual_预算 ||--o{ manual_预算历史 : "变更流水"
  meta_schema {
    string key PK
    string value
  }
  meta_运行日志 {
    int id PK
    string 结果
  }
```

**修订记录**：2026-07-16 任务书33 — 整数分 + WAL + 单事务重建 + 重复定位键行为 + quick_check；同日补 SCHEMA v3（adj 分文本 + 预算比率百分位点）。

---

## 换库须知（任务书43 · 2026-07-16）

当前实现：**SQLite only**。业务层零裸 SQL（`db.py` / `db_write.py` / `schema.py`）。

### SQLite 方言清单（换库时必改点）

| 方言/特性 | 位置 | 说明 |
|-----------|------|------|
| `PRAGMA foreign_keys/journal_mode/WAL/busy_timeout/synchronous` | `db.connect` | 连接初始化 |
| `PRAGMA quick_check` / `table_info` / `database_list` | `db`/`schema` | 体检与迁移 |
| `BEGIN IMMEDIATE` + 手动事务 | `db_write.rebuild_std_tables` | 单事务重建 std |
| `INSERT OR REPLACE` | 预算/手填/配置等 | 幂等写 |
| `VACUUM` | `db_write.vacuum_db` | 月末压缩 |
| `date('now', '-N days')` | `prune_run_logs` | 运行日志滚动 |
| `AUTOINCREMENT` / `INTEGER PRIMARY KEY` | `schema` DDL | 主键 |
| 金额 **INTEGER 分** | 全库 | 与 MySQL DECIMAL 映射需迁移脚本 |

### 索引

当前 **未新增预防性索引**。`EXPLAIN QUERY PLAN` 见交付报告附件；表规模适合全表扫描时不建索引。

### 保留策略

| 数据 | 策略 |
|------|------|
| `meta_运行日志` | 默认 365 天滚动（`run_log_keep_days`） |
| `manual_*` 历史/配置变更 | 全量保留；可导出归档，不自动删 |
| `数据/备份/` | `backup_keep_days`（默认 365） |
| 共享盘台账 | **只读**拷入本地；绝不回写共享盘 |

## 索引（任务书64·D2）

std 五表在 `schema.create_all` 建覆盖索引：`定位键`、`(已删除, 归属月)`，以及部门/销售/客户/业务BU 等明细筛选列（`CREATE INDEX IF NOT EXISTS`）。**只改速度不改结果**（golden 零 diff）。

