# 甲骨易智能经营罗盘 · Ubuntu 26.04 从零部署手册

> **版本对齐（2026-08-03）**：产品以根目录 **`VERSION`（当前 3.7.7）** + 项目 `progress.md` 顶部为准：统一 `/login`、会话仅 **`kanban_sid`**、金额 int 分、Vue 单轨、nginx 根路径必须反代后端；发版见 `publish_kanban.sh`（强制备份 + 可选 :8019 候选预热）。日常处方见 `Runbook.md` §0。

> **✅ 已首次上线（2026-07-20，SSH 实核）**：本手册照做已在公司机跑通生产态——`/opt/kanban/看板正式程序` + systemd `kanban` + nginx `kanban`:80 + 三套 cron + 真实数据。**日常运维处方**（挂了怎么办/回滚/更新）看 `Runbook.md` §0，本手册管"从零装"。  
> **适用**：部署机从 Windows 迁到 **Ubuntu 26.04 LTS**（明昊 2026-07-17 拍板；22.04 旧稿作废）。  
> **产品目录约定**：`/opt/kanban/看板正式程序`（也可放 home，权衡见 §1）。  
> **形态**：**生产标准** = nginx:80 发 `frontend/dist` + 反代 `127.0.0.1:8018`（见 §nginx / MADR-0009）；uvicorn 仅回环。systemd 常驻 + cron 定时 + 智云/台账 CIFS。简易模式单进程 `--serve` 仅开发/预览。  
> **修订**：2026-07-17 任务书50·D.6（22.04→26.04；系统 python3 建 venv）。原 2026-07-16 任务书40/42 基础仍有效。  
> **Windows 手册与 `.bat` 已于任务书54 删除**（部署机=Ubuntu 唯一线）。

**不做**：Docker / K8s（现阶段裸 systemd 最简，见 `docs/madr/`）。

---

## 0. 你需要准备什么

| 项 | 说明 |
|----|------|
| 机器 | 财务部 Ubuntu 26.04，内网，建议常开 |
| 权限 | sudo（装包、fstab、systemd、ufw） |
| 账号 | 智云全量只读号；看板管理员口令；**CIFS 共享盘账号密码（手填，不进 git）** |
| 网络 | 智云内网、收单台账 SMB 共享（**具体 IP/路径不进 git，见部署机运维笔记**）、Gitee（或 GitHub） |
| 代码 | **git clone**（一键更新才可用） |

---

## 1. 目录与系统用户

推荐：

```bash
sudo mkdir -p /opt/kanban
sudo useradd -r -m -d /opt/kanban -s /bin/bash kanban 2>/dev/null || true
sudo chown kanban:kanban /opt/kanban
```

- 放 `/opt/kanban`：与系统服务惯例一致，备份清晰。  
- 放 `$HOME/kanban`：无需单独用户，但 systemd `User=` 要改成你的登录用户。

下文以 `/opt/kanban/看板正式程序` + 用户 `kanban` 为例。

```bash
sudo -u kanban -i
export LANG=C.UTF-8 LC_ALL=C.UTF-8
```

---

## 2. 基础包 + Python（系统 python3 ≥ 3.12）

Ubuntu **26.04** 系统 `python3` 已 ≥ 3.12，**直接用系统解释器建 venv**（MADR：`docs/madr/0010_python_version_ubuntu26.md`）。  
**不要**默认装 deadsnakes（旧 22.04 路径已 SUPERSEDED，见 `0002_python_version_ubuntu22.md`）。

```bash
sudo apt update
sudo apt install -y git curl ca-certificates build-essential \
  cifs-utils fonts-noto-cjk \
  python3 python3-venv python3-dev \
  nginx

# 判定：必须 ≥ 3.12
python3 --version   # 例：Python 3.12+（系统 python3）.x / 3.13.x

# Playwright 系统库：不在手册硬编码发行版包名（24.04+ 多为 t64 后缀）
# 装完 venv + requirements 后执行：
#   .venv/bin/playwright install chromium
#   sudo .venv/bin/playwright install-deps chromium   # 缺库时
```

**中文字体 `fonts-noto-cjk` 必装**：否则导出 PNG 中文变豆腐块。

**导出 PNG / Playwright**（可选，管理端截图导出时）：

```bash
.venv/bin/playwright install chromium
# 缺系统库时（推荐，自适应发行版）：
sudo .venv/bin/playwright install-deps chromium
```

---

---

## 3. clone 代码 + venv + 依赖

