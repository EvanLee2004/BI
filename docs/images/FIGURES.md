# 图集说明

产品版本以仓库根目录 `VERSION` 为准（现网 **3.3.1**，2026-07-29）。  
下列工程图描述生产主架构：**浏览器 → nginx → Vue + FastAPI(`/api/v1/*`) → domain/profit → SQLite**；部署机 Ubuntu · systemd · nginx。

| 文件 | 内容 | 图龄备注 |
|------|------|----------|
| architecture.png | 系统逻辑架构 | 2026-07-21；主路径仍准；框内「assemble HTML / user_html」等措辞为历史，现网导出=**kanban_snapshot** |
| deploy.png | 部署与运行拓扑 | 2026-07-21 |
| modules.png | 模块与组件 | 2026-07-21 |
| auth.png | 账号登录与权限分流 | 2026-07-22；会话现仅 `kanban_sid` |
| howto-run.png | 每天怎么跑（白话） | 2026-07-22 |
| sequence.png | 关键流程时序 | 2026-07-22 |
| er.png | 数据库模型 | 2026-07-22；金额 INTEGER 分 |

矢量编辑源：`docs/设计图/`。  

界面实拍：`docs/images/ui/`（`_golden_data` 离线演示数据，非生产客户数据）。**摄于 2.3.1 批次**——主布局可用；用户统计导航 / 含税口径小字 / 设置页无飞书卡 / 晨光主题等**未重截**（见根 README「界面长什么样」免责声明）。
