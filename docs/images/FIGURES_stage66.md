# 图集与 v2.2.0 对齐说明（2026-07-21）

| 图 | 路径 | 含义（stage66） |
|----|------|-----------------|
| architecture | architecture.png / 02_*.svg | nginx→Vue→API VM→profit 分整数→SQLite；管理端单轨 |
| sequence | sequence.png / 03 时序.svg | 刷新不预装 HTML；导出按需装配 |
| er | er.png / 03 ER.svg | 金额库内分；手填/adj 分 |
| deploy | deploy.png / 04_*.svg | systemd+nginx；ScheduleLoop |
| modules | modules.png / 05_*.svg | refresh 增量重算；gen_vm_ts |
| auth | auth.png / 06_*.svg | 账号分流；密码明文口径不变 |
| howto-run | howto-run.png | 本地 run_verify / 生产 pull 自愈 |

源 mmd 与 svg 均含 stage66 注释；PNG 为渲染产物（与 svg 语义一致）。
