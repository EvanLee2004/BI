# 2.6.12 live 证据（本机 Playwright）

## 点了什么 → 看到了什么

- **L1**：在 `#rankViews`「下单/回款 · 按销售」前十点了 **Cathy Wang** → 弹出 **「Cathy Wang · 1~12 月下单/回款」**，有 1～12 月双条。截图 `L1_top10_month.png`。**PASS**
- **L2（核心）**：在 `#rankViews` 点 **「其余…点开展示明细」** → 弹层标题 **「下单/回款 · 按销售 · 完整排名」**（32 行均 `is-clickable`）→ 弹层内点 **陈霞**（idx=12）→ 再开 **「陈霞 · 1~12 月下单/回款」**。截图 `L2_full_modal.png`、`L2_modal_month.png`。**PASS**
- **L3**：按客户前十点了 **杭州数典科技有限公司** → 月钻 OK；完整排名内点 **中国第一历史档案馆** → 月钻 OK。截图 `L3_customer_month.png`、`L3_customer_full_month.png`。**PASS**

## 结果

| 项 | 状态 |
|----|------|
| L1 前十月钻 | PASS |
| L2 完整排名弹层内月钻 | PASS |
| L3 按客户 | PASS |

> 注：首次误点「收入结构」的「其余」弹层（无 onItemClick）曾 FAIL；收口后严格限定 `#rankViews` dual 路径。
