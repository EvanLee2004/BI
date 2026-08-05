# 图集说明

产品版本以仓库根目录 `VERSION` 为准（**3.7.15** · 以文件与项目 `progress.md` 顶部为准）。  
下列工程图描述生产主架构：**浏览器 → nginx → Vue + FastAPI(`/api/v1/*`) → domain/profit → SQLite**；部署机 Ubuntu · systemd · nginx · **CIFS `/mnt/kanban-ledger`**；发版 **:8019 候选预热**后切主 **:8018**。

| 文件 | 内容 | 图龄 |
|------|------|------|
| architecture.png | 系统逻辑架构（含 CIFS 台账） | **2026-08-05 · 3.7.15**（由 `设计图/*.mmd` 导出；矢量源优先） |
| deploy.png | 部署与运行拓扑（含 :8019 + CIFS） | 同上 |
| modules.png | 模块与组件 | 同上 |
| auth.png | 账号登录与权限分流（kanban_sid · 凭据不下发） | 同上 |
| howto-run.png | 每天怎么跑（白话） | 同上 |
| sequence.png | 关键流程时序（`/api/v1/*`） | 同上 |
| er.png | 数据库模型（金额 INTEGER 分） | 同上 |

矢量源：`docs/设计图/*.mmd`。  
**导出铁律**：工程 PNG **必须** `npx @mermaid-js/mermaid-cli -i xxx.mmd -o docs/images/xxx.png -b white`（Chromium 画节点字）。  
**禁止** `mmd→svg→rsvg-convert`——librsvg 不渲染 foreignObject，Gitee/GitHub 会显示白框无字。

界面实拍：`docs/images/ui/`（`_golden_data` 脱敏）。  
`05_key_customers.png` = **完整作战台**（双饼 + 三池名单 + 行动队列，约 1440×1240）。
