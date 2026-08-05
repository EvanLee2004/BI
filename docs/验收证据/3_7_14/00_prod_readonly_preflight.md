# 3.7.14 部署机只读 preflight

> 时间：2026-08-05T10:22+08:00（主机 local）  
> 方式：`ssh -o BatchMode=yes kanban-lan` **只读**  
> **禁止已遵守**：未 umount / 未 `gio mount -u` / 未改 fstab / 未写 `本地配置.json` / 未重启 kanban

## 主机

| 项 | 值 |
|----|-----|
| hostname | `lee-ThinkCentre-M755e-D182` |
| date | `2026-08-05T10:22:35+08:00` |
| Wi‑Fi / SSID | 可见 **BESTEASY**（nmcli 列表含 BESTEASY / BESTEASYGUEST） |

## 共享盘可达性

| 探测 | 结果 |
|------|------|
| ping `192.168.1.151` | **100% 丢包**（与现网 gvfs 主机不一致；勿再以 1.151 为唯一目标） |
| ping `192.168.10.151` | **通**（rtt ~1.8–7.3 ms） |
| TCP 445 → `192.168.10.151` | **open** |
| TCP 445 → `192.168.1.151` | 不通 / 未开 |

## gvfs / gio

- `gio mount -l`：**仍挂载**  
  `192.168.10.151 上的 财务部` → `smb://192.168.10.151/财务部/`
- POSIX 路径形态（gvfs）：  
  `/run/user/1000/gvfs/smb-share:server=192.168.10.151,share=财务部`
- 目录 `ls` 可读（含业务子目录），**exists=true**

## ledger_share_path 形态

| 项 | 值 |
|----|-----|
| 配置文件 | `/opt/kanban/看板正式程序/数据/本地配置.json` |
| 键 | `ledger_share_path` |
| 形态 | **仍为 gvfs**（路径含 `/run/user/1000/gvfs/smb-share:...`） |
| exists | **true**（父 share 目录与台账 xlsx 路径配置存在于 gvfs 树） |
| 非 gvfs 目标 | `/mnt/kanban-ledger` **不存在**（本轮不在生产 mount） |

> 完整 UNC/gvfs 路径仅部署机私有证据需要；公开叙述优先写「仍为 gvfs 形态 + exists」。

## CIFS / fstab

| 项 | 结果 |
|----|------|
| `/etc/fstab` cifs/smb/kanban-ledger | **无** |
| `mount` 中 cifs | **无** |
| `/mnt/kanban-ledger` | **无** |

→ 与审计 **08** 一致：**现网仍 gvfs，未切 CIFS**。不触发 BLOCKED。

## kanban 服务 + health（脱敏）

| 项 | 值 |
|----|-----|
| unit | user `kanban.service`（`ActiveState=active` / `SubState=running`） |
| 进程 | `run.py --serve`（MainPID 见上机时 journal） |
| 监听 | `127.0.0.1:8018` |
| health `result` | **黄** |
| built_at | `2026-08-05 09:33:48` |
| metrics.version | `3.7.13` |
| sources | 五源均有行数（含收单台账）；**未在此粘贴客户/金额** |
| warnings（摘要） | 手填缺月；内部译员 1 行未来月 |
| run_reasons（摘要） | 定时漏跑 08-04 09:30；手填缺月 |

## 与审计 08 对照

| 检查点 | 08 预期 | 本 preflight | 结论 |
|--------|---------|--------------|------|
| BESTEASY 内网 | 是 | 是 | 一致 |
| 财务部 gvfs 挂载 | 是 | 是 | 一致 |
| ledger 为 gvfs | 是 | 是 | 一致 |
| 无 CIFS/fstab | 是 | 是 | 一致 |
| kanban active | 是 | 是 | 一致 |
| 共享主机 IP | 10.151 系 | 10.151 通；1.151 不通 | 一致（勿用 1.151） |

**总控判定**：不 BLOCKED。可按 gvfs 现状施工仓内 DOC/OPS（不在生产 mount）。

## 操作记录

- 仅 `ssh` + 读命令（ping/nmcli/gio/ls/curl/python 读配置键）。
- **未**执行 umount / `gio mount -u` / 写 fstab / 改本地配置 / systemctl restart。
