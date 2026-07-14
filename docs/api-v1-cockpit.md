# API v1 · 驾驶舱 JSON（v1.4.0-beta 前后端分离）

> 金额只在后端 `profit` 计算；本接口**序列化**已算好的 summary。  
> 对照测试：`tests/test_api_v1_numbers.py` 与 `golden/baseline_numbers.json` **全等**。

## 会话

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/session` | 当前账号；未登录 401 |
| POST | `/api/v1/login` | `{account,password}` → cookie + session |
| POST | `/api/v1/logout` | 清 cookie |

## 驾驶舱

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/cockpit` | 整体 JSON（含 `numbers` 快照）；需整体/管理员；BU 账号 403 |
| GET | `/api/v1/cockpit/bu/{name}` | 单 BU JSON；会话闸 |
| GET | `/api/v1/cockpit/view` | **像素级** HTML：与 `/` 同源 `render_dashboard` 输出（外置 CSS/JS） |

## 静态资源

| 路径 | 内容 |
|---|---|
| `/static/css/theme.css` | 原 `theme.get_css()` 全文 |
| `/static/js/cockpit.js` | 整体页 JS（周期/主题/导出/排名等） |
| `/static/js/cockpit-bu.js` | BU 页 JS |
| `/static/shell.html` | 登录后轻量壳 → fetch `cockpit/view` 再 document.write |

回退直出 HTML：`KANBAN_LEGACY_INLINE=1`。

## 外部复用（如飞书机器人）

1. 内网携带会话 Cookie 或后续加只读 token（当前与看板同一登录态）。  
2. `GET /api/v1/cockpit` 取 `numbers.periods["2026年"].kpi` 等字段推送。  
3. **不要**解析 HTML；数字以 JSON 为准。

## 既有管理端 API

`/api/manual*` `/api/alloc_ratios` `/api/detax_rates` `/api/detail` `/api/refresh*` `/api/settings` `/api/update/*` 等**保留**，行为与 v1.3.1 一致。
