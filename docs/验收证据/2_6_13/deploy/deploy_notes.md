# 2.6.13 生产上机实核

- 主机: `kanban-lan` · `/opt/kanban/看板正式程序`
- **VERSION=2.6.13** · HEAD=`4092094`
- 操作: `git pull --ff-only`；kill -KILL serve 子进程 → start_with_rollback 拉起
- 就绪: `kanban.log` 就绪 built_at=**2026-07-28 13:39:24**；nginx /login 200；health 黄（手填缺月业务黄，非本单回归）
- 抽核: 代码 VERSION 与进程重建后 built_at 更新；本单金额与 2.6.12 同库同口径（本地 32 周期 regress 零 diff + golden 零 diff）
- 未改 IP/端口；未 push tags
