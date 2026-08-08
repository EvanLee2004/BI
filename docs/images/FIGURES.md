# 图集说明

产品版本以仓库根目录 `VERSION` 为准（当前 **3.7.19**）。  
下列工程图描述生产主架构：**浏览器 → nginx → Vue + FastAPI(`/api/v1/*` + authz) → domain/profit → SQLite**；部署机 Ubuntu · systemd · nginx · **CIFS `/mnt/kanban-ledger`**；发版 **:8019 候选预热**后切主 **:8018**；定时 **每 `schedule_times` 时点完整刷新**。

| 文件 | 内容 | 图龄 |
|------|------|------|
| architecture.png | 系统逻辑架构（CIFS · ScheduleLoop 每点完整 · authz 闸） | **2026-08-08 · 3.7.19**（`设计图/*.mmd` 导出） |
| deploy.png | 部署与运行拓扑（:8019 + CIFS + BESTEASY） | 同上 |
| modules.png | 模块与组件（含 authz 能力矩阵） | 同上 |
| auth.png | 登录 / 角色 / 能力 / BU 隔离 / 导出 cap | 同上 |
| howto-run.png | 每天怎么跑（白话） | 同上 |
| sequence.png | 关键流程时序（会话闸 + 导出 cap） | 同上 |
| er.png | 数据库模型（金额 INTEGER 分） | 同上 |

矢量源：`docs/设计图/*.mmd`。  
**导出铁律**：工程 PNG **必须** `npx @mermaid-js/mermaid-cli -i xxx.mmd -o docs/images/xxx.png -b white`（Chromium 画节点字）。  
**禁止** `mmd→svg→rsvg-convert`——librsvg 不渲染 foreignObject，Gitee/GitHub 会显示白框无字。

界面实拍：`docs/images/ui/`（`_golden_data` 脱敏）。  
`05_key_customers.png` = **完整作战台**（双饼 + 三池名单 + 行动队列）。
