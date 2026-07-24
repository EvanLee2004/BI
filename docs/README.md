# docs/ 索引（程序仓 · 产品文档）

**更新：2026-07-24（2.4.3 运维入口）** · 仓库只保留**产品/运维/设计**文档。  
AI 施工任务书、交付报告、验收证据、pixel 截图等**不进本仓**（工作区归档见下）。  
**产品版本以根目录 `VERSION` 为准；变更史见根目录 [`../CHANGELOG.md`](../CHANGELOG.md)**（Keep a Changelog）。

> **日常运维先看根目录 [README.md · 生产运维](../README.md#生产运维)**（入口、命令、nginx 铁律）；本页是文档地图。

---

## 当前权威（优先读）

| 文件 / 目录 | 是什么 | 什么时候看 |
|-------------|--------|------------|
| **根 [README · 生产运维](../README.md#生产运维)** | 入口两链接 · 日常命令 · nginx 根路径铁律 | **生产运维首页** |
| **[Ubuntu部署手册.md](./Ubuntu部署手册.md)** | Ubuntu 生产部署 how-to | 装机 / 升级 |
| **[Runbook.md](./Runbook.md)** | 运维排障处方卡 | 坏了怎么查 |
| **[用户手册/](./用户手册/)** | 看板使用 + 管理端 + FAQ | 教同事 |
| **[设计图/](./设计图/)** · **[images/](./images/)** | 架构/部署 SVG + README 用 PNG | 看系统长什么样 |
| **[数据来源说明.md](./数据来源说明.md)** | 六源进料与路径 | 对口径 |
| **[api-v1-cockpit.md](./api-v1-cockpit.md)** · **[cockpit_render_contract_v1.md](./cockpit_render_contract_v1.md)** · **[api/](./api/)** | 看端 API / 渲染契约 | 联调 |
| **[madr/](./madr/)** | 架构决策记录 | 为什么这样设计 |
| **[softeng/](./softeng/)** | 软工文档镜像（接口/DB/部署） | 设计细节 |
| **[系统教学说明_甲骨易智能经营罗盘_v1.md](./系统教学说明_甲骨易智能经营罗盘_v1.md)** | 教学向总览 | 新人上手 |
| **根目录 [CHANGELOG.md](../CHANGELOG.md)** | 全版本变更史（Keep a Changelog） | 版本账 |

上级完整索引（工作区）：`方案与文档/00_项目文档地图_从这里开始.md`。

---

## 子目录

| 路径 | 内容 |
|------|------|
| `用户手册/` | 看板使用 · 管理端 · FAQ · 截图 |
| `设计图/` | 现行架构/部署 SVG（旧 Windows 图在 `设计图/归档_*`） |
| `images/` | README 嵌入的架构/部署 PNG |
| `madr/` | MADR 决策 |
| `softeng/` | 接口清单 · schema · 部署说明 |
| `api/` | API 契约补充 |

---

## 运维与健康

| 路径 | 说明 |
|------|------|
| `../deploy/healthcheck.sh` | 登录页 + 数据新鲜度 |
| `../deploy/healthcheck_cron说明.md` | cron 挂法 |
| `../deploy/linux/` | nginx / systemd 模板 |

---

## 不在本仓的内容

施工过程物（任务书、交付报告、验收证据、pixel、上线交接包等）已迁出到工作区：

`方案与文档/软件工程文档/4_管理过程/施工过程归档_不进代码仓_20260720/`

`.gitignore` 已挡同类路径，避免再误 commit。
