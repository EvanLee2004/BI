# 3.7.8 活体 L1–L6 自证笔记（脱敏 · EXECUTOR）

> 无真实客户金额。API 以 TestClient / 单元测 + 结构断言自证；UI 路径与 testid 对齐。

| ID | 点了什么 | 期望 | 自证 |
|----|----------|------|------|
| L1 | 管理员保存手填/去税 | 200，可再存 | `tests/test_task_3_7_8_write_lock.py` 连续 detax 200 + already_locked |
| L2 | 无 `export_pl_xlsx` 账号 GET pl.xlsx | **403** | `test_no_pl_export_cap_403` |
| L3 | 无 `export_ledger_xlsx` ledger/export | **403** | `test_no_ledger_export_cap_403` |
| L4 | 设置页能力勾选 | UI: `data-testid=acct-caps` + 保存带 `能力` | 源码 SettingsView + useSettingsForm round-trip |
| L5 | 账号表密码 👁 | GET accounts 含明文 `密码` | `test_admin_accounts_returns_plaintext_password` |
| L6 | exceptions 失败 | 错误态非「无待处理」 | `test_task_3_7_8_exceptions_false_green.py` |

## 结构指针

- 写锁：`src/routes/_srv.py` · `manual.py` · `config_api.py`
- 能力：`src/authz.py` · export/manual/data_api/cockpit/auth 闸
- 密码：`accounts.public_row(with_password=True)` 管理端
- 异常：`ExceptionOverview.vue` loadError + loadedOk
