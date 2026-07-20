# MADR-0022 金额端到端分整数 + Decimal ROUND_HALF_UP

- Status: Accepted
- Date: 2026-07-21
- Context: F-01 税拆分/去税/附加税曾走「分→元 float→round→分」，半位与累计不稳。
- Decision: 算账路径在分上 `Decimal` 除乘 + `ROUND_HALF_UP`；显示层才 `fen_to_yuan`。
- Consequences: golden 本数据集数值零 diff；边界由单测锁定。
