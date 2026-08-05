# Runbook：三张处方卡

## 0. 生产环境实况（2026-08-05 · 以机上 `git rev-parse HEAD` + 仓内 `VERSION` + 项目 `progress.md` 顶部为准，勿钉死本表旧号）

| 项 | 值 |
|----|----|
| 部署机 | 公司 Ubuntu 26.04 台式机 `lee-ThinkCentre-M755e-D182`（内网，用户 `lee`） |
| 代码目录 | `/opt/kanban/看板正式程序`（git 仓库，HEAD=部署时 main） |
| 版本 | **以机上 `cat VERSION` + `git rev-parse --short HEAD` 为准**（文档收口时产品线 **3.7.15** · tip 见项目 `progress.md`）。人可见：首屏六段、重点客户、管理端设置「台账共享 CIFS 可配置」、审计加固（3.7.14）、候选预热发版、强制备份、API `/api/v1/*`、仅 `kanban_sid`。飞书 webhook 已废止。 |
| 进程托管 | **systemd `kanban`**：**单 worker** User=**lee**、enabled+active、**Restart=on-failure** + StartLimit 5/120s；沙箱 NoNewPrivileges + PrivateTmp + ProtectSystem=strict + **ReadWritePaths 含 `/mnt/kanban-ledger`**；主 app `127.0.0.1:8018`、`KANBAN_SERVE_STATIC=0`；发版可选 **:8019 候选预热** 后切主。**多 worker / Redis 未支持** |
| 对外入口 | **nginx** 站点 `kanban`（`:80` default_server）：`frontend/dist` + 反代 API；**`location = /` 必须反代后端**（2.4.3，禁 try_files index 抢根路径）；**server_tokens off**；安全头 nosniff / **`X-Frame-Options: SAMEORIGIN`** / Referrer-Policy |
| 用户入口口径 | **首选（2026-07-30 海鹏）**：`http://dash.besteasy.com:8001`（**内外网统一**；**必须带 `:8001`**）。过渡期旧链：内网 `http://192.168.30.46`；外网 `http://101.254.102.94:8001`。用自己账号登录即可；**无**单独管理员登录 URL；管理端路径 `/admin` |
| 会话 | 浏览器 cookie **仅 `kanban_sid`**。**上机后须重登**。探活 `GET /api/v1/health`；刷新状态 `GET /api/v1/admin/refresh_status` |
| 休眠 | `sleep`/`suspend`/`hibernate`/`hybrid-sleep` **target 已 mask** |
| 每日更新 | **服务内 ScheduleLoop**（以机上 `schedule_times` 为准） |
| 其它 cron | healthcheck 每小时、备份 03:30；`kanban-schedule` 哨兵段**无** `run.py --scheduled` |
| 远程运维 | `ssh kanban-home`（家）/ `kanban-lan`（公司内网） |
| 人侧残留 | BIOS「来电自启」需进固件菜单 |

> 连机（在家）：`ssh kanban-home`。若 `Permission denied` 但跳板 `ping` 通 → **先钥匙不是穿透坏了**：见 `公司电脑（部署机）/Agent.md`「连前必先解锁钥匙」与 **「双跳都用 hostup」（2026-08-01）**；总手册 `…/20260717_家中远程通路实测与复用手册.md` §0.0.1。  
> sudo：交互 `ssh -t … sudo …`，或非交互管道 `sudo -S`（密码**不进仓库/git**）。

## 0.2 共享盘 / BESTEASY / CIFS（3.7.15 现网）

生产收单台账依赖公司内网共享。**现网（2026-08-05）已切 CIFS**，不再依赖 gvfs 会话。

| 形态 | 特征 | 现网 |
|------|------|------|
| **CIFS/fstab（现行）** | `/mnt/kanban-ledger` + `//服务器/共享` + cred 0600 | **是** · 开机 automount |
| **网络可达** | Wi‑Fi **BESTEASY** · `ping` 服务器 · TCP **445** | 前置条件 |
| **gvfs / gio（已退役）** | `/run/user/…/gvfs/smb-share:…` | 仅历史；重启会掉，勿再当唯一依赖 |

**默认路径形态**（真实子路径在机上 `本地配置.json`，**不进 git**）：

```text
/mnt/kanban-ledger/<相对路径>/收单台账.xlsx
```

