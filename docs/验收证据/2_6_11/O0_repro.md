# O-0 复现钉死 · 2.6.11

> 环境：本地 `KANBAN_OFFLINE=1` · `python run.py --serve` · `:8018` · VERSION **2.6.10**  
> 时间：2026-07-28 · 不改 VERSION 仅观测

## 步骤与 DOM length

| 入口 | 操作 | 查询 | length / 可见 |
|------|------|------|----------------|
| `/` 直连 | 点「交付成本 查看构成 ›」 | `.drawer.open,[data-testid=drawer-panel]` | **2**（drawer+panel）；`visibility:visible`；`position:fixed`；`z-index:60` |
| `/` 直连 | 点「其余 N 个 · 点开展示明细 ›」 | `[data-testid=data-modal]` | **1**；`position:fixed`；`z-index:90` |
| `/admin` 展示 iframe | iframe 内点「查看构成 ›」 | iframe 文档内同上 | **2**；visible；z-index **60** |
| Console | 红 error | `/` 与 iframe | **无** console error |

补充：

- `#periodSync` computed `will-change` = **`opacity, transform`**（R-01 常驻确认）
- `.drawer` 规则仅来自 `/static/css/theme.css`（`z-index:60`），**SPA dist CSS 无 `.drawer{`**（B-03/B-04）
- `PLTable.vue` 源码：`v-if="drawerOpen && detail"`（B-01 静默路径坐实）
- `structure_for_vm` lines 不含 `expandable`/`children`（B-02）

## 结论选型

任务书三选一原文：`DOM不出 | DOM出但不可见 | 仅iframe坏 | 两者都坏`

**本机 offline 观测：DOM 出且可见**（`/` 与 admin iframe 均能挂出 fixed 弹层；Console 无红错）。  
→ **不等同于「两者都坏」**；现象级「全站点不开」在生产公司机报告，本机用同一 2.6.10 代码**未能**复现「DOM 完全不挂」。

**仍必须全量修的代码真 bug（与现场症状同族）**：

1. **B-01** 无 `detail` 时 `drawerOpen && detail` 静默  
2. **B-03** 抽屉基座只在 theme，dist 无 `.drawer{`（theme 路径异常即全挂）  
3. **B-04** `z-index:60` 硬编码低于 token 80  
4. **R-01** `#periodSync` 常驻 `will-change:transform`（fixed 包含块风险）  
5. **B-02/B-05** VM 裁 expandable/children，无链路测

**选型落盘**：`DOM出但不可见` **不适用本机**；记为 **`本机DOM出且可见 · 代码层公共弹层/静默/VM 缺陷已坐实 · 按 B-01～B-05+R-01 全量硬化`**。生产上机 L1/L2 再核。

## 后续选型

按公共层硬化（O-1）→ 空态契约（O-2）→ VM 透传（O-3）执行，不拆 admin iframe。
