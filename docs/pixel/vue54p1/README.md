# vue54p1 像素证据（任务书54.1 · B0 人审打回视觉整改）

- **修改前基线**：`before/`（从 stage54 `docs/pixel/vue54/` 拷贝，见其 README）
- **迭代**：`iter_1/` 首轮=最终轮（单轮目检通过，无 iter_2）
- 亮/暗 × 1440/375：`vue_overall_{dark|light}_{1440|375}.png`
- 逐卡：`vue_overall_{mode}_{kpi|sec|trend|pl|expense_*|rank|receipts}.png`
- V7 费用折线：`v7_expense_trend_line.png`
- V8 resize：`v8_resize_before_1600.png` / `v8_resize_after_900.png`
- legacy 对照：`compare_legacy_*` / `compare_vue_*`
- 脚本：`tests/frontend/playwright_task54p1_pixel.py`（ANIM_WAIT_MS=1100）
