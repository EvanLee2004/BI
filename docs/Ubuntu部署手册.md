# 甲骨易智能经营罗盘 · Ubuntu 26.04 从零部署手册

> **版本对齐（2026-07-25）**：产品 **v2.6.0**（以根目录 `VERSION` 为准）：统一 `/login`、会话 cookie **`kanban_sid`**（旧 cookie 兼容读 21 天）、金额分整数、管理端 Vue 单轨、nginx 根路径反代（2.4.3）。

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

## 4. 收单台账 CIFS / gvfs 挂载（最高风险项）

> **真实共享 IP、共享名、子目录、文件名不写进本仓库（GitHub）**。  
> 部署时对照机上 `/opt/kanban/运维笔记/收单台账路径.md` 或工作区「公司电脑（部署机）」夹（不上公开仓）。

共享源：`//【文件服务器】/【共享名】` → 挂到例如 `/mnt/caiwu`（或桌面 gvfs）。

```bash
sudo mkdir -p /mnt/caiwu
sudo tee /etc/kanban-cifs.cred >/dev/null <<'EOF'
username=【部署时手填】
password=【部署时手填】
domain=【若有】
EOF
sudo chmod 600 /etc/kanban-cifs.cred
# 凭证绝不进 git

# fstab（_netdev = 等网络再挂；【】处换成机上运维笔记里的真实值）
echo '//【文件服务器】/【共享名】 /mnt/caiwu cifs credentials=/etc/kanban-cifs.cred,iocharset=utf8,uid=kanban,gid=kanban,file_mode=0640,dir_mode=0750,_netdev,vers=3.0 0 0' | sudo tee -a /etc/fstab

sudo mount -a
mount | grep caiwu
ls /mnt/caiwu/   # 再进入运维笔记写明的子目录
```

**看板配置**：管理端「设置 → 台账路径」填 **完整可达路径**（POSIX / gvfs / UNC 均可），**只落** `数据/本地配置.json`（gitignore）。

```text
# 示例形态（占位，非真实地址）
/mnt/caiwu/【子目录】/收单台账.xlsx
```

`config.json` 出厂 `ledger_share_path` **留空**——真实路径不得写进 git。

**挂不上时看板表现**：`fetch_ledger` 走上次本地副本 + 体检黄，管道不中断。自查：

```bash
mount | grep caiwu
ls -la /mnt/caiwu
journalctl -u kanban -n 50 --no-pager | grep -i 台账
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

与 Windows 相同护栏：`updater.apply_update` → `git pull --ff-only` → 依赖变则 pip → 写 `.update_rollback` → 退出码 **42**。

- systemd `Restart=always` + 包装脚本处理 42；  
- 坏版本：包装脚本按标记 `git reset --hard` 一次；  
- 手工回滚：

```bash
cd /opt/kanban/看板正式程序
git reset --hard <好commit>
sudo systemctl restart kanban
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

管理端设置或 `数据/本地配置.json` 写 `feishu_webhook_url`（不进 git）。空=静默。

### NTP

```bash
timedatectl status   # NTP synchronized: yes
```