**3.7.15 管理端 B 方案**：设置页「收单台账 · 公司共享盘」可改 **服务器 / 共享名 / 相对路径 / 账号**；密码**留空=不改**、永不回显。非密写入 `数据/本地配置.json` 并拼装 `ledger_share_path`；改账号/密码走 **`/usr/local/sbin/kanban-cifs-apply`**（仓内 `deploy/linux/kanban-cifs-apply.sh` + `sudoers.d-kanban-cifs`）更新 `/etc/kanban/cifs-ledger.cred` 并 remount。**禁止**把真实密码写进 git。

**排障速查（台账红 / local_fallback）**：

1. `nmcli -t -f active,ssid dev wifi` 是否 **BESTEASY**  
2. `ping` 配置中的服务器；445 是否通  
3. `findmnt /mnt/kanban-ledger` 是否 cifs  
4. `test -f "$(jq -r .ledger_share_path 数据/本地配置.json)"`  
5. 管理端设置页 `ledger_path_exists` / 状态灯
3. `findmnt /mnt/kanban-ledger` 是否 **cifs**  
4. 管理端：结构化字段 + `ledger_path_exists` / `ledger_mount_ok` / `ledger_smb_password_set`  
5. **禁止**擅自 umount 现网唯一挂载  
6. 安装 apply（一次）：  
   ```bash
   sudo install -m755 deploy/linux/kanban-cifs-apply.sh /usr/local/sbin/kanban-cifs-apply
   sudo mkdir -p /etc/kanban && sudo chmod 755 /etc/kanban
   sudo cp deploy/linux/sudoers.d-kanban-cifs /etc/sudoers.d/kanban-cifs
   sudo chmod 440 /etc/sudoers.d/kanban-cifs && sudo visudo -cf /etc/sudoers.d/kanban-cifs
   # unit：NoNewPrivileges=false + KANBAN_CIFS_USE_SUDO=1 + APPLY_SCRIPT=/usr/local/sbin/...
   sudo cp deploy/linux/kanban.service /etc/systemd/system/kanban.service
   sudo systemctl daemon-reload && sudo systemctl restart kanban
   ```

## 1. 服务挂了

1. 看服务：`systemctl status kanban`（active=正常；failed 看 `journalctl -u kanban -n50`）
2. 看日志：`/opt/kanban/看板正式程序/数据/日志/`；healthcheck 输出 `数据/日志/healthcheck_cron.out`（勿写 `deploy/`，否则 git 判脏挡一键更新）
3. 健康：`curl -s http://127.0.0.1:8018/api/v1/health | head` 或 `bash deploy/healthcheck.sh; echo $?`
4. 重启：`sudo systemctl restart kanban`（**别手动裸跑 run.py**，会和 systemd 抢端口）
5. 对外不通但 app 活：查 nginx —— `systemctl status nginx`、`sudo nginx -t`、`curl -s -o/dev/null -w '%{http_code}' http://localhost/login`
6. 若 503 数据未生成：管理端「更新数据」或机上 `sudo -u lee .venv/bin/python run.py`
7. **`built_at` 不走 / 到点页面不刷新**：先看服务日志是否有 `schedule_loop started times=…`；再看 `/api/v1/admin/refresh_status` 的 `refreshing` 是否卡住；确认管理端 `schedule_times` 与机上本地时区。**勿**指望 cron `run.py --scheduled` 更新页面内存（独立进程不写 `_state`）
8. **业务线账号「第一次能进、再开根地址进不去」**（2.4.3）：多半是 nginx 根路径未反代。核对 `location = /` 含 `proxy_pass`、**无** `try_files /index.html`；仓库 conf 变更后必须：
   ```bash
   sudo cp /opt/kanban/看板正式程序/deploy/linux/nginx-kanban.conf /etc/nginx/sites-available/kanban
   # sites-enabled 若已是 symlink 到 available 则无需再 ln
   sudo nginx -t && sudo systemctl reload nginx
   ```
   **禁止**只 `git pull` 不 reload nginx。发版后管理端 chunk 404：用户强制刷新浏览器（Ctrl/Cmd+Shift+R）。
9. **台账/共享盘**：见 §0.2（BESTEASY · gvfs vs CIFS）；勿 umount 现网。

## 0.1 发版上机铁律（3.7.0 · 备份 + 门闸）

**推荐标准入口**（3.7.3+，候选预热；承接 3.7.0 备份门闸）：

