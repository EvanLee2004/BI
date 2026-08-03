# domain 包 · 可导航门面

> 产品版本以根 `VERSION` 为准（当前 3.7.x）。本包只做**展示领域结构**（费用白名单、PL 结构、排名、重点客户等），**不算金额**；算账在 `src/profit/`。

本目录是**业务域入口**，不是第二套算账实现。看数链路：**domain → viewmodels → Vue**；**无** `render_*` 驾驶舱双轨（3.0.0+ 已物理删除）。

| 包 | 真实逻辑 | 说明 |
|----|----------|------|
| `config_engine` | 本包实现 | 配置引擎 |
| `pl/` | 本包实现 | 利润表 / KPI 共享结构 |
| `key_customers/` | 本包实现 | 3.4.0 重点客户六档（自然年下单预估）；summary 顶层挂载 |
| `kpi` / `expense` / `receipts` / `rankings` / `ledger` | re-export → `profit` | 可导航别名；与 `profit` 同对象 |
| `trend` | （空门面） | HTML 趋势卡已在装运层；本包不再 re-export |
| `export` | re-export → `export_png.screenshot_png` | PNG 截图边界；HTML 快照走 `kanban_snapshot` / `export_html` |

**周边巨石（本包外，可导航）**：

- `src/profit/`：算账 summary（冻结口径；库内/算账 **int 分**）
- `src/db*` / `schema.py`：SQLite 读写
- `src/viewmodels/`：API/页面用 VM 打包（`value` + `value_disp`）
- `src/export_html.py` · `export_png.py` · `export_pl_xlsx.py`：导出（snapshot / 截图 / Excel）
- `src/server.py` + `routes/*`：HTTP（业务/管理/运维均 `/api/v1/*`）

拆分原则：只搬家、不改算法；拆后必跑 32 周期回归 + `KANBAN_OFFLINE=1 sh tests/run_verify.sh`。
