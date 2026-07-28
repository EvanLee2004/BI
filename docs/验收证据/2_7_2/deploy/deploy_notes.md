# 2.7.2 生产上机实核

- 主机: `kanban-lan` · `/opt/kanban/看板正式程序`
- **VERSION=2.7.2** · HEAD=`3e69d15`（代码主交付 `0d1ac92`）
- 操作: `git pull --ff-only`；kill serve → 看门狗拉起
- 就绪: **built_at=2026-07-28 17:46:37**；nginx `/login` **200**；health **黄**（业务）
- 契约: 旧 `/api/health` **404**；旧 `POST /api/refresh` **404**；`/api/v1/health` **200**
- 重登: login 200；cockpit KPI 有数（orders/pretax 非空）；cookie 仅 `kanban_sid`
- 管理端: `GET /api/v1/admin/refresh_status` **200**
- 未改 IP/端口；未 push tags
