# 架构 SSOT · 3.0+ / 3.1.0

> 现行唯一真相。历史 fragments/render 合同见 `docs/archive/`。

## 看数主路径

```
Domain（算账 SSOT）
  → viewmodels/packers + format（显示串）
  → GET /api/v1/vm/cockpit | /api/v1/vm/bu/{name}
  → Vue frontend/dist
```

**禁止**：`src/render*.py`、整页 HTML 装运、服务端预拼驾驶舱 fragments。

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

## 已删除（3.0.0–3.1.0）

- `src/render*.py`、`static/templates/render/`
- 兼容别名 `build_cockpit_views` / `cockpit_fragments` / strip 族
- fragments 路由注册
- `static/js/cockpit*.js`、`static/js/assemble/`

## 刷新 / 状态

- `publish`：`summary` + `views` + `bu_pages[{name,summary,views}]`
- 不预装整页 HTML；`user_html` 默认可为空串（兼容测试/ready 检查）

## 门禁

G1 数字 · G2 无 HTML 预装 · G3 导出同源 · G4 零 import render · G5 pl_structure · G6 render 物理删除 · G7 3.1.0 卫生

## 禁区

- 改 profit/domain 算账
- 把业务「双榜 dual_rank」当架构双轨删除
- 删活模板 charts/partials/export
