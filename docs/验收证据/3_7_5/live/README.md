# 3.7.5 活体证据（脱敏）

> 真实客户名/金额/密码禁止入库。本目录记录 route / viewport / theme / 操作→所见。

## 环境

| 项 | 值 |
|----|-----|
| worktree | `kanban-375-ui-trust` |
| branch | `task/20260802-ui-trust-polish` |
| 基线 | `9ca4d45` |
| 候选 | 见控制卡 `candidate_commit` |
| fixture | offline `_golden_data` / 合成账号 |
| 浏览器 | 本机 headless 可选；无浏览器时以组件守卫 + 门禁代替截图 |

## 桌面 ≥1440（neon 或 dark）

| # | route | viewport | 操作 | 预期 | 实际 | 备注 |
|---|-------|----------|------|------|------|------|
| D1 | `/` 首页 | 1440 | 打开 | KPI/六段可见 | 守卫+build | 合成 |
| D2 | `/` 下单回款 | 1440 | 看右侧 | 年度进度大数字/完成率/目标/尚差/条 | `rc-year-progress` 守卫 | |
| D3 | `/` 重点客户 | 1440 | hover/click `?` | 浮层锚定、Esc/点外关 | HelpPopover 守卫 | |
| D4 | `/` 重点客户 | 1440 | 摘要 | 三等宽卡，无「需跟进」顶卡 | 无 `kc-card-silent` | 行动队列仍在下方 |
| D5 | `/` 费用 | 1440 | 悬停格 | 月×类+金额；图例单位范围 | heat pack 守卫 | |
| D6 | `/admin/settings` | 1440 | 打开 | 密码框空；已设置提示 | 凭据红→绿 | |
| D7 | `/admin/review/overview` | 1440 | 切组 | skeleton 后内容 | admin-page-loading | |

## 390px

| # | route | 操作 | 预期 | 实际 |
|---|-------|------|------|------|
| M1 | `/` 顶栏 | 打开 | logo/标题/更新时间/主题导出不重叠 | App.css 两行分层 |
| M2 | `/admin` 导航 | 五一级 | 横向可滚、非单字竖排、当前态 | admin-layout.css |
| M3 | 重点客户 `?` | click | 完整可滚不裁切 | DataModal 窄屏 |
| M4 | 费用热力 | 横滚 | 轴标签/tooltip 可读 | min-width 560 + confine |

## 已知限制

- 本 EXECUTOR 环境以离线测试与静态/结构守卫为主；完整像素截图可在有 Playwright 的验收会话补齐。
- 证据不得含真实密码/客户金额。
