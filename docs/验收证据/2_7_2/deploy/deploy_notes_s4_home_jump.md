# 2.7.2 S4 export 生产上机（家机跳板）

- 跳板: home-linux `192.168.1.7` → Tailscale `lee@100.127.5.5`（kanban）
- 代码: `git pull --ff-only` → **VERSION=2.7.2** HEAD=**924c020**
- 操作: kill serve 子进程 → systemd 看门狗拉起
- 就绪: built_at=**2026-07-28 19:02:25**；health 黄（业务）；nginx `/login` 200

## 路由实核

| 路径 | 结果 |
|------|------|
| `/export.html` `/export.png` `/bu/x/export.html` | **404** |
| `GET /api/health` `POST /api/refresh` | **404** |
| `GET /api/v1/health` | **200** |
| 登录整体 + `/api/v1/vm/cockpit` | KPI 有数（orders/pretax） |
| cookie | 仅 `kanban_sid` |
| `GET /api/v1/export.html`（已登录） | **200** text/html |
| `GET /api/v1/admin/refresh_status`（管理员） | **200** |

## 说明

- 未改 IP/端口；未 push tags
- 家机 Mac `id_ed25519` 有口令，跳板首跳用密码；生产用 `id_ed25519_hostup`
