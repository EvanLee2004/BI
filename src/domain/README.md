# domain 包 · 可导航门面（任务书 54.4·E）

本目录是**业务域入口**，不是第二套算账实现。

| 包 | 真实逻辑 | 说明 |
|----|----------|------|
| `config_engine` | 本包实现 | 配置引擎 |
| `pl/structure` | 本包实现 | 利润表/KPI 共享结构 |
| `kpi` / `trend` / `expense` / `receipts` / `rankings` / `ledger` / `export` | re-export → `profit` / `render` | 可导航别名；`test_domain_reexport` 保证 `is` 同一对象 |

**巨石现状（可导航）**：

- `profit.py`：算账 summary（冻结口径）
- `db.py`：SQLite 读写
- `render.py`：HTML/导出拼装（看端壳已删，仍服务导出与历史快照）
- `server.py` + `routes/*`：HTTP 入口（路由已拆模块）

拆分原则：只搬家、不改算法；拆后必跑 32 周期 + `run_verify`。
