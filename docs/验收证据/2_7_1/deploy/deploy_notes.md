# 2.7.1 生产上机实核

- 主机: `kanban-lan` · `/opt/kanban/看板正式程序`
- **VERSION=2.7.1** · HEAD=`acb9ad9`
- 操作: `git pull --ff-only`（`b4830f5..acb9ad9`）；`kill -KILL` serve → 看门狗拉起
- 就绪: **built_at=2026-07-28 16:16:00**；nginx `/login` **200**；health **黄**（手填缺月业务黄）
- 契约: 旧 `/api/profit_ranking` → **404**；无 cookie `/api/v1/session` → **401**
- 重登: `POST /api/v1/login` 整体账号 → session 200；`/api/v1/vm/cockpit` 200；KPI 有数（orders/receipts/revenue_net/pretax_profit 非空）；cookie 仅 `kanban_sid`
- 未改 IP/端口；未 push tags；未 force
