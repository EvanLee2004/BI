# deploy/linux · Ubuntu **26.04** 部署资产（任务书50·D.6）

Linux 为主部署线；根目录 `*.bat` / schtasks 逻辑**保留不删**（Windows legacy）。  
Python：系统 `python3`（≥3.12）建 venv，见 `docs/madr/0010_python_version_ubuntu26.md`。

| 文件 | 作用 |
|------|------|
| `kanban.service` | systemd 单元模板（改 WorkingDirectory/User 后 install；uvicorn 建议仅回环） |
| `start_with_rollback.sh` | 看门狗：码 42 重启 / `.update_rollback` 回滚一次 / 5 次停下 |
| `register_schedule.sh` | 按合并配置 `schedule_times` 写用户 crontab 哨兵段 |
| `nginx-kanban.conf` | **生产标准**：nginx 发 `frontend/dist` + 反代 `127.0.0.1:8018`（MADR-0009） |

完整步骤见 `docs/Ubuntu部署手册.md`。真实 systemd/挂载/cron/nginx 在**部署机**验收；本机（macOS 开发）只做脚本桩测 + `bash -n`。