```bash
cd /opt/kanban
# 推荐 Gitee 镜像；按实际仓库地址改
git clone <仓库URL> 看板正式程序
cd 看板正式程序

# 必须用 ≥3.12 的 python3 建 venv（fastapi 0.139+ 要求；系统 python3 --version 先确认）
python3 -m venv .venv
.venv/bin/pip install -U pip
# 清华镜像（与 config 默认 pip_mirror 一致；也可用官方源）
.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 开发机/跑全量验证时另装测试依赖（httpx 等，生产运行不必装）：
#   .venv/bin/pip install -r requirements-dev.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 无智云/共享盘的预演（开发机或首次空跑）：
#   export KANBAN_OFFLINE=1
#   准备 数据/ 下进料文件（可先拷 _golden_data/ 合成样例，正式环境再换真源）
#   .venv/bin/python run.py
```

---

## 4. 收单台账 CIFS 挂载（最高风险项 · 3.7.15 现网）

> **真实共享 IP、共享名、子目录、账号密码不写进本仓库（GitHub）**。  
> 现网：**CIFS** `/mnt/kanban-ledger`（**非 gvfs**）。细则见 `docs/运维_收单台账CIFS_fstab步骤单_只写不执行.md` 与 `docs/Runbook.md` §0.2。

共享源：`//【文件服务器】/【共享名】` → 固定挂到 **`/mnt/kanban-ledger`**。

```bash
sudo apt-get install -y cifs-utils
sudo mkdir -p /mnt/kanban-ledger /etc/kanban
sudo tee /etc/kanban/cifs-ledger.cred >/dev/null <<'EOF'
username=【部署时手填】
password=【部署时手填】
EOF
sudo chmod 600 /etc/kanban/cifs-ledger.cred
# 凭证绝不进 git

# fstab（_netdev / automount；【】处换成机上真实值）
echo '//【文件服务器】/【共享名】 /mnt/kanban-ledger cifs credentials=/etc/kanban/cifs-ledger.cred,uid=lee,gid=lee,iocharset=utf8,file_mode=0644,dir_mode=0755,nofail,x-systemd.automount,_netdev 0 0' | sudo tee -a /etc/fstab

sudo mount -a
findmnt /mnt/kanban-ledger
# 安装管理端改密用的受控脚本
sudo install -m 755 deploy/linux/kanban-cifs-apply.sh /usr/local/sbin/kanban-cifs-apply
sudo cp deploy/linux/sudoers.d-kanban-cifs /etc/sudoers.d/kanban-cifs
sudo chmod 440 /etc/sudoers.d/kanban-cifs && sudo visudo -cf /etc/sudoers.d/kanban-cifs
```

**看板配置（3.7.15）**：管理端「设置 → 收单台账 · 公司共享盘」填 **服务器 / 共享名 / 相对路径 / 账号**（密码只写不回显），**只落** `数据/本地配置.json`（gitignore）并拼装 `ledger_share_path`。

```text
# 路径形态（占位）
/mnt/kanban-ledger/【相对路径】/收单台账.xlsx
```

`config.json` 出厂 `ledger_share_path` **留空**——真实路径不得写进 git。

**挂不上时看板表现**：`fetch_ledger` 走上次本地副本 + 体检黄，管道不中断。自查：

```bash
findmnt /mnt/kanban-ledger
test -f /mnt/kanban-ledger/…/收单台账.xlsx
journalctl -u kanban -n 50 --no-pager | grep -i 台账
# Wi-Fi 须 BESTEASY
```

---

## 5. 数据文件清单

`数据/` 需要（文件名固定，见 `数据/README.md`）：

- `项目明细.xlsx` `下单.xlsx` `回款记录.xlsx` `内部译员.xlsx` `收单台账.xlsx` `手填与调整.xlsx`
- 账号：`看板账号.json`、管理员密钥等按样例生成（**真实口令不进 git**）

首次可先用测试数据跑通，再换正式文件。

```bash
cd /opt/kanban/看板正式程序
KANBAN_OFFLINE=1 .venv/bin/python run.py   # 无智云时离线重算
```

---

## 6. systemd 安装启用

```bash
cd /opt/kanban/看板正式程序
sudo cp deploy/linux/kanban.service /etc/systemd/system/kanban.service
# 若路径/用户不同，编辑 Unit 里 WorkingDirectory、User、ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now kanban
systemctl status kanban --no-pager
journalctl -u kanban -n 100 --no-pager
```

