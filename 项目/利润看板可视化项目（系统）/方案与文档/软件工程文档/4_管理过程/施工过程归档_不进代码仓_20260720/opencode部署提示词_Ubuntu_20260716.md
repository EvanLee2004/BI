# opencode 部署提示词 · 甲骨易智能经营罗盘 · Ubuntu 26.04

> 用法：在 Ubuntu 部署机 clone 好仓库（或解压发布包）后，在程序根目录打开 opencode，**把下面「== 提示词正文 ==」整段贴给它**。  
> 对齐任务书50·D.6（部署目标 26.04）；细节以 `docs/Ubuntu部署手册.md` 为准。  
> Windows 旧提示词标 **legacy**。

---

## == 提示词正文（从这里整段复制给 opencode）==

你是这台 **Ubuntu 26.04** 上的部署助手。当前目录是「甲骨易智能经营罗盘」程序根（含 `run.py`、`deploy/linux/`、`docs/Ubuntu部署手册.md`）。请按步骤部署：**nginx 发 frontend/dist + 反代 API** + systemd 常驻 uvicorn（仅 127.0.0.1:8018）+ cron +（如需要）CIFS 台账挂载。**每一步做完把结果贴给我；遇到【停下问我】必须等我回复再继续。**

### 步骤 0 · 环境自检
1. `cat /etc/os-release` 确认 **Ubuntu 26.04** 系（若仍是 22.04，先停下告知我——默认策略已改为 26.04）。
2. `python3 --version`：**必须 ≥ 3.12**。用**系统 python3** 建 venv，**不要**默认装 deadsnakes（见 `docs/madr/0010_python_version_ubuntu26.md`）。
3. 若 `< 3.12`：`sudo apt install -y python3 python3-venv python3-dev` 后再验。
4. `git --version`；`locale` 建议 `LANG=C.UTF-8`。
5. 确认当前用户是否有 sudo；没有就只做用户态能做的（venv/cron），systemd/fstab/ufw/nginx 列命令给我手工跑。

### 步骤 1 · 目录与代码
1. 推荐路径 `/opt/kanban/看板正式程序`。若不在此，记下实际路径，后面所有路径替换。
2. 若还没有 clone：【停下问我】仓库 URL（Gitee/GitHub）与是否已有数据盘。
3. `git status` / `git log -1 --oneline` 贴给我。

### 步骤 2 · venv 与依赖
```bash
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```
装完 ` .venv/bin/python -c "import fastapi,openpyxl; print('ok')"`。

可选 Playwright（管理端导出 PNG）：
```bash
.venv/bin/playwright install chromium
sudo .venv/bin/playwright install-deps chromium   # 缺系统库时；勿手抄 22.04 包名清单
```

### 步骤 3 · 前端 dist
```bash
cd frontend && (npm ci || npm install) && npm run build && cd ..
test -f frontend/dist/index.html
```

### 步骤 4 · 数据与账号【停下问我】
1. 读 `数据/README.md`，列出 6 个 xlsx 是否齐全。
2. **真实财务数据你不能编**。缺文件就停，等我放好。
3. 账号文件是否已有（`看板账号.json` 等）——没有则用样例生成后让我改密码。

### 步骤 5 · CIFS 台账【停下问我 · 凭据绝不进 git】
1. 若要用共享盘：检查 `/etc/kanban-cifs.cred` 是否已由管理员创建（权限 600）。**不要把密码写进仓库。**
2. 按手册 §4 检查 `mount | grep caiwu`。
3. 管理端设置页台账路径应填 **POSIX**（如 `/mnt/caiwu/.../收单台账.xlsx`）。
4. 挂不上：允许先用本地 `数据/收单台账.xlsx` + 体检黄上线。

### 步骤 6 · 离线试算
```bash
KANBAN_OFFLINE=1 .venv/bin/python run.py
```
成功应有输出/页面产物。失败把 traceback 原样贴我。

### 步骤 7 · systemd（uvicorn 仅回环）
1. 复制并按实际路径改 `deploy/linux/kanban.service` → `/etc/systemd/system/kanban.service`。
2. 确认生产配置：`server_host=127.0.0.1`、`serve_static=false`（或环境变量等价），**不要**把 8018 直接暴露公网。
3. `sudo systemctl daemon-reload && sudo systemctl enable --now kanban`
4. `systemctl status kanban` + `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8018/`

### 步骤 8 · nginx（生产标准 · MADR-0009）
```bash
sudo apt install -y nginx
sudo cp deploy/linux/nginx-kanban.conf /etc/nginx/sites-available/kanban
# 改 root/alias 为实际 .../frontend/dist 与 static 路径
sudo ln -sf /etc/nginx/sites-available/kanban /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/
```

### 步骤 9 · cron
```bash
bash deploy/linux/register_schedule.sh
crontab -l | sed -n '/BEGIN kanban-schedule/,/END kanban-schedule/p'
```

### 步骤 10 · 防火墙【停下问我】
生产只开放 **80**（nginx）；8018 仅本机：
```bash
sudo ufw allow 80/tcp comment 'kanban-nginx'
# 不要默认 ufw allow 8018
```

### 步骤 11 · 验收清单
- [ ] 管理员 `/admin` 能登录  
- [ ] 整体 `/` 能看五板块（Vue dist）  
- [ ] BU 链接只见本 BU  
- [ ] 中文字体：`fc-list :lang=zh | head`  
- [ ] nginx 反代 API 200；8018 外网不可达（若已配 ufw）  

### 明确禁止
- 不改 `config.json` 出厂项来写机器路径（走设置页 → 本地配置.json）  
- 不把 CIFS 密码、管理员口令写进 git  
- 不删 Windows `.bat`（legacy 保留）  
- 不引入 Docker  
- 不默认 deadsnakes（26.04 用系统 python3）  