```bash
cd /opt/kanban/看板正式程序
# 备份 → pull → 旁路 :8019 预热 → 通过后 reload 主 :8018 → 门闸 SUCCESS
bash deploy/linux/publish_kanban.sh --pull
# 近零断流（须 conf 已 include kanban_upstream.inc，且 sudo nginx）：
# bash deploy/linux/publish_kanban.sh --pull --nginx-cutover
# 退回旧半原子（无候选）：
# bash deploy/linux/publish_kanban.sh --pull --no-candidate
```

| 门闸 | 要求 |
|------|------|
| 备份 | `数据/备份/看板_pre_publish_*.db` + manifest；**无备份退出非 0** |
| 候选预热 | :8019 health 200 + runtime version/commit/pid 对齐磁盘；失败则主进程不动并 reset pull |
| reload | 旧 PID 消失 + 新 PID + health 200 + runtime 对齐磁盘 |
| 成功 | `declare_publish_success`：backup + version + commit + pid + health |

**诚实**：单机 SQLite，非双机蓝绿；默认仍有主进程 restart 短窗口。`--nginx-cutover` 用 upstream 短暂指候选，缩短用户可见断流。

设计：`docs/madr/MADR-0030_…` · `docs/madr/MADR-0031_候选预热与nginx切流_3_7_3.md`。

**systemd 对齐**（若 `Restart` 不是 on-failure）：

```bash
bash deploy/linux/install_systemd_unit.sh   # 需 sudo
systemctl show kanban -p Restart            # 期望 on-failure
```


代码 `git pull` **不会**自动装载 nginx conf。每次 conf 或维护页相关发版：

```bash
cd /opt/kanban/看板正式程序 && git pull --ff-only origin main
sudo cp deploy/linux/nginx-kanban.conf /etc/nginx/sites-available/kanban
sudo nginx -t && sudo systemctl reload nginx
systemctl is-active kanban
```

**禁止**只 pull 就勾「已上机」。**禁止**无业务库备份就 reload 宣称发版成功。

### 0.1.1 S-13 · CSRF 与 `:8001` Host 端口（仓库已改；上机须 RELEASER）

**现象**：`http://dash.besteasy.com:8001/admin` 点「更新数据」→ `403 CSRF blocked: origin_mismatch`；刷新未启动。

**根因**：nginx `proxy_set_header Host $host` **丢弃非默认端口**；浏览器 Origin 含 `:8001`，后端 Host 无端口 → 误判跨站。

**仓库侧**（代码/模板已具备，**不等于生产已装载**）：
- 全部反代 location：`Host $http_host` + `X-Forwarded-Host $http_host`
- 后端 CSRF：scheme + hostname + effective port；**仅 loopback 客户端**信任 `X-Forwarded-*`
- 契约测：`tests/test_s13_csrf_proxy_host_port.py`

**RELEASER 上机 checklist**（须 fresh 证据，本文不宣称生产已修复）：
```bash
# 1) 装载 conf 并校验
sudo cp /opt/kanban/看板正式程序/deploy/linux/nginx-kanban.conf /etc/nginx/sites-available/kanban
sudo nginx -t && sudo systemctl reload nginx
# 2) 确认无残留 $host
sudo grep -n 'proxy_set_header Host' /etc/nginx/sites-available/kanban
# 期望每行均为 $http_host，且有 X-Forwarded-Host
# 3) smoke（正式入口，登录后管理端）
#    - http://dash.besteasy.com:8001/admin/settings →「更新数据」应非 403
#    - 内网 http://192.168.30.46 写路径仍可用
# 4) 应用 reload 后 loopback health 仍 200（匿名不要求暴露 commit）
```

## 0.2 维护模式开关（2.7.3）

| 操作 | 命令 |
|------|------|
| 打开维护（用户见「系统正在更新中」） | `bash deploy/linux/maintenance_on.sh` 或 `manual`/`update`/`boot` |
| 关闭维护 | `bash deploy/linux/maintenance_off.sh` |
| 标志文件 | `数据/maintenance.flag`（已 gitignore；超时默认 10 分钟强制关 + 写 `数据/日志/告警.log`） |

- 一键更新成功会在重启前自动 `turn_on(update)`；看门狗每次启动 `run.py --serve` 前 `turn_on(boot)`；`serve()` 首次构建成功后在 listen 前 `turn_off`。
- 构建失败保持 on，依赖超时兜底。
- **不要**只靠内存记维护态；**不要**对 `/api/` 用 nginx `proxy_intercept_errors` 把 JSON 换成 HTML。
- 健康检查仍直连 `127.0.0.1:8018` + `/api/v1/health`（不走 :80 维护页）。

