# 活体 L1–L6 · 2.6.11（重拍·可见弹层）

根因补修：neon `body > * {position:relative}` 曾压掉 Teleport 抽屉 fixed → 视口内不可见。
已改为 :not(.drawer):not(.data-modal-mask)…，tokens 对 body>.drawer 加 fixed !important。

L1: 点击「交付成本 查看构成 ›」→ 右侧抽屉可见 title='交付成本（生产成本）构成' w=460 h=900
L2: 点击「点开展示明细 ›」→ 居中 DataModal 可见 text='收入 · 按销售 · 完整排名\n关闭\n1\nCathy Wang\n2,294.7万\n2\n吴洪伟\n721' w=1400 h=900
L3: 期间费用切「按类别」点「技术服务费」→ 抽屉可见 title='技术服务费 · 费用明细' w=460 h=900
L4: /bu/游戏 点击「查看构成 ›」→ 抽屉可见 title='交付成本（生产成本）构成'
L6: 本数据无「其他N项」，B-02 靠单测 test_structure_for_vm_preserves_expandable_children

自检：bounding_box h>200 且 y≈0 后截图。

## 生产（neon 根因修复后重拍）

prod L1: 点击「查看构成 ›」→ 右侧抽屉可见 title='交付成本（生产成本）构成' w=460 h=900
prod L2: 点击「点开展示明细 ›」→ DataModal 可见 text='收入 · 按销售 · 完整排名\n关闭\n1\nCathy Wang\n2,326.1万\n2\n吴洪伟\n728.5万\n3\n郑瑞\n5' w=1400 h=900
prod L5: admin iframe 查看构成 → 抽屉可见 title='交付成本（生产成本）构成' w=460 h=758
prod L5-L2: admin iframe 点开展示明细 → DataModal 可见 text='收入 · 按销售 · 完整排名\n关闭\n1\nCathy Wang\n2,326.1万'
