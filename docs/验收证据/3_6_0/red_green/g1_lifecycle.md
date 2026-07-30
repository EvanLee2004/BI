# G1 红→绿摘要

## 根因（生产事故链）
- TERM/143 被看门狗计为崩溃 → 与 systemd Restart=always 双重重启
- health=200 单独判绿（旧 PID/commit 可假绿）
- 构建失败后 has_data=false → /admin 误进首次安装
- Excel 并发读 BadZip/CRC 无稳定复制

## 修复
- `reload_verify.verify_process_switch` 纯函数；reload_kanban.sh 调用
- start_with_rollback：0/130/143 预期运维退出，不累计 FAILS
- kanban.service：Restart=on-failure
- install_state + resolve_admin_entry：bootstrap 仅 fresh
- LKG 快照：构建失败 fail-closed 加载
- excel_stable.stable_copy / db_backup 带 version+commit manifest

## 测试
`python tests/run_test.py tests/test_g1_lifecycle_3_6_0.py` → 18 OK
