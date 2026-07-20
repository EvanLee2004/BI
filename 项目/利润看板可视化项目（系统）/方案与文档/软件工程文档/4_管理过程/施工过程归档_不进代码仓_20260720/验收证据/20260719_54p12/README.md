# 54.12 验收证据索引

| 项 | 证据 |
|----|------|
| R-06 ruff | `ruff check src/` EXIT:0（run_verify 1a 步） |
| R-07 B023 | `src/schema.py` `_side(..., _cur_fen=cur_fen)` 绑定 |
| R-08 | `tests/run_verify.sh` 含 ruff check |
| R-01 | `tests/test_task37_expense_perm.py` + `tests/test_authz.py` |
| R-10 | 54.14 commit `38855a8`；`ExpenseSection.vue` withWanUnit |
| R-13/14/15 | `tests/test_task54p12_export_consistency.py` |
| R-02 | `LedgerView.vue` data-testid=ledger-empty |
| R-03 | `SettingsView.vue` zyDrawer |
| R-04 | `ExpenseSection.vue` exp-body-fixed min-height |
| R-05 | `TrendChart.vue` grid bottom 64 / height 400 |
| R-09 | AdminLayout nav-manual + route `admin-manual` |
| R-12 | 发布说明「本期包含/未包含」 |
