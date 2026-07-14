# 07 · HTTP 接口清单（权威 · 从 server.py 数出）

> **产品 v1.5.0-beta**（`程序/看板正式程序` HEAD 以仓库为准）  
> **统计方法**：对 `src/server.py` 用正则提取 `@app.get|post|…`，共 **55** 个注册路由；另挂载 `StaticFiles` 于 `/static/*`（不计入 55）。  
> **鉴权**：从路由函数前几行是否调用 `_require` / `_user` / `_vacct` / `_can_view_*` 归纳；细节以源码为准。  
> 页面返回 HTML；`/api/*` 多为 JSON。更细的 cockpit 字段见程序仓 `docs/api-v1-cockpit.md`。

## 一、页面与静态

| 方法 | 路径 | 鉴权 | 说明 | 谁在用 |
|------|------|------|------|--------|
| GET | `/` | 未登录→登录页；已登录按权限分流 | 看板统一入口 | 浏览器 |
| POST | `/login` | 公开 | 账号+密码表单登录 | 看端登录表单 |
| GET | `/bu/{name}` | 已登录且可看该 BU | BU 独立页 HTML | BU/整体/管理员 |
| GET | `/admin` | 未登录→管理员登录页；已登录管理员→控制台 | v1.5 默认 `static/admin/admin.html` | 管理员 |
| POST | `/admin/login` | 公开 | 管理员登录 | 管理端登录表单 |
| GET | `/admin/logout` | 清 cookie | 退出管理端 | 管理端 |
| GET | `/admin/app.js` | 公开（壳资源） | 读 `static/admin/admin.js` 并注入 `__MANUAL_ITEMS__` | 管理端页面 |
| GET | `/static/*` | 公开 | CSS/JS/壳（看端+管理端） | 浏览器 |
| GET | `/export.png` | 整体/管理员会话 | 整页 PNG 导出 | 整体页 |
| GET | `/bu/{name}/export.png` | 可看该 BU 的会话 | BU 页 PNG | BU 页 |

## 二、JSON API v1（看端分离 · 纯序列化）

| 方法 | 路径 | 鉴权 | 入参/返回要点 | 谁在用 |
|------|------|------|----------------|--------|
| GET | `/api/v1/session` | 已登录 | 当前账号公开字段 | 壳/外部 |
| POST | `/api/v1/login` | 公开 | body: account, password → cookie + redirect | JSON 客户端 |
| POST | `/api/v1/logout` | 清 cookie | ok | 同上 |
| GET | `/api/v1/cockpit` | 整体/管理员 | 整体 summary JSON + `numbers` | 外部/调试 |
| GET | `/api/v1/cockpit/bu/{name}` | 可看该 BU | BU summary JSON | 外部/调试 |
| GET | `/api/v1/cockpit/view` | 整体/管理员 | 像素级 HTML（render 缓存） | shell.html |

## 三、只读动态查询（看端）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/daily` | 整体/管理员 | 任意日期段逐日下单/回款+排名；BU 会话 401 |
| GET | `/api/profit_ranking` | 整体/管理员 | 收入/毛利按客户或销售全量 |
| GET | `/api/health` | 管理员（管理端体检） | 绿/黄/红 + 警告 |

## 四、管理端写读（均需管理员会话，除非注明）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/accounts` | 账号表明文管理 |
| POST | `/api/my_passwd` | 看的人自改密码（非管理员看端） |
| GET | `/api/detail` | 明细分页（可 unfilled_dept / unclassified） |
| GET | `/api/detail_export` | 明细导出 xlsx |
| GET | `/api/exceptions` | 异常总览计数 |
| GET | `/api/order_depts` | 下单部门清单 |
| POST | `/api/refresh` | 立即更新（异步） |
| GET | `/api/refresh_status` | 更新进度 |
| GET | `/api/history` | 历史快照列表 |
| GET | `/api/history/{day}` | 某日页面快照 HTML |
| GET/POST | `/api/bu_config` | BU 名单+销售归属 |
| GET | `/api/sales_pool` | 销售归属池 |
| GET | `/api/config_changes` | 配置变更留痕 |
| GET | `/api/version` | 产品版本+changelog |
| GET/POST | `/api/update/check` · `/api/update/apply` | 一键更新 |
| GET/POST | `/api/settings` | 调度/备份/智云/台账路径等 |
| POST | `/api/adjust` · `…/revoke` · `…/rearm` · `…/expired/revoke_all` | 明细调整 |
| GET | `/api/adjustments` | 调整台账列表 |
| GET/POST | `/api/manual` · `/api/manual_batch` | 手填 |
| GET/POST | `/api/alloc_ratios` | 公共费用按月分摊比例 |
| GET/POST | `/api/detax_rates` | 费用去税率 |
| GET/POST | `/api/budget` · `/api/budget_batch` · `/api/budget_depts` | 业绩目标 |
| GET | `/api/adjust_fields` | 可调字段白名单（schema 推导） |

## 五、端点计数（诚实）

| 类别 | 数量 |
|------|------|
| server.py `@app.*` 注册 | **55** |
| 其中 GET | 34 |
| 其中 POST | 21 |
| StaticFiles `/static` | 另计，非装饰器 |

> 若增删路由：改 `server.py` 后重跑本统计脚本，并更新本表。