## 2. 回滚版本

1. 业务 tag：`git tag -l 'stage5*'`
2. `sudo systemctl stop kanban` → `git -C /opt/kanban/看板正式程序 checkout <tag>` → 依赖变了 `pip install -r requirements.txt`
3. 恢复 `数据/看板.db` 与 `数据/看板账号.json` 备份（在 `数据/备份/`）
4. `sudo systemctl start kanban`，curl `/api/v1/health` 绿/黄可接受
5. 一键更新（管理端按钮）走 `git pull --ff-only` + 依赖同步 + `.update_rollback` 自愈（铁律18）；坏版本看门狗自动回滚
6. 口径配置：管理端 UI/API 已下线；引擎默认直通。紧急改口径仅运维层（代码默认值 / DB，见 MADR-0012）
7. **账号密码（任务书64·P / MADR-0020）**：`看板账号.json` **明文为真相源**（管理员设置页可见可改）；写盘 `chmod 0o600`。保留：防爆破、改密踢会话、SESSION_TTL=12h、审计不记明文。生产若从未上过 63 哈希版则零迁移。

## 3. 备份恢复

1. 备份位置：`数据/备份/`（日更管道产出）
2. 恢复：拷贝 `看板.db` 到 `数据/`（先停服务）
3. 演练：`python tests/run_test.py tests/test_backup_restore.py`
4. 起服后 `/api/v1/health` + 登录抽查 KPI

### 3.1 演练证据（2026-07-26 · 2.6.4 上机）

| 项 | 回显 |
|----|------|
| 自动化 | 本机 `pytest tests/test_backup_restore.py` → **2 passed**（EXIT 0） |
| 生产上机前备份 | `数据/备份/看板_pre_2.6.4_20260726_001852.db` size **4325376** |
| 上机后表级对照 | std 五表与全部 `manual_*` / `adj_调整记录` **相对备份 delta=0**；仅 `meta_运行日志` +1（冷启动写日志） |
| 对照落盘 | `方案与文档/…/3_测试/20260726_2.6.4复查证据/deploy/table_counts_vs_backup.txt` |

> 临时目录灾难演练（删主库→restore）以 `test_backup_restore` 为准；**禁止**在生产 `数据/` 上做破坏性演练。

## 任务书64 运维要点（2.0.3）

- 备份：每日 `VACUUM INTO` 一致快照（失败回退 copy2 + 体检黄）；`数据/快照存档/` 与 `数据/年度归档/` **永久保留**，不进 30 天滚动清理。
- 跨年：智云 auto 首抓前自动归档上年四源 xlsx+库；台账 sheet 由亮晶新建当年名。
- 部署：nginx 安全头 + systemd `NoNewPrivileges`/`ProtectSystem=strict`/`PrivateTmp`；healthcheck 失败**只写本地 log**（飞书外发已删除）+ 磁盘余量检查。
- 密码：明文 + 文件 0600；**禁止猜生产口令**。

## 无 sudo 的代码热加载（lee · 3.1.0）

公司内网 `lee@192.168.30.46` 上，发版后若无交互 sudo：

```bash
cd /opt/kanban/看板正式程序
git pull --ff-only origin main
bash deploy/linux/reload_kanban.sh
# 等待 health 200（冷启动可能数分钟）
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8018/api/v1/health
cat VERSION
```

脚本优先 `sudo -n systemctl restart kanban`；失败则结束 `run.py --serve`，由看门狗/systemd 拉起。


## 3.5.0 reload 成功判据（2026-07-30）

**禁止**只凭 `health=200` + 磁盘 `VERSION` 宣布成功（3.4.3 曾假绿：旧 serve 仍 200、摘要空）。

成功必须同时：

1. 重载前记录 serve PID；重载后旧 PID 消失、新 PID 出现  
2. `http://127.0.0.1:8018/api/v1/health` = 200  
3. health.metrics 含 `version`（=磁盘 VERSION）、`git_commit`（=目标 HEAD）、`pid`  
4. （上线后）重点客户 VM 含 `amount_axis` / 月点 `value_wan`  

脚本：`deploy/linux/reload_kanban.sh`。失败保持/恢复维护态，按本 Runbook 回滚，禁止生产现场改码。

