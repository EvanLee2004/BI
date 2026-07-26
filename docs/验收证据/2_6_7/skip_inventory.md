# Skip 清单 · 2.6.7 A-5

> 扫描日：2026-07-26 · 源码静态位点（装饰器 + `self.skipTest` / `pytest.skip`）  
> **结论**：共 **29** 处；均依赖外部/本机可选资源。本机 `run_verify` 已覆盖路径均真跑；下列 skip 保留理由充分，**不删**。

| 桶 | 数量 | 是否 CI/本机 run_verify 真跑 | 理由 |
|----|------|------------------------------|------|
| live_browser_or_port | 6 | 否（需 8018 + playwright） | 可选 live 巡检，不进日常门禁 |
| fixture_golden_db | 6 | 部分（有 golden 才跑） | 缺 golden 时 skip |
| node_toolchain | 4 | 有 node_modules/tsx 才跑 | 工具链可选 |
| frontend_dist | 3 | dist 构建后才跑 | 构建产物可选 |
| local_secrets_or_docs | 3 | 本机有账号/文档才跑 | 不上云凭据 |
| deploy_host | 2 | 仅部署机 | nginx/linux 环境 |
| git_binary | 1 | 有 git 才跑 | `@skipUnless(git)` |
| other | 4 | 条件性 | ranking 空数据、e2e BU 账号等 |

## 明细

| 文件:行 | 类型 | 消息摘要 | 保留？ |
|---------|------|----------|--------|
| test_backup_restore.py:23,82 | runtime | 无备份/golden db | 是 |
| test_e2e_auth_isolation_2_6_4.py:171 | runtime | no BU account | 是 |
| test_expense_drawer.py:83 | runtime | dist 未构建 | 是 |
| test_linux_deploy.py:39 | runtime | 无 bash | 是 |
| test_schedule.py:89 | runtime | 需非 linux 测 no-op | 是 |
| test_task43_nginx_mode.py:114 | runtime | 本机无 nginx | 是 |
| test_task51_frontend_types.py:51 | runtime | 无 node_modules | 是 |
| test_task52_fixes.py:173,189,211,257 | runtime | 账号/docs/golden | 是 |
| test_task54p11_r02_period.py:104,109 | runtime | 8018/playwright | 是 |
| test_task54p11_r03_overlay.py:52,56 | runtime | 8018/playwright | 是 |
| test_task54p14_live_optional.py:134,138 | runtime | 8018/playwright | 是 |
| test_task54p14_r20_no_double_wan.py:60,112,149 | runtime | golden/BU 配置 | 是 |
| test_task54p14_r21_r26.py:135,191,249 | runtime | golden/tsx | 是 |
| test_task_2_4_3_entry.py:62 | runtime | 无 node/esbuild | 是 |
| test_task_2_6_1_rankings_full_and_scroll.py:221 | runtime | fixture 无排名数据 | 是 |
| test_task_2_6_3_batch_d.py:27 | runtime | no frontend/dist | 是 |
| test_ui_sales_customer_order_and_ro_filter.py:175 | runtime | dist 未构建 | 是 |
| test_update.py:52 | decorator | 无 git | 是 |

`run_verify.sh` 末尾打印：`[skip] 测试源码 skip 位点数=N`。
