# MADR-0009：生产架构 = nginx 双进程；单进程为简易模式

- **状态**：Accepted · 2026-07-17 · 任务书50·D
- **背景**：任务书46 交付时 FastAPI 单进程既发 `frontend/dist` 又发 API，开发方便但不是生产标准；任务书43 已有 Ubuntu nginx 脚本。
- **决策**：
  1. **生产标准（Ubuntu）**：nginx :80 直接发 `frontend/dist`（资产 immutable，`index.html` no-store）+ `/api/*`、`/admin`、`/bu/*`、`/login` 反代 `127.0.0.1:8018`（uvicorn 仅回环）。配置模板：`deploy/linux/nginx-kanban.conf`。
  2. **简易模式保留**：`run.py --serve` 单进程（开发机 / Windows legacy / 本机预览）行为不变；两模式静态资源与 API 响应等价（测试 `test_task43_nginx_mode` 及后继）。
  3. **开发链路**：`frontend/` vite dev server proxy `/api → 127.0.0.1:8018`（见 README）。
  4. **存储**：SQLite 抽象结论不变（MADR-0004 / 0008）。
- **后果**：部署手册以 nginx 为唯一推荐架构；简易模式文档标注「非生产」。
