# O-5 同族扫尾 · 展开/Teleport/遮罩/fixed/静默空态

## 扫了什么
- 全部 `Teleport to="body"`：PLTable / ExpenseSection / DataModal / Toast / TopBarActions
- `v-if` 与 detail/openRow 与门：仅 PL 已改为 `drawerOpen`；Expense 对齐
- 产品 CSS `z-index:60` 与 drawer：无 drawer 硬编码 60
- `#periodSync` 默认 will-change：已收敛到 `.is-period-switching`
- SPA dist：含 `.drawer{` 与 `z-index:var(--z-drawer`

## 修了什么（本单）
- B-01～B-05、R-01 见主修复
- ExpenseSection 空态对齐（同族）

## 未修待拍板
- TopBarActions 内联 `position:fixed`（既有，非静默空态；搬 tokens 属非同族样式债）
- vendor scifi-kit 内其它 will-change（非 #periodSync，铁律17 主路径已收）
- 拆 admin iframe：禁止擅自做
