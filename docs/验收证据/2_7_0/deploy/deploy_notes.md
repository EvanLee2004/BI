# 2.7.0 生产上机实核

- 主机: `kanban-lan` · `/opt/kanban/看板正式程序`
- **VERSION=2.7.0** · HEAD=`b4830f5`
- 操作: `git pull --ff-only`（gitee origin `4092094..b4830f5`）；`kill -KILL` serve 子进程（PID 655328）→ start_with_rollback 看门狗拉起（新 PID 658106）
- 就绪: `kanban.log` **就绪 built_at=2026-07-28 15:16:52**；nginx `/login` **200**；health **黄**（手填缺月/销售未归属 BU 业务黄，非本单回归）
- 抽核: 机上 `cat VERSION`=2.7.0 与 `git rev-parse --short HEAD`=b4830f5 一致；进程冷启首次管道后 built_at 更新
- 未改 IP/端口；未 push tags；未 force
