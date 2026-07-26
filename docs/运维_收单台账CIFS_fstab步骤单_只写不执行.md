# 收单台账共享盘 · CIFS/fstab 步骤单（**只写不执行**）

> 2.6.8 T4 产出 · 2026-07-27  
> **本文件仅供白天在公司由运维/明昊手动执行。本轮代码与部署脚本绝不改 `/etc/fstab`、不动 gvfs、不写 smb 凭据。**

## 背景

- 现象：`ledger_share_path` 指向用户态 gvfs 挂载时，会话断开后 `Path.exists()` 失败 → 管道 `local_fallback`，费用用本地旧台账。
- 2.6.8 已做：探测 + 短重试（`ledger_share_retries` / `ledger_share_retry_delay_sec`）+ 人话告警；**不**自动挂载。

## 推荐目标态（系统级 CIFS）

1. 固定挂载点，例如：`/mnt/kanban-ledger`（目录预先 `mkdir`，属主 root，权限 755）。
2. 凭据文件：`/etc/kanban/cifs-ledger.cred`（mode `600`，仅 root 可读），内容形如：
   ```
   username=...
   password=...
   domain=...   # 若需要
   ```
3. `/etc/fstab` 追加一行（**示意，勿照抄敏感路径到 git**）：
   ```
   //文件服务器/共享名 /mnt/kanban-ledger cifs credentials=/etc/kanban/cifs-ledger.cred,uid=lee,gid=lee,iocharset=utf8,file_mode=0644,dir_mode=0755,nofail,x-systemd.automount 0 0
   ```
4. `sudo mount -a` 或 `sudo systemctl daemon-reload && sudo systemctl restart remote-fs.target`。
5. 管理端「设置」把 `ledger_share_path` 改成 **POSIX 文件路径**，例如：  
   `/mnt/kanban-ledger/……/收单台账.xlsx`  
   （Linux 勿填 `\\server\share\...` UNC 字面量。）
6. 验证：`test -f "$ledger_share_path" && echo OK`；管理端点「更新数据」→ 体检 fetch=fetched。

## 回退

- `sudo umount /mnt/kanban-ledger`；注释 fstab 行；路径改回 gvfs 或仅本地副本。

## 禁止

- 把真实服务器名/账号/密码写进本仓库或公开文档。
- 在无人值守脚本里 `echo password | sudo` 改 fstab。
