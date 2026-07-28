# 2.7.2 S4 export 上机补丁

- 代码 tip: **74d4815**（已 dual-push main origin+gitee PUSH:0）
- 内容: 裸 export 全迁 v1；admin api.ts cookie=kanban_sid
- 本机门禁: run_verify EXIT:0（见 run_verify.log 覆盖 S4 后全量）
- **上机**：2026-07-28 晚 ssh kanban-lan/home/deploy **均超时**（公司内网/Tailscale 不可达）
- 恢复后一键：
  ```bash
  ssh kanban-lan 'cd /opt/kanban/看板正式程序 && git pull --ff-only && cat VERSION && git rev-parse --short HEAD'
  # kill serve 子进程（同 Runbook §0 2.7.x 惯例）后等 built_at
  curl -s -o/dev/null -w 'old_export=%{http_code}\n' http://127.0.0.1:8018/export.html
  curl -s -o/dev/null -w 'v1_export=%{http_code}\n' -b jar http://127.0.0.1:8018/api/v1/export.html
  ```
- 期望: VERSION=2.7.2 HEAD=74d4815；`/export.html` 404；`/api/v1/export.html` 鉴权后 200
