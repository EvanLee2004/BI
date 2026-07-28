# S0 复现 F-01 · 2.6.12 开工钉死

- **基线**：`VERSION=2.6.11` · HEAD=`f2baa33`
- **日期**：2026-07-28
- **复现方式**：源码对照（RankList 主列表 vs 弹层）+ 与 2.6.11 行为一致

## 现象（F-01）

| 路径 | 期望 | 基线实际 |
|------|------|----------|
| 下单/回款「按销售/按客户」**前十**行点击 | 打开「×× · 1～12 月下单/回款」月钻 | ✅ 可点（主列表有 `onItemClick` + `mkey`） |
| 点「其余 N 个 → 点开展示明细」后，在**完整排名弹层内**点人名 | 同样打开月钻 | ❌ 不可点（弹层只渲染 `RankBar`，无 click / `is-clickable`） |

## 根因（源码）

文件：`frontend/src/components/base/RankList.vue`

- **主列表**（约 117–136 行）：`class` 含 `is-clickable`（当 `onItemClick && it.mkey`），`@click` → `onItemClick(it)`
- **弹层** `data-testid="rank-modal-list"`（约 157–172 行）：仅 `v-for` 渲染 `RankBar`，**未**绑 `onItemClick` / `mkey` 可点契约

父组件 `RankingsDual.vue` 已传 `:on-item-click="onItemClick"`，且 `toListItems` / `fetchFull` 保留 `mkey`；**不是**缺 monthly API 数据。

## 复现结论

- 根因已钉死：弹层漏接与主列表相同的 click 契约。
- 修复范围：仅 RankList 弹层行绑定；禁止大重构、禁止重算金额。
