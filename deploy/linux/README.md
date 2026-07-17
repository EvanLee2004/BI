# deploy/linux · Ubuntu **26.04** 部署资产（任务书50·D.6）

Linux 为**唯一**部署线（任务书54：Windows `.bat` / schtasks 已全线退役）。  
Python：系统 `python3`（≥3.12）建 venv，见 `docs/madr/0010_python_version_ubuntu26.md`。  
**不**在脚本里写死 `python3.12` 或 deadsnakes 路径。

| 文件 | 作用 | 26.04 审查（2026-07-17） |
|------|------|---------------------------|
| `kanban.service` | systemd 单元（改 WorkingDirectory/User 后 install；生产仅回环 8018） | systemd 语法通用；注释标 26.04 |
| `start_with_rollback.sh` | 看门狗：码 42 重启 / `.update_rollback` 回滚一次 / 5 次停下 | 解释器=` .venv/bin/python` 否则 `python3` |
| `register_schedule.sh` | 按合并配置 `schedule_times` 写用户 crontab 哨兵段 | cron 语法通用；同上 python 解析 |
| `nginx-kanban.conf` | **生产标准**：nginx 发 `frontend/dist` + 反代 `127.0.0.1:8018` | nginx 语法通用；root 指 dist |
| `README.md` | 本文件 | 部署目标与 MADR 指针 |

完整步骤见 `docs/Ubuntu部署手册.md`。真实 systemd/挂载/cron/nginx 在**部署机**验收；本机（macOS 开发）只做脚本桩测 + `bash -n`。

### Python 路径约定（五件套一致）

```bash
# 部署机装依赖（手册 §2~3）
python3 --version          # 须 ≥ 3.12
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Playwright 系统库勿抄 22.04 包名：
.venv/bin/playwright install chromium
sudo .venv/bin/playwright install-deps chromium
```
