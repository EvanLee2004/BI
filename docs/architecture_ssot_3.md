# 架构 SSOT · 3.2.0

> 现行唯一真相。历史 fragments/render 合同见 `docs/archive/`。

## 看数主路径

```
Domain（算账 SSOT）
  → viewmodels/packers + format（显示串）
  → GET /api/v1/vm/cockpit | /api/v1/vm/bu/{name}
  → Vue frontend/dist
```

**禁止**：`src/render*.py`、整页 HTML 装运、服务端预拼驾驶舱 fragments、`user_html` 进程缓存。

## 进程装配（3.2.0 薄门面）

| 模块 | 职责 |
|------|------|
| `server.py` | 薄 composition / re-export；`create_app` → `app_factory.build_app`；`serve()` |
| `app_factory.py` | 中间件、静态/SPA、会话闭包、DI、`register_all` |
| `middleware_stack.py` | GZip / RequestId / Maintenance |
| `refresh_pipeline.py` | `publish` / `do_full` / `do_recompute` / `start_refresh_async` |
| `app_state.py` | 唯一 `_state` / `_LOCK`（与 `server._state` **同一对象**） |

稳定契约：测试与 routes 可继续 `import server`；打桩 `server._do_full` 仍生效。

## 导出

```
assemble_export_pack → build_export_html（kind=kanban_snapshot）
  → GET /api/v1/export.html
  → GET /api/v1/export.png（Playwright 截同款 HTML）
```

## 活模板（勿删）

| 目录 | 用途 |
|------|------|
| `static/templates/export/` | snapshot 壳 |
| `static/templates/charts/` | `charts.py` 图例/空态 |
| `static/templates/partials/` | 服务端 partial（导航等） |
| `static/templates/errors/` | HTTP 错误页 |
| `static/templates/login.html` 等 | 登录皮 |

## 墓碑路由（旧路径 → 结果）

| 旧路径 / 机制 | 现行结果 |
|---------------|----------|
| `/api/v1/cockpit/fragments` | **404**（未注册） |
| `/api/v1/cockpit/bu/{name}/fragments` | **404**（未注册） |
| `/api/v1/cockpit/view` / SERVE_SHELL 直出 | **已删**（无路由） |
| `static/js/cockpit*.js` / `page.js` 装运 | **已删**；看端只走 Vue dist |
| 进程态 `user_html` / `fragments` | **不存在**；`publish` 会 pop 清理残留键 |
| VM/API `kpi_body` / `pl_body` / `body_by_period` / `svg_html` 等 | **已删**；JSON 只发结构化 views |

现行入口：`/` → SPA；数据 → `/api/v1/vm/*`；导出 → `/api/v1/export.html` / `export.png`。

## 已删除（3.0.0–3.2.0）

- `src/render*.py`、`static/templates/render/`
- 兼容别名 `build_cockpit_views` / `cockpit_fragments` / strip 族
- fragments 路由注册
- `static/js/cockpit*.js`、`static/js/assemble/`
- `_empty_html_view_fields` 及空 HTML 装运字段
- 进程态 `user_html`

## 刷新 / 状态

- `publish(cfg, summary, *, bu_pages=, views=)`：只发 `summary` + `views` + `bu_pages[{name,summary,views}]`
- **无** `user_html` 键；ready 看 `summary` / `has_data`（`admin_html="ready"` 为兼容哨兵，以 `has_data` 为准）
- `frontend_mode(...)` **恒** `"vue"`

## 门禁

G1 数字 · G2 无 HTML 预装 · G3 导出同源 · G4 零 import render · G5 pl_structure · G6 render 物理删除 · G7 3.1.0 卫生 · **G8 3.2.0 结构**（薄门面 / 无 user_html / 无 HTML 僵尸）

## 禁区

- 改 profit/domain 算账
- 把业务「双榜 dual_rank」当架构双轨删除
- 删活模板 charts/partials/export
- 双轨：胖 server 实现 + 新模块并存
