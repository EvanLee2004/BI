# offline_seed · 3.6.0 离线门禁脱敏数据源

合成业务表（示例客户/员工命名），**不含生产真实客户、金额、口令、内网路径**。

生成/物化：

```bash
python scripts/materialize_offline_fixtures.py
```

物化目标：仓库根 `_golden_data/`（gitignore）。`KANBAN_OFFLINE=1` 时 `tests/run_verify.sh` 会自动物化并设 `KANBAN_PROFILE=dev`。

两次物化后同名业务文件哈希一致（确定性拷贝）。
