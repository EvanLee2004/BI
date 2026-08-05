# 收单台账共享盘 · CIFS/fstab 步骤单（**只写不执行**）

> 2.6.8 T4 产出 · 2026-07-27 · **3.7.14 对齐** · **3.7.15 管理端 B 方案**  
> **本文件仅供白天在公司由运维/明昊手动执行。AI Goal 默认不改生产 fstab/cred/umount；管理端改密走受控 apply 脚本（另装 sudoers）。**

## 现网实况（2026-08-05 preflight · 与审计 08 一致）

| 项 | 状态 |
|----|------|
| Wi‑Fi | 公司 **BESTEASY** 内网 |
| 共享主机 | `192.168.10.151`（**非** `192.168.1.151`）ping/445 通 |
| 挂载形态 | **仍为 gvfs**：`gio` 挂「财务部」→ `/run/user/1000/gvfs/smb-share:server=192.168.10.151,share=财务部` |
| `ledger_share_path` | 本地配置指向 **gvfs 下 xlsx**；exists=true（会话在线时） |
| CIFS / fstab | **无**；`/mnt/kanban-ledger` **未建** |
| 仓内 unit | `deploy/linux/kanban.service` 已 **预留** `ReadWritePaths=/mnt/kanban-ledger`（未挂载无害） |

→ 管道在 gvfs 会话断开后会 `local_fallback`；**切 CIFS = 另一次人授权运维窗口**，不在 3.7.14 Goal。

## 背景

- 现象：`ledger_share_path` 指向用户态 gvfs 挂载时，会话断开后 `Path.exists()` 失败 → 管道 `local_fallback`，费用用本地旧台账。
- 2.6.8 已做：探测 + 短重试（`ledger_share_retries` / `ledger_share_retry_delay_sec`）+ 人话告警；**不**自动挂载。
- 3.7.14：管理端设置 API 增加只读 `ledger_path_exists`（管理员可见）；**不**存 SMB 密码、**不**进程内 mount。

## 推荐目标态（系统级 CIFS · 人白天执行）

1. 固定挂载点：`/mnt/kanban-ledger`（`sudo mkdir -p`，属主 root，权限 755）。
2. 凭据文件：`/etc/kanban/cifs-ledger.cred`（mode `600`，仅 root 可读），内容形如：
   ```
   username=...
   password=...
   domain=...   # 若需要
   ```
3. `/etc/fstab` 追加一行（**示意，勿照抄敏感路径到 git**）：
   ```
   //192.168.10.151/财务部 /mnt/kanban-ledger cifs credentials=/etc/kanban/cifs-ledger.cred,uid=lee,gid=lee,iocharset=utf8,file_mode=0644,dir_mode=0755,nofail,x-systemd.automount 0 0
   ```
   （共享名/子路径以财务实况为准；主机用 **10.151**。）
4. `sudo mount -a` 或 `sudo systemctl daemon-reload && sudo systemctl restart remote-fs.target`。
5. 确认 `deploy/linux/kanban.service` 已含 `/mnt/kanban-ledger` 可读路径后：`sudo systemctl daemon-reload && sudo systemctl restart kanban`（**另窗授权**）。
6. 管理端「设置」把 `ledger_share_path` 改成 **POSIX 文件路径**，例如：  
   `/mnt/kanban-ledger/……/收单台账.xlsx`  
   （Linux 勿填 `\\server\share\...` UNC 字面量；**勿**在无人 Goal 里改生产 `本地配置.json`。）
7. 验证：`test -f "$ledger_share_path" && echo OK`；设置页/API `ledger_path_exists=true`；管理端「更新数据」→ 体检 fetch=fetched。

## 与 gvfs 并存注意

- **切 CIFS 前不要 umount 现网 gvfs**（除非已改路径且验证新挂载可读），否则刷新可能立刻掉台账。
- 推荐顺序：先挂 CIFS → 改路径并点更新验证 → 再考虑是否卸 gvfs。

## 回退

- 路径改回 gvfs 或仅本地副本；注释 fstab 行；`sudo umount /mnt/kanban-ledger`（**仅人授权**）。

## 3.7.15 与管理端 B 对齐

| 项 | 说明 |
|----|------|
| 本地配置 | `ledger_smb_*` + 派生 `ledger_share_path`（无密码） |
| 本机 cred | `/etc/kanban/cifs-ledger.cred` mode 0600 |
| 应用脚本 | `deploy/linux/kanban-cifs-apply.sh` → 建议 `/usr/local/sbin/kanban-cifs-apply` |
| sudoers | `deploy/linux/sudoers.d-kanban-cifs` 仅允许固定脚本 |
| 抓数 | 仍读 `ledger_share_path`（行为不变） |
| 兼容 | 仅有旧 `ledger_share_path` 时 GET 尽量解析或只读 + 迁移提示 |

## 禁止

- 把真实账号/密码写进本仓库或公开文档。
- 在无人值守脚本 / AI Goal 里改 fstab、写 cred、umount、reboot 验收（无控制卡预授权）。
- Python 进程内任意 `sudo` shell；仅文档化 apply 接口。
