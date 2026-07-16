# MADR 0001：定时更新用 cron，不用 systemd timer

- **状态**：已采纳（2026-07-16 · 任务书40）
- **上下文**：每日多时间点跑 `run.py --scheduled`；Windows 侧为 schtasks 多任务。

## 决策

采用**当前用户 crontab + 哨兵段**（`# BEGIN kanban-schedule` … `# END kanban-schedule`），由 `deploy/linux/register_schedule.sh` 与管理端 `sync_schedule` Linux 分支重写段内行。

## 理由

1. **无需 root**：用户 crontab 即可；systemd timer 常需 unit 装到 `/etc/systemd/system`。
2. **多时间点最简**：每个 HH:MM 一行；timer 要为每个时间点写 OnCalendar 或用一个复杂 calendar。
3. **与设置页对齐**：保存 `schedule_times` 时 best-effort 重写哨兵段，失败提示重跑脚本——与 Windows 行为对称。
4. **绝不吞用户其它 cron 行**：哨兵圈定，段外原样保留。

## 后果

- 部署机需有 `cron` 服务（Ubuntu 22.04 默认有 `cron` 包）。
- 真实 crontab 写入**仅部署机可验**；CI/开发机桩测哨兵逻辑。

## 未选

- **systemd timer**：能力更强，但多时间点+非 root 运维成本更高；将来若统一 root 运维可另立任务书迁移。
