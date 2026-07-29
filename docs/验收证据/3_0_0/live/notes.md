# 3.0.0 G6 浏览器冒烟 notes

环境：KANBAN_OFFLINE=1 · port=8018 · VERSION=3.0.0 · 账号 123

## 轮次 1
| 图 | 看到了什么 | 合格 |
|----|------------|------|
| docs/验收证据/3_0_0/live/r1_overall.png | 整体 KPI 万级 + v3.0.0 | 是 |
| docs/验收证据/3_0_0/live/r1_bu_data.png | BU「数据」有数 | 是 |
| docs/验收证据/3_0_0/live/r1_bu_game.png | BU「游戏」有数 | 是 |
| export.html / export.png | /api/v1/export.html ~10MB · export.png ~6MB PNG | 是 |

## 轮次 2
| 图 | 看到了什么 | 合格 |
|----|------------|------|
| docs/验收证据/3_0_0/live/r2_overall.png | 再次整体非空 + v3.0.0 | 是 |
| docs/验收证据/3_0_0/live/r2_bu_data.png | 再次 BU 数据非空 | 是 |
| docs/验收证据/3_0_0/live/r2_bu_game.png | 再次 BU 游戏非空 | 是 |
| export 再跑 | HTML/PNG 再次 ok | 是 |

## 结论
冒烟合格：登录 + 整体 + ≥2 BU + 导出 HTML/PNG 两轮绿。完整导出体过大不入库，见 export_proof.txt 与 _matrix_log.txt。
