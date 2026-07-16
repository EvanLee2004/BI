# MADR-0006：允许 npm / Vue 前端

- **状态**：Accepted · 2026-07-17 · 任务书46（明昊授权修订铁律）
- **背景**：旧铁律禁 React/npm/新依赖，阻碍工业级看端。
- **决策**：删除「禁 npm/新依赖」；**保留**铁律2 前端零金额运算、铁律12 BU 隔离、数字红线、凭据不进 git。
- **栈**：Vue3 + Vite + pinia + vueuse + echarts@5；不引 Element/AntD/Naive。
- **后果**：`frontend/` 进仓，`dist` 进 git；CI 重建 dist diff。
