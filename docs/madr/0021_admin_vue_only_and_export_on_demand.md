# 0021 · 管理端 Vue 单轨 + 渲染按需导出

- **状态**：Accepted
- **日期**：2026-07-20
- **任务书**：65

## 背景

文档曾写「54.4 已删 legacy 管理端」，实际运行时仍保留 `_admin_is_vue` 双轨与 `static/admin` 旧壳。
服务端 `render*.py` 每次刷新预装整页 HTML，而看端已是 Vue；整页 HTML 实际只服务 PNG 导出与历史快照。

## 决策

1. **管理端唯一路径 = Vue SPA**（+ 空库 `bootstrap.html` 引导）。删除 `admin.js` / `admin.html.legacy` / 双轨分支。
2. **刷新不预装整页**；`has_data` 显式标志；导出时 `assemble_export_html` 按需装配（同 `built_at` 缓存）。
3. `bu_pages` 仍发布 summary/fragments/views（看端 API 依赖），不预装 `html`。

## 后果

- 测试不得再锁定 legacy admin 文件；改扫 Vue 源。
- PNG 导出功能保留且行为等价。
