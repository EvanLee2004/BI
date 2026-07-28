# 文档 SSOT 指针（2.7.2）

| 文件 | 唯一职责 |
|------|----------|
| **项目** `progress.md` | 进度 / 当前交付版本一句话 |
| **程序** `Agent.md` | 架构铁律 / API 契约 / 终态（读只 v1；须重登） |
| **程序** `docs/Runbook.md` | 运维处方（部署、挂服、回滚） |
| **程序** `docs/softeng/12_风险与技术债台账.md` | 技术债台账（更新状态） |
| 根 `工作日志.md` | 流水追加，**不写 VERSION 真理** |

版本号真理：程序根 `VERSION` 文件 + `src/version.py` PRODUCT_CHANGELOG。

**2.7.2**：业务读/写/探活均 `/api/v1/*`；上机后须**重新登录**（仅 `kanban_sid`）。
