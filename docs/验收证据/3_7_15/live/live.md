# 3.7.15 活体 / API 证据（本地 OFFLINE）

## L1 GET settings 无 password

- 驱动：`test_get_settings_no_password_key`
- 结果：200；JSON 无 `password` / `ledger_smb_password`；有 `ledger_smb_password_set`、`ledger_mount_root`

## L2 POST 结构化拼路径

- 驱动：`test_post_structured_updates_path_no_apply_without_user`
- 结果：`ledger_share_path` = `/mnt/kanban-ledger/team/台账.xlsx`；未调 apply

## L3 POST 改密触发 apply（mock）

- 驱动：`test_post_password_triggers_apply`
- 结果：`run_cifs_apply` 被调用一次；响应无密文

## L4 非管理员

- 驱动：`test_non_admin_403` → 401/403

## L5 脚本 tmpdir cred 0600

- 驱动：`test_script_writes_cred_0600` · `test_run_cifs_apply_via_python`
- 结果：cred mode 0600；改 username 保留旧 password

## L6 前端

- `npm run typecheck` OK；设置页含结构化字段与状态（`SettingsView.vue`）
