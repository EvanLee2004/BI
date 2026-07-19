# Runbook：三张处方卡

## 0. 生产环境实况（2026-07-20 首次上线·SSH 实核）

| 项 | 值 |
|----|----|
| 部署机 | 公司 Ubuntu 26.04 台式机 `lee-ThinkCentre-M755e-D182`（内网，用户 `lee`） |
| 代码目录 | `/opt/kanban/看板正式程序`（git 仓库，HEAD=部署时 main） |
| 版本 | 2.0.0-rc12（`stage58_ui` 线） |
| 进程托管 | **systemd 单元 `kanban`**（active + enabled，Restart=always，重启/崩溃/重机自愈）；app 只绑 `127.0.0.1:8018` |
| 对外入口 | **nginx** 站点 `kanban`（`:80` default_server，发 `frontend/dist` 静态 + `proxy_pass` API→127.0.0.1:8018）；内网 `http://<机内网IP>/` |
| 定时 | cron：每日更新 09:30、healthcheck 每小时、备份 03:30 |
| 远程运维 | 家里 Linux 跳板 + Tailscale：`ssh kanban-home`（细节见 `公司电脑（部署机）/`） |

> 连机：本机 `ssh kanban-home`。sudo 操作需 TTY（`ssh -t kanban-home` 或机上 opencode 代跑）。

## 1. 服务挂了

1. 看服务：`systemctl status kanban`（active=正常；failed 看 `journalctl -u kanban -n50`）
2. 看日志：`/opt/kanban/看板正式程序/数据/日志/`；healthcheck 输出 `deploy/healthcheck_cron.out`
3. 健康：`curl -s http://127.0.0.1:8018/api/health | head` 或 `bash deploy/healthcheck.sh; echo $?`
4. 重启：`sudo systemctl restart kanban`（**别手动裸跑 run.py**，会和 systemd 抢端口）
5. 对外不通但 app 活：查 nginx —— `systemctl status nginx`、`sudo nginx -t`、`curl -s -o/dev/null -w '%{http_code}' http://localhost/login`
6. 若 503 数据未生成：管理端「更新数据」或机上 `sudo -u lee .venv/bin/python run.py`

## 2. 回滚版本

1. 业务 tag：`git tag -l 'stage5*'`
2. `sudo systemctl stop kanban` → `git -C /opt/kanban/看板正式程序 checkout <tag>` → 依赖变了 `pip install -r requirements.txt`
3. 恢复 `数据/看板.db` 与 `数据/看板账号.json` 备份（在 `数据/备份/`）
4. `sudo systemctl start kanban`，curl `/api/health` 绿/黄可接受
5. 一键更新（管理端按钮）走 `git pull --ff-only` + 依赖同步 + `.update_rollback` 自愈（铁律18）；坏版本看门狗自动回滚
6. 口径配置：管理端 UI/API 已下线；引擎默认直通。紧急改口径仅运维层（代码默认值 / DB，见 MADR-0012）

## 3. 备份恢复

1. 备份位置：`数据/备份/`（日更管道产出）
2. 恢复：拷贝 `看板.db` 到 `数据/`（先停服务）
3. 演练：`python tests/run_test.py tests/test_backup_restore.py`
4. 起服后 `/api/health` + 登录抽查 KPI
