# deploy/linux · Ubuntu 22.04 部署资产

Linux 为主部署线；根目录 `*.bat` / schtasks 逻辑**保留不删**（Windows legacy）。

| 文件 | 作用 |
|------|------|
| `kanban.service` | systemd 单元模板（改 WorkingDirectory/User 后 install） |
| `start_with_rollback.sh` | 看门狗：码 42 重启 / `.update_rollback` 回滚一次 / 5 次停下 |
| `register_schedule.sh` | 按合并配置 `schedule_times` 写用户 crontab 哨兵段 |

完整步骤见 `docs/Ubuntu部署手册.md`。真实 systemd/挂载/cron 在**部署机**验收；本机（macOS 开发）只做脚本桩测 + `bash -n`。
