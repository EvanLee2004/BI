# 2.7.2 S0 盘点

- **日期**：2026-07-28
- **起点 VERSION**：`2.7.1`
- **HEAD**：`2cf480c`（代码 `acb9ad9`）
- **基线 run_verify**：终态 `run_verify.log` → **EXIT:0**；回归 32 周期零 diff

## 后端仍非 `/api/v1/*`（本刀必迁后删）

| 方法 | 旧路径 | 新路径 |
|------|--------|--------|
| POST | `/api/adjust` | `/api/v1/admin/adjust` |
| POST | `/api/adjust/batch` | `/api/v1/admin/adjust/batch` |
| POST | `/api/adjust/{adj_id}/revoke` | `/api/v1/admin/adjust/{adj_id}/revoke` |
| POST | `/api/adjust/{adj_id}/rearm` | `/api/v1/admin/adjust/{adj_id}/rearm` |
| POST | `/api/adjust/expired/revoke_all` | `/api/v1/admin/adjust/expired/revoke_all` |
| POST | `/api/refresh` | `/api/v1/admin/refresh` |
| GET | `/api/refresh_status` | `/api/v1/admin/refresh_status` |
| POST | `/api/my_passwd` | `/api/v1/my_passwd` |
| POST | `/api/update/apply` | `/api/v1/admin/update/apply` |
| GET | `/api/health` | `/api/v1/health` |

## 导出裸路径（S4）

| 路径 | 前端引用 | 处理 |
|------|----------|------|
| `/export.html` 兼 `/api/v1/export.html` | 主路径已用 v1 | 删裸 `/export.html` 若测允许；保留 v1 |
| `/export.png` `/export/pl.xlsx` | 测有引用 | 迁或保留双路径中裸的到 v1-only |
| `/bu/{name}/export.html` / `.png` / `pl.xlsx` | TopBarActions / PLTable | 保留页面路径 **或** 统一仍走现有 URL（非 `/api/*` 业务写路径清单外；有引用则保留实现） |

## 前端调用方

- AdminLayout: health, refresh, refresh_status
- TopBarActions: my_passwd
- DetailView / OrderDeptView / LedgerView: adjust*
- static/admin/bootstrap.html, static/js/cockpit*.js: refresh/my_passwd

## 脚本

- `deploy/healthcheck.sh` → `/api/health` 须改 v1
