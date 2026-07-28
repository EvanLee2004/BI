# 2.7.1 S0 盘点

- **日期**：2026-07-28
- **起点 VERSION**：`2.7.0`
- **HEAD**：`fd269c8`（代码主交付 `b4830f5`）
- **git status**：clean
- **基线/终态 run_verify**：`docs/验收证据/2_7_1/run_verify.log` → **EXIT:0**；回归 32 周期零 diff

## 对照干净目标态

| 项 | 状态 | 说明 |
|----|------|------|
| 2.7.0 v1 rankings/profit 双源 | **已满足** | `/api/v1/rankings/profit` + 旧 `/api/profit_ranking` 仍 200 |
| 2.7.0 detail v1 别名 | **已满足** | `/api/v1/admin/detail` 在；旧 `/api/detail*` 仍注册 |
| 2.7.0 core/structure int 分 | **已满足** | S4 跳过；回归 32 周期已绿 |
| 2.7.0 文档 SSOT / 单 worker | **已满足** | 本刀升到 2.7.1 并改「须重登」 |
| cookie 兼容读 + 21 天窗 | **本刀待做** | `session_ctx.resolve` 仍读 legacy；`SESSION_LEGACY_COMPAT_DAYS=21` |
| legacy 前端 mode==legacy 建造 | **本刀待做** | `viewmodels.frontend_mode` 仍分支 HTML 建造 |
| 旧业务 GET 仍注册 | **本刀待做** | 见下表 |
| 前端/admin 仍调旧读路径 | **本刀待做** | frontend/src 大量 `/api/*` 非 v1；static/js 亦有 |
| 写路径 POST | **本刀不强制迁** | 报告列未迁清单 |

## 仍注册的旧业务 GET（删后须 404）

| 旧路径 | 目标 v1 |
|--------|---------|
| `/api/profit_ranking` | `/api/v1/rankings/profit` |
| `/api/detail` `/api/detail/values` `/api/detail_export` | `/api/v1/admin/detail` `…/values` `…/export` |
| `/api/daily` `/api/bu_daily` | `/api/v1/daily` `/api/v1/bu_daily` |
| `/api/exceptions` `/api/order_depts` | `/api/v1/admin/exceptions` `/api/v1/admin/order_depts` |
| `/api/history` `/api/history/{day}/vm` `/api/history/{day}` | `/api/v1/history…` |
| `/api/version` `/api/update/check` | `/api/v1/version` `/api/v1/update/check` |
| `/api/bu_config` GET `/api/sales_pool` `/api/config_changes` | `/api/v1/admin/…` |
| `/api/settings` GET `/api/archive_export` | `/api/v1/admin/settings` 等 |
| `/api/adjustments` `/api/manual_items` `/api/manual` GET `/api/alloc_ratios` `/api/detax_rates` GET `/api/budget` GET `/api/adjust_fields` | `/api/v1/admin/…` |
| `/api/accounts` GET | `/api/v1/admin/accounts` |
| `/api/export.html` `/api/export/pl.xlsx` | `/api/v1/export/…` |

## 例外（可非 v1）

- `GET /api/health`
- `GET /api/refresh_status`

## 本刀交付

- **VERSION=2.7.1**
- 会话仅 `kanban_sid`；旧 cookie 不能维持登录
- 业务读仅 `/api/v1/*`（+ 上表例外）；旧 GET 404
- 只 vue；文档三源 2.7.1；live 截图；push+上机
