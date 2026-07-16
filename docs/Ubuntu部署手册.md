# 甲骨易智能经营罗盘 · Ubuntu 22.04 从零部署手册

> **适用**：部署机从 Windows 迁到 **Ubuntu 22.04 LTS**（或兼容的 22.04 系）。  
> **产品目录约定**：`/opt/kanban/看板正式程序`（也可放 home，权衡见 §1）。  
> **形态**：FastAPI 同端口双端（用户 `/` + 管理 `/admin`）+ systemd 常驻 + cron 定时更新 + 智云/台账 CIFS 抓数。  
> **修订**：2026-07-16 任务书40/42。  
> **Windows 手册**（`docs/Windows部署手册.md`）保留，标 **legacy**，回退保险。

**不做**：Docker / K8s（现阶段裸 systemd 最简，见 `docs/madr/`）。

---

## 0. 你需要准备什么

| 项 | 说明 |
|----|------|
| 机器 | 财务部 Ubuntu 22.04，内网，建议常开 |
| 权限 | sudo（装包、fstab、systemd、ufw） |
| 账号 | 智云全量只读号；看板管理员口令；**CIFS 共享盘账号密码（手填，不进 git）** |
| 网络 | 智云内网、共享盘 `//192.168.10.151/财务部`、Gitee（或 GitHub） |
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

## 2. 基础包 + Python 3.12（deadsnakes）

Ubuntu 22.04 自带 3.10；本产品与 CI 对齐 **3.12**（MADR：`docs/madr/0002_python_version_ubuntu22.md`）。

```bash
sudo apt update
sudo apt install -y git curl ca-certificates build-essential \
  cifs-utils fonts-noto-cjk \
  libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2

# deadsnakes → Python 3.12
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
python3.12 --version
```

**中文字体 `fonts-noto-cjk` 必装**：否则导出 PNG 中文变豆腐块。

**导出 PNG / Playwright**（可选，管理端截图导出时）：

```bash
# 在 venv 装好 requirements 后
.venv/bin/playwright install chromium
# 若缺系统库，再：
sudo .venv/bin/playwright install-deps chromium
# 或使用上文 apt 列表（chromium 运行库）
```

---

## 3. clone 代码 + venv + 依赖

```bash
cd /opt/kanban
# 推荐 Gitee 镜像；按实际仓库地址改
git clone <仓库URL> 看板正式程序
cd 看板正式程序

python3.12 -m venv .venv
.venv/bin/pip install -U pip
# 清华镜像（与 config 默认 pip_mirror 一致；也可用官方源）
.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 4. 收单台账 CIFS 挂载（最高风险项）

共享源：`//192.168.10.151/财务部` → 挂到 `/mnt/caiwu`。

```bash
sudo mkdir -p /mnt/caiwu
sudo tee /etc/kanban-cifs.cred >/dev/null <<'EOF'
username=【明昊部署时手填】
password=【明昊部署时手填】
domain=【若有】
EOF
sudo chmod 600 /etc/kanban-cifs.cred
# 凭证绝不进 git

# fstab（_netdev = 等网络再挂）
echo '//192.168.10.151/财务部 /mnt/caiwu cifs credentials=/etc/kanban-cifs.cred,iocharset=utf8,uid=kanban,gid=kanban,file_mode=0640,dir_mode=0750,_netdev,vers=3.0 0 0' | sudo tee -a /etc/fstab

sudo mount -a
mount | grep caiwu
ls /mnt/caiwu/lara.zhao/   # 按实际子路径
```

**看板配置**：管理端「设置 → 台账路径」填 **POSIX 路径**，例如：

```text
/mnt/caiwu/lara.zhao/收单台账.xlsx
```

落 `数据/本地配置.json`（gitignore），**不要改** `config.json` 里的 Windows UNC 出厂默认。

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

## 7. cron 注册多时间点

```bash
cd /opt/kanban/看板正式程序
bash deploy/linux/register_schedule.sh
crontab -l | sed -n '/BEGIN kanban-schedule/,/END kanban-schedule/p'
```

管理端改「自动更新时间」保存时，Linux 上会 best-effort 重写哨兵段；失败提示重跑本脚本。  
选型理由：`docs/madr/0001_cron_vs_timer.md`。

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
| 服务起不来 | `journalctl -u kanban -e`；`.venv` 与 Python 3.12 |
| 定时没跑 | `crontab -l` 哨兵段；`systemctl status cron` |
| 一键更新拒 | `git status` 是否脏（勿改 config.json） |

---

## 12. 仅部署机可验清单

下列项开发机（macOS）**无法**完整模拟，上线日按本手册勾选：

1. `systemctl enable --now kanban` 开机自启  
2. 真实 CIFS `mount -a` 与掉挂载后的体检黄  
3. 真实用户 `crontab` 到点执行 `--scheduled`  
4. `systemd-analyze verify /etc/systemd/system/kanban.service`  
5. ufw 从同事机访问 8018  
6. Playwright 导出 PNG 中文清晰  

本仓库已覆盖：脚本 `bash -n`、回滚三态桩测、cron 哨兵桩测、`fetch_ledger` POSIX 降级、全量 `run_verify`。
