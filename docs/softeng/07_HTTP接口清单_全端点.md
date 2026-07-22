# 07 · HTTP 接口清单（权威 · 从 server.py 数出）

> **产品 v2.2.7**（2026-07-22；`VERSION` 为准）  
> **统计方法**：对 `src/routes/*` + `server.py` 注册路由扫描；另挂载 dist/`/static/*`。  
> **鉴权**：`_require` / `_user` / `_vacct` / `_can_view_*`；细节以源码为准。  
> 页面 HTML；`/api/*` JSON。VM 字段闸：`scripts/gen_vm_ts.py --check`。cockpit 字段见 `docs/api-v1-cockpit.md`。

## 一、页面与静态

| 方法 | 路径 | 鉴权 | 说明 | 谁在用 |
|------|------|------|------|--------|
| GET | `/` | 未登录→登录页；已登录按权限分流 | 看板统一入口 | 浏览器 |
| POST | `/login` | 公开 | 账号+密码表单登录 | 看端登录表单 |
| GET | `/bu/{name}` | 已登录且可看该 BU | BU 独立页 HTML | BU/整体/管理员 |
| GET | `/admin` | 未登录→管理员登录页；已登录管理员→控制台 | Vue SPA（65 单轨） | 管理员 |
| POST | `/admin/login` | 公开 | 管理员登录 | 管理端登录表单 |
| GET | `/admin/logout` | 清 cookie | 退出管理端 | 管理端 |
| GET | `/admin/app.js` | 公开（壳资源） | 410 已下线（65·L1） | 管理端页面 |
| GET | `/static/*` | 公开 | CSS/JS/壳（看端+管理端） | 浏览器 |
| GET | `/export.html` | 整体/管理员会话 | 整页 HTML 导出（Vue 皮） | 直连 :8018 / 已 reload 的 nginx |
| GET | `/api/export.html` | 同上 | **同实现**；经现网 nginx `/api` 反代（顶栏主路径） | 看端顶栏导出 |
| GET | `/bu/{name}/export.html` | 可看该 BU 的会话 | BU 页 HTML 导出 | BU 页 |
| GET | `/export.png` | 整体/管理员会话 | PNG 兼容保留（前端不走） | 旧客户端 |
| GET | `/bu/{name}/export.png` | 可看该 BU 的会话 | BU PNG 兼容 | 旧客户端 |

## 二、JSON API v1（看端分离 · 纯序列化）

| 方法 | 路径 | 鉴权 | 入参/返回要点 | 谁在用 |
|------|------|------|----------------|--------|
| GET | `/api/v1/session` | 已登录 | 当前账号公开字段 | 壳/外部 |
| POST | `/api/v1/login` | 公开 | body: account, password → cookie + redirect | JSON 客户端 |
| POST | `/api/v1/logout` | 清 cookie | ok | 同上 |
| GET | `/api/v1/cockpit` | 整体/管理员 | 整体 summary JSON + `numbers` | 外部/调试 |
| GET | `/api/v1/cockpit/bu/{name}` | 可看该 BU | BU summary JSON | 外部/调试 |
| GET | `/api/v1/cockpit/fragments` | 整体/管理员 | 渲染就绪碎片 JSON（B-P5；view 已删） | shell.html + page.js |
| ~~GET `/api/v1/cockpit/view`~~ | — | **B-P5 真删** | 回退靠 git |

## 三、只读动态查询（看端）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/daily` | 整体/管理员 | 任意日期段逐日下单/回款+排名；BU 会话 401 |
| GET | `/api/profit_ranking` | 整体/管理员 | 收入/毛利按客户或销售全量 |
| GET | `/api/health` | 管理员（管理端体检） | 绿/黄/红 + 警告 |

## 四、管理端写读（均需管理员会话，除非注明）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/accounts` | 账号表管理（管理员会话**下发明文密码**；任务书64·P / MADR-0020） |
| POST | `/api/accounts/{账号}/reset_passwd` | 管理员重置密码（可选快捷入口）；body `{new?}`；列表亦可直接编辑明文 |
| POST | `/api/my_passwd` | 看的人自改密码（非管理员看端） |
| GET | `/api/detail` | 明细分页；看端费用明细列=白名单（audience）；`month` 或 `month_from`+`month_to` 归属月区间；可 unfilled_dept / unclassified |
| GET | `/api/detail_export` | 明细导出 xlsx（列与当前会话明细一致：看端白名单/管理端全列） |
| GET | `/api/detail/values` | 列去重值（多选筛） |
| GET | `/api/detail/meta` | 列名+类型（看端跟白名单） |
| GET | `/api/settings` | 管理员：含 `feishu_webhook_url` / `run_log_keep_days` / `disk_free_min_ratio`（任务书43） |
| POST | `/api/settings` | 管理员：可写飞书 webhook 等（落本地配置覆盖层） |
| GET | `/api/archive_export?year=YYYY` | 管理员：审计流水年度 xlsx 归档（历史表不删） |
| GET | `/api/exceptions` | 异常总览计数 |
| GET | `/api/order_depts` | 下单部门清单 |
| POST | `/api/refresh` | 立即更新（异步） |
| GET | `/api/refresh_status` | 更新进度 |
| GET | `/api/history` | 历史 VM 存档列表（`vm_YYYYMMDD.json`） |
| GET | `/api/history/{day}/vm` | 某日归档 VM JSON（管理员；Vue `/?archive=` 只读） |
| GET | `/api/history/{day}` | **410** 旧 HTML 快照已停用 |
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
