# Runbook：三张处方卡

## 0. 生产环境实况（2026-07-21 加固后 · 以机上为准）

| 项 | 值 |
|----|----|
| 部署机 | 公司 Ubuntu 26.04 台式机 `lee-ThinkCentre-M755e-D182`（内网，用户 `lee`） |
| 代码目录 | `/opt/kanban/看板正式程序`（git 仓库，HEAD=部署时 main） |
| 版本 | **2.2.0**（`stage66_debtfree`；金额分整数 / 增量重算 / VM 闸 / 抓数护栏） |
| 进程托管 | **systemd `kanban`**：User=**lee**（与数据目录属主一致，非模板占位 kanban）、enabled+active、Restart=always、StartLimit 5/120s；**沙箱** NoNewPrivileges + PrivateTmp + ProtectSystem=strict + ReadWritePaths（程序树/数据/备份/归档/`/run/user/1000`/`/home/lee`）；app 仅 `127.0.0.1:8018`、`KANBAN_SERVE_STATIC=0` |
| 对外入口 | **nginx** 站点 `kanban`（`:80` default_server）：`frontend/dist` + 反代 API；**server_tokens off**；安全头 nosniff / **`X-Frame-Options: SAMEORIGIN`**（勿 DENY——管理端「看」iframe 嵌 `/`）/ Referrer-Policy |
| 休眠 | `sleep`/`suspend`/`hibernate`/`hybrid-sleep` **target 已 mask**（不会睡死断服） |
| 每日更新 | **服务内 ScheduleLoop**（09:30 / 12:00 / 17:00 备忘；以机上 `schedule_times` 为准） |
| 其它 cron | healthcheck 每小时、备份 03:30；`kanban-schedule` 哨兵段**无** `run.py --scheduled` |
| 远程运维 | `ssh kanban-home`（家）/ `kanban-lan`（公司内网）；细节见 `公司电脑（部署机）/` |
| 人侧残留 | BIOS「来电自启」需进固件菜单（软件层做不到） |

> 连机：`ssh kanban-home`。sudo：交互 `ssh -t … sudo …`，或非交互管道 `sudo -S`（密码**不进仓库/文档**）。

## 1. 服务挂了

1. 看服务：`systemctl status kanban`（active=正常；failed 看 `journalctl -u kanban -n50`）
2. 看日志：`/opt/kanban/看板正式程序/数据/日志/`；healthcheck 输出 `数据/日志/healthcheck_cron.out`（勿写 `deploy/`，否则 git 判脏挡一键更新）
3. 健康：`curl -s http://127.0.0.1:8018/api/health | head` 或 `bash deploy/healthcheck.sh; echo $?`
4. 重启：`sudo systemctl restart kanban`（**别手动裸跑 run.py**，会和 systemd 抢端口）
5. 对外不通但 app 活：查 nginx —— `systemctl status nginx`、`sudo nginx -t`、`curl -s -o/dev/null -w '%{http_code}' http://localhost/login`
6. 若 503 数据未生成：管理端「更新数据」或机上 `sudo -u lee .venv/bin/python run.py`
7. **`built_at` 不走 / 到点页面不刷新**：先看服务日志是否有 `schedule_loop started times=…`；再看 `/api/refresh_status` 的 `refreshing` 是否卡住；确认管理端 `schedule_times` 与机上本地时区。**勿**指望 cron `run.py --scheduled` 更新页面内存（独立进程不写 `_state`）

## 2. 回滚版本

1. 业务 tag：`git tag -l 'stage5*'`
2. `sudo systemctl stop kanban` → `git -C /opt/kanban/看板正式程序 checkout <tag>` → 依赖变了 `pip install -r requirements.txt`
3. 恢复 `数据/看板.db` 与 `数据/看板账号.json` 备份（在 `数据/备份/`）
4. `sudo systemctl start kanban`，curl `/api/health` 绿/黄可接受
5. 一键更新（管理端按钮）走 `git pull --ff-only` + 依赖同步 + `.update_rollback` 自愈（铁律18）；坏版本看门狗自动回滚
6. 口径配置：管理端 UI/API 已下线；引擎默认直通。紧急改口径仅运维层（代码默认值 / DB，见 MADR-0012）
7. **账号密码（任务书64·P / MADR-0020）**：`看板账号.json` **明文为真相源**（管理员设置页可见可改）；写盘 `chmod 0o600`。保留：防爆破、改密踢会话、SESSION_TTL=12h、审计不记明文。生产若从未上过 63 哈希版则零迁移。

## 3. 备份恢复

1. 备份位置：`数据/备份/`（日更管道产出）
2. 恢复：拷贝 `看板.db` 到 `数据/`（先停服务）
3. 演练：`python tests/run_test.py tests/test_backup_restore.py`
4. 起服后 `/api/health` + 登录抽查 KPI

## 任务书64 运维要点（2.0.3）

- 备份：每日 `VACUUM INTO` 一致快照（失败回退 copy2 + 体检黄）；`数据/快照存档/` 与 `数据/年度归档/` **永久保留**，不进 30 天滚动清理。
- 跨年：智云 auto 首抓前自动归档上年四源 xlsx+库；台账 sheet 由亮晶新建当年名。
- 部署：nginx 安全头 + systemd `NoNewPrivileges`/`ProtectSystem=strict`/`PrivateTmp`；healthcheck 失败可飞书（未配 webhook 则只写 log）+ 磁盘余量检查。
- 密码：明文 + 文件 0600；**禁止猜生产口令**。
