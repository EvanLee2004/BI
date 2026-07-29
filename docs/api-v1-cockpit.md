# API v1 · 驾驶舱 JSON（3.0+ 现行）

> 金额只在后端 domain/profit 计算；本接口**序列化**已算好的 summary / ViewModel。  
> **现行主路径**：Domain → packers/format → `/api/v1/vm/*` → Vue（`frontend/dist`）。  
> 对照：`tests/test_api_v1_numbers.py`、`tests/test_g1_2_7_6_vm_numbers_contract.py`。  
> 架构 SSOT：`docs/architecture_ssot_3.md`。

## 会话

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/session` | 当前账号；未登录 401 |
| POST | `/api/v1/login` | `{account,password}` → cookie + session |
| POST | `/api/v1/logout` | 清 cookie |

## 驾驶舱（现行）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/vm/cockpit` | 整体 ViewModel；需整体/管理员 |
| GET | `/api/v1/vm/bu/{name}` | 单 BU ViewModel；会话闸 |

## 已废止 / 已删

| 路径 | 状态 |
|---|---|
| `GET /api/v1/cockpit` | 已删（2.6.9+）；请用 `/api/v1/vm/cockpit` |
| `GET /api/v1/cockpit/bu/{name}` | 已删；请用 `/api/v1/vm/bu/{name}` |
| `GET /api/v1/cockpit/fragments` | **3.1.0 起不再注册**；请求 → 404 |
| `GET /api/v1/cockpit/bu/{name}/fragments` | **3.1.0 起不再注册**；请求 → 404 |
| `GET /api/v1/cockpit/view` | 已删（B-P5） |

历史 fragments 合同见 `docs/archive/cockpit_render_contract_v1.md`（归档作废）。

## 静态资源（现行）

| 路径 | 内容 |
|---|---|
| `/static/css/*` | 主题与公共样式 |
| `/app/*` 或 SPA 入口 | Vue 构建产物（`frontend/dist`） |
| `/static/templates/export/*` | 导出 snapshot 壳（服务端） |
| `/static/templates/charts/*` | 图表图例等小模板（`charts.py`） |
| `/static/templates/partials/*` | 服务端 partial（BU 导航等） |

**已删除（3.1.0）**：`static/js/cockpit.js`、`static/js/cockpit-bu.js`、`static/js/assemble/*`（旧 shell 拼装）。

## 导出

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/export.html` | `kanban_snapshot` 自包含 HTML |
| GET | `/api/v1/export.png` | 与 HTML 同源截图 |

## 外部复用（如飞书机器人）

1. 内网携带会话 Cookie。  
2. 优先 `GET /api/v1/vm/cockpit` 或数字契约字段；**不要**解析 HTML。  
3. 数字以 JSON / VM 为准。

## 管理端 API

`/api/v1/admin/*` 等写路径见 `docs/softeng/07_HTTP接口清单_全端点.md`。
