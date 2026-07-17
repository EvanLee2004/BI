# MADR-0011：口径配置 UI / 读写 API 于任务书54 下线

- **状态**：Accepted · 2026-07-18 · 任务书54·阶段 A（明昊拍板）
- **范围**：管理端设置页「口径配置」卡 + `GET/POST /api/config/caliber*`

## 上下文

- 任务书46 引入配置即数据引擎（`domain.config_engine`）与管理端口径配置卡，支持白名单/映射等键的校验与版本回滚。
- 实务中口径变更极少、且错误改动能直接改数；明昊 2026-07 拍板：**不需要管理端可写口径配置**，默认硬编码忠实导出即可。

## 决策

1. **下线 UI**：删除 `static/admin` 设置页「口径配置」整卡及 `caliberLoad/Save/Rollback` 前端函数。
2. **下线 HTTP**：`routes/config_engine_api.register` 不再挂载 `/api/config/caliber` 读写/回滚（请求 → 未注册/404）。
3. **引擎内核保留**：`domain.config_engine` 的 seed / `default_config_from_hardcoded` / 不变量校验 / 表结构 **全部保留**；启动与算账仍走默认直通，**行为与数字零变化**。
4. **golden**：`golden/admin_baseline.html` 仅删该卡块（任务书54 唯一授权 golden 改动）。

## 理由

- 少一个能改口径的写入口 = 少一类误操作事故面。
- 默认值已与现硬编码一致；日常运维不需要 UI。
- 若未来再开写入口，可恢复 API + 卡，引擎层无需重写。

## 后果

- Runbook「口径配置回滚」步骤改为：改代码/默认值或直接操作 DB（仅运维）；管理端不再提供该卡。
- 相关 HTTP 契约测试若存在应改为「未注册」；`tests/test_config_engine.py` 内核例继续绿。

## 未选

- 删整表 `cfg_口径配置` 与引擎：破坏已部署库与 migrate 路径，且无收益。
- 只藏 UI 保留 API：仍暴露写面，不符合「不需要可写」。
