# 收单台账共享盘 · CIFS 步骤单（运维）

> 2.6.8 起 · **2026-08-05 现网已落地 CIFS + 3.7.15 管理端 B**  
> 真实账号/密码**永不进 git**。改密优先走管理端（受控 apply）或本机手工改 cred。

## 现网实况（2026-08-05 · PROD 3.7.15）

| 项 | 状态 |
|----|------|
| Wi‑Fi | 公司 **BESTEASY** |
| 挂载 | **`/mnt/kanban-ledger`** · cifs · `//192.168.10.151/财务部` |
| 凭据 | `/etc/kanban/cifs-ledger.cred` mode **0600**（root） |
| fstab | 含 kanban-ledger 行（`nofail,x-systemd.automount,_netdev`） |
| 看板路径 | `数据/本地配置.json` → `ledger_share_path` = `/mnt/kanban-ledger/…/收单台账.xlsx` |
| 结构化字段 | `ledger_smb_server/share/relpath/username` + `ledger_smb_password_set` |
| apply | `/usr/local/sbin/kanban-cifs-apply` + `/etc/sudoers.d/kanban-cifs` |
| unit | `ReadWritePaths` 含 `/mnt/kanban-ledger` |
| gvfs | **不再作为生产依赖**（历史会话可残留，勿当唯一路径） |

## 新建机 / 重装时（人白天执行）

1. `sudo apt-get install -y cifs-utils`  
2. `sudo mkdir -p /mnt/kanban-ledger /etc/kanban`  
3. 写 cred（mode 600）— **勿提交 git**  
4. fstab 一行（主机/共享名以财务实况为准）：  
   `//<server>/<share> /mnt/kanban-ledger cifs credentials=/etc/kanban/cifs-ledger.cred,uid=lee,gid=lee,iocharset=utf8,file_mode=0644,dir_mode=0755,nofail,x-systemd.automount,_netdev 0 0`  
5. `sudo mount -a` · `findmnt /mnt/kanban-ledger`  
6. 安装：  
   `sudo install -m 755 deploy/linux/kanban-cifs-apply.sh /usr/local/sbin/kanban-cifs-apply`  
   `sudo cp deploy/linux/sudoers.d-kanban-cifs /etc/sudoers.d/kanban-cifs && sudo chmod 440 … && sudo visudo -cf …`  
7. 管理端设置填服务器/共享/相对路径/账号（密码只写一次）；或直接编辑 `本地配置.json` 非密字段  
8. `sudo systemctl daemon-reload && sudo systemctl restart kanban`  
9. 验证：路径 exists · 管理端「更新数据」· 体检非 local_fallback  

## 日常换账号 / 换盘

| 方式 | 操作 |
|------|------|
| **推荐** | 管理端设置页改字段 → 保存（密码留空=不改） |
| 手工 | 改 cred + `sudo mount -o remount /mnt/kanban-ledger` 或 umount+mount |

## 回退

- 路径改本地副本 only；注释 fstab；`sudo umount /mnt/kanban-ledger`（**仅人授权**）  
- **不推荐**回 gvfs 作 7×24 唯一依赖  

## 禁止

- 真实密码进仓库 / 公开文档 / 审计 md  
- 无人授权 AI Goal 改 fstab、umount、reboot  
- Python 内任意 `sudo` shell（仅 apply 白名单）  