**看门狗语义**（`deploy/linux/start_with_rollback.sh`）：

| 退出码 / 状态 | 行为 |
|---------------|------|
| 42 | 一键更新后重启（新代码） |
| 非 42 + `.update_rollback` 存在 | `git reset --hard <标记>` 一次再起 |
| 连续异常 ≥5 | 脚本退出；配合 `StartLimitBurst` 停下报警 |

服务正常跑约 20s 后进程内会清回滚标记（`server.serve`，平台无关）。

---

## 7. 每日更新与 cron 哨兵（任务书60）

**页面/API 数据的每日到点刷新**由服务进程内 **ScheduleLoop** 完成（`python run.py --serve` / systemd `kanban` 启动后自动起 daemon）。  
`bash deploy/linux/register_schedule.sh` 只同步 `kanban-schedule` 哨兵段：**不再**注册 `run.py --scheduled`；上线/升级后重跑一次用于**清掉旧刷新 cron 行**。备份与 healthcheck 等其它 cron 不在本段内。

```bash
cd /opt/kanban/看板正式程序
bash deploy/linux/register_schedule.sh
crontab -l | sed -n '/BEGIN kanban-schedule/,/END kanban-schedule/p'
# 期望：段内仅注释，无 run.py --scheduled 命令行
```

管理端改「自动更新时间」保存时，Linux 上会 best-effort 重写哨兵段（清旧行）；时间点热读进 ScheduleLoop，无需重启即可按新时间触发。  
`run.py --scheduled` 仍保留为 CLI 离线批跑，**不**刷新 `--serve` 内存。

---

## 8. 防火墙放行 8018

```bash
sudo ufw allow 8018/tcp comment 'kanban'
sudo ufw status
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8018/
# 期望 200 或 302（登录跳转）
```

---

## 9. 三账号验收（摘要）

| 角色 | 入口 | 检查 |
|------|------|------|
| 管理员 | `/admin` | 登录、重算、设置、数据调整全列 |
| 整体 | `/` | 五板块、费用明细白名单列、导出 |
| BU | `/bu/{token}` | 仅本 BU、费用明细无他 BU |

默认端口 **8018**。账号名见部署机 `数据/看板账号.json`（不写密码进文档）。

---

## 10. 一键更新（Linux）

护栏：`updater.apply_update` → `git pull --ff-only` → 依赖变则 pip → 写 `.update_rollback` → 维护 on → 退出码 **42**。

- systemd `Restart=always` + 包装脚本处理 42；  
- 2.7.3：更新/重启窗口用户端显示「系统正在更新中」；就绪后自动关维护；  
- 坏版本：包装脚本按标记 `git reset --hard` 一次；  
- 手工回滚：

```bash
cd /opt/kanban/看板正式程序
git reset --hard <好commit>
sudo systemctl restart kanban
```

### 10.1 运维发版上机铁律（2.7.3 · 禁止只 pull）

`git pull` **不会**自动装载 nginx conf。每次上机必须：

```bash
cd /opt/kanban/看板正式程序 && git pull --ff-only origin main
sudo cp deploy/linux/nginx-kanban.conf /etc/nginx/sites-available/kanban
sudo nginx -t && sudo systemctl reload nginx
systemctl is-active kanban
```

维护开关（可选手工）：

```bash
bash deploy/linux/maintenance_on.sh    # 用户见「系统正在更新中」
bash deploy/linux/maintenance_off.sh   # 关闭
# 标志：数据/maintenance.flag（gitignore；超时 10 分钟强制关）
```

---

## 11. 常见故障

| 现象 | 自查 |
|------|------|
| 台账一直黄 | `mount \| grep caiwu`；设置页路径是否 POSIX |
| 导出图中文方块 | `fc-list :lang=zh`；装 `fonts-noto-cjk` |
| 8018 不通 | `ss -lntp \| grep 8018`；`ufw status` |
| 服务起不来 | `journalctl -u kanban -e`；`.venv` 与 Python 3.12+（系统 python3） |
| 定时没跑 | `crontab -l` 哨兵段；`systemctl status cron` |
| 一键更新拒 | `git status` 是否脏（勿改 config.json） |

---

## 12. 仅部署机可验清单

下列项开发机（macOS）**无法**完整模拟，上线日按本手册勾选：

