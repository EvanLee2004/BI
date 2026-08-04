# 3.7.9 活体 L1–L4（API 级 + 源码静态）

> 环境限制：本 EXECUTOR 工位无交互浏览器验收。  
> 证据形态：**API 级 TestClient 实跑** + **设置页源码/产物静态核对**。

## L1 · 开设置·账号表

| 动作 | 结果 |
|------|------|
| `GET /api/v1/admin/accounts`（管理员登录） | 返回账号列表；管理员 caps 管理类 + 全部导出 true |
| 源码 `SettingsView.vue` | 管理员行渲染「管理员 · 全部权限」，**无** checkbox 矩阵 |
| 源码 `useSettingsForm.ts` | `CAP_KEYS` 仅四导出 |

## L2 · 无「看整体」能力勾

| 动作 | 结果 |
|------|------|
| 扫 `SettingsView.vue` | 无「看整体」「进管理端」能力勾文案 |
| 扫 `CAP_KEYS` | 无 `view_main` / 管理类 key |
| 单元 `TestSettingsUiSource379` | 钉死上述静态约束 |

## L3 · 改整体号导出勾 → 保存 → 重载

| 动作 | 结果 |
|------|------|
| 将 `overall` 的 `export_page_png=false` 写入 `POST /api/v1/admin/accounts` | 200 |
| 再 `GET /api/v1/admin/accounts` | `export_page_png=false` 保持；`export_pl_xlsx` 仍 true |

## L4 · 无 pl 导出 → 403

| 动作 | 结果 |
|------|------|
| `no_pl` 整体号登录 | session.caps.export_pl_xlsx=false；can_main=true |
| `GET /api/v1/export/pl.xlsx` | **403** |

## 限制说明

- 未在本机起真实 Chromium 点设置页 UI；UI 以 **源码 + dist 构建产物**（含「管理员 · 全部权限」「管理员固定全权」）为准。
- 服务端硬规则与 403 由 `tests/test_task_3_7_9_caps.py` 全绿覆盖。
