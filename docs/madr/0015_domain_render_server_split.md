# MADR-0015：domain / render / server 拆分（补录）

- **状态**：Accepted（补录）
- **日期**：2026-07-19（实施于 54.13）· 补录日期 2026-07-19
- **背景**：`server.py` / `render.py` / `db.py` / `profit` 巨石，难导航、C901 堆叠。
- **决策**：  
  - `routes/*` 按域注册；`server.create_app` 只装配  
  - `render_*` 按板块拆文件  
  - `domain/*` 承载展示向领域（白名单、PL 结构）  
  - `db/` 子包、`profit/` 子包  
- **备选**：微服务（否）；仅注释分区（否：不够）。
- **后果**：import 路径变；纯搬家批次须行为零 diff + run_verify。
- **出处**：任务书 54.13 M1~M2。