1. `systemctl enable --now kanban` 开机自启  
2. 真实 CIFS `mount -a` 与掉挂载后的体检黄  
3. 服务内 ScheduleLoop 到点刷新：`built_at` 前进且日志有 `schedule_loop` / `trigger=schedule`（勿再依赖 cron `--scheduled` 更新页面）  
4. `systemd-analyze verify /etc/systemd/system/kanban.service`  
5. ufw 从同事机访问 8018  
6. Playwright 导出 PNG 中文清晰  

本仓库已覆盖：脚本 `bash -n`、回滚三态桩测、cron 哨兵桩测、`fetch_ledger` POSIX 降级、全量 `run_verify`。

---

## 附录 · nginx 反代双进程（任务书43 · 方案 B）

### 模式

| 模式 | server_host | serve_static | 对外 |
|------|-------------|--------------|------|
| 直连（默认/开发） | 0.0.0.0 | true | :8018 静态+API |
| nginx 生产 | 127.0.0.1 | false | :80 nginx → 127.0.0.1:8018 |

```bash
sudo apt install -y nginx
sudo cp /opt/kanban/看板正式程序/deploy/linux/nginx-kanban.conf /etc/nginx/sites-available/kanban
# 改 conf 内 root/alias 路径
sudo ln -sf /etc/nginx/sites-available/kanban /etc/nginx/sites-enabled/kanban
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
# systemd 已设 KANBAN_SERVER_HOST=127.0.0.1 KANBAN_SERVE_STATIC=0
sudo systemctl restart kanban
```

**发版后再次上机**：仍须 `git pull` → `sudo cp …/nginx-kanban.conf` → `nginx -t && reload`（见 §10.1）。只 pull 不算完成。  
**2.7.3**：页面入口在 `数据/maintenance.flag` 或上游 502/504 时出维护 HTML；`/api/` **不** intercept 成 HTML。

### 禁休眠 / ufw / fail2ban（台式机长开）

```bash
# 禁休眠（GNOME 示例；以发行版为准）
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

# ufw：放行 80；8018 仅本机（不对外）
sudo ufw allow 80/tcp comment 'kanban-nginx'
sudo ufw allow from 127.0.0.1 to any port 8018
sudo ufw status

# fail2ban SSH（发行版包）
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

### 飞书告警

**已删除（2026-07-25）**。看板不再支持飞书 webhook 外发；禁止向公司大群/财经新闻 bot 测试。运维告警只看本机日志与 `数据/日志/`。

### NTP

```bash
timedatectl status   # NTP synchronized: yes
```

---

## 附录 · 整机灾难恢复（2.6.6 演练补）

> 本地空机演练（2026-07-26）：`git clone` → `python3 -m venv` → `pip install -r requirements.txt` → 恢复 `数据/看板.db` → `create_app` 可建。墙钟约 **10s**（已有依赖缓存时；全新机器 pip 更久）。

### 必拷数据（丢了就回不来）

| 路径 | 作用 |
|------|------|
| `数据/看板.db` | 业务库（std / 手填 / 调整 / 预算 / 日志） |
| `数据/看板账号.json` | 账号口令真相源（chmod 600） |
| `数据/本地配置.json`（若有） | 路径/开关；损坏会退回默认 |
| `数据/管理员密钥.json` | 会话密钥；无则首次启动自动生成（**旧会话全失效**） |
| 智云 / 台账凭据 | **不进 git**；见机上运维笔记 / 公司电脑夹 |
| CIFS 凭据 `/etc/kanban-cifs.cred` | 台账共享；不进 git |

### 从备份恢复库

```bash
cd /opt/kanban/看板正式程序
sudo systemctl stop kanban
# 备份损坏库
cp -a 数据/看板.db "数据/备份/看板_坏库_$(date +%Y%m%d%H%M).db"
# 从异地/本机备份恢复（文件名按实际）
cp -a 数据/备份/看板_上机前_YYYYMMDDHHMM.db 数据/看板.db
# 手填/调整行数应与备份一致（见演练报告对照命令）
sudo systemctl start kanban
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8018/login
```

### 手册曾漏、演练补上的点

1. **明确写 `数据/看板.db` 文件名**与「先停服再拷」顺序。  
2. **无共享盘时**：`KANBAN_OFFLINE=1` 或允许 local_fallback；正式机仍应修 CIFS。  
3. **clone 后仓库已含 `frontend/dist`**：不必在部署机 `npm run build`（除非改前端源码）。  
4. **账号样例** `docs/看板账号样例.json` ≠ 生产口令；生产用机上 `数据/看板账号.json`。

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

