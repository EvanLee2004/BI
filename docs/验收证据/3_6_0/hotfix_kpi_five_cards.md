# 热修记录 · KPI 恢复五卡并排

- **日期**：2026-07-31
- **原因**：3.6.0 G5 将「税前利润」改成通栏主卡 + 四副卡，未经产品确认；现网截图反馈要求改回
- **范围（只动这些）**：
  - `frontend/src/components/KpiCards.vue` → 恢复 `kpi-grid kpi-5` + 卡内 `kpi-bus`
  - `frontend/src/styles/components/App.css` → 删除 hero/secondary/bu-strip 钩子
  - `frontend/dist/*` → 随 `scripts/build_frontend.sh` 重建
  - `tests/test_g5_boss_ui_3_6_0.py` · `tests/test_task54p1_visual.py` 守卫对齐
  - `CHANGELOG.md` 补记
- **不动**：密码/CSRF/调度/LKG/重点客户轴/中性新鲜度条/后端算账/VERSION（仍 3.6.0）
- **验收**：看端「一、基本情况」五 KPI 等权并排；税前利润不再独占整行
