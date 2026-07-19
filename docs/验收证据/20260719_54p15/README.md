# 54.15 证据索引

| 项 | 路径 |
|----|------|
| R-30 白名单源码 | `src/domain/expense/chart_whitelist.py` |
| R-30 单元（含 shipped pack） | `tests/test_task54p15_chart_whitelist.py` · `whitelist_unit.log` |
| R-30 改前/改后 | `改前改后_口径证据.md`（改前=stage55_rc7 无 filter；改后=filter→_pack_expense_area） |
| R-31 热力 | `frontend/src/components/ExpenseHeatmap.vue`（confine/grid/visMap） |
| R-32 表头+tooltip | `LedgerTable.vue` ledger-caliber-note；Trend/Expense/Receipts confine |
| 交付报告 | `docs/20260719_任务书54.15交付报告.md` |

## 截图说明

未伪造改前/改后像素并排图。Playwright 本批未做双图抓屏；以**驱动 shipped `filter_expense_monthly_raw_for_charts` + `_pack_expense_area`** 的断言证明「成本」不进 `area_series` 名。
