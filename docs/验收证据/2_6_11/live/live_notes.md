# 活体 L1–L6 · 2.6.11

环境：本地 offline `http://127.0.0.1:8018` · 修复后 dist + theme · 2026-07-28

L1: 点击「交付成本 查看构成 ›」→ 抽屉标题「交付成本（生产成本）构成」出现，关闭按钮可用；z-index=80；截图 L1_pl_drawer.png
L2: 点击收入·按销售「其余 19 个 · 点开展示明细 ›」→ 居中 DataModal「收入 · 按销售 · 完整排名」有列表；z-index=90；截图 L2_data_modal.png
L3: 期间费用切「按类别」点「技术服务费」行 → 抽屉「技术服务费 · 费用明细」打开，有明细行；z-index=80；截图 L3_expense_drawer.png
L4: `/bu/游戏` 点「交付成本 查看构成 ›」→ 抽屉标题「交付成本（生产成本）构成」出现；截图 L4_bu_drawer.png
L5: `/admin` 展示 iframe 内点「查看构成 ›」→ iframe 视口内抽屉可见（标题同上）；再点「点开展示明细 ›」→ iframe 内 DataModal 可见；截图 L5_admin_iframe.png
L6: 本数据交付成本抽屉无「其他 N 项」▸ 行，B-02 expandable/children 靠单测 `test_structure_for_vm_preserves_expandable_children` 锁死

自检：已打开上述截图确认遮罩/面板可见，非空白静默。

## 生产实核（2026-07-28 · SSH 上机后）

- 生产 `VERSION=2.6.11` HEAD=`a9f0c61`；nginx 发 dist 含 `.drawer{` + `z-index:var(--z-drawer`
- prod L1: 点击「查看构成 ›」→ 抽屉标题「交付成本（生产成本）构成」，count=2；截图 prod_L1_drawer.png
- prod L2: 点击「点开展示明细 ›」→ DataModal「收入 · 按销售 · 完整排名」；截图 prod_L2_modal.png
- prod L5: `/admin` 展示 iframe 内查看构成 → drawer count=2；截图 prod_L5_admin.png
- 上机：git fetch github + ff-merge（origin/gitee TLS 曾中断）；kill lee 主进程由 systemd Restart=always 拉起（sudo 需交互密码）
