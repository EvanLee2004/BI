# MADR：管理端 UI 组件库选型 · Element Plus

- **状态**：已采纳（任务书 54.4 批次 D）
- **日期**：2026-07-18
- **决策者**：执行 AI（按任务书授权；明昊可改）

## 背景

看端已是 Vue3 + SciFi 自研壳 + ECharts。管理端原 `static/admin` 为单体 JS（~1100 行），需迁入同一 `frontend/` 工程。中后台表格/表单/抽屉密度高，需要成熟组件库。

## 决策

采用 **Element Plus 2.9.x**（MIT）作为管理端专用 UI 库；看端驾驶舱 **不** 引入 Element Plus 样式（admin 入口单独挂载/分包）。

## 备选

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| Element Plus | 中后台生态完整、表格/表单/分页成熟、中文文档 | 包体积偏大 | **选** |
| Naive UI | TS 友好、主题灵活 | 中后台范例与表格生态略弱于 EP | 备选 |
| 纯自研 | 零依赖 | 管理端工期不可接受 | 否 |
| 继续 static/admin | 零迁移 | 违反 PERF-FE 管理端 Vue 全量 | 否 |

## 后果

- 依赖：`element-plus`、`@element-plus/icons-vue`（MIT）
- 看端 bundle 尽量 code-split 隔离 admin 路由
- 许可证宽松，可进内网/公开代码库（仍禁真实数据）

## 找过什么

- Element Plus 官方 license：MIT
- Naive UI license：MIT
- 仓库铁律 #9：优先现成开源，不自造中后台轮子
