# 驾驶舱渲染就绪 JSON Contract v1（阶段 B-P1）

> 基准=阶段 A 完成后的看端形态。前端只拼 DOM，零金额运算。

## 顶层
| 节点 | 说明 |
|------|------|
| api_version | "v1" |
| scope | 整体 / BU |
| meta | generated_at, year, year_key, tab_groups, budget, health… |
| period_keys / default_period / periods | 全周期预渲染数据 |
| rankings_view[period_key] | **P0 已落地** 双血条显示串 |
| trend / receipt_order_monthly | 图表原始系列（或后续 pre-rendered svg） |
| numbers | golden 对照子集 |

## 模板清单 ↔ contract 节点（防漏卡）
| static/templates | contract 节点 |
|------------------|---------------|
| render/dashboard_body.html | page.shell |
| render/kpi_*.html | periods[k].kpi_cards（待 P2） |
| render/trend_card.html | trend_card（待 P3） |
| render/pl_table.html | periods[k].pl_table（待 P3） |
| render/expense_*.html | periods[k].expense_views（待 P3） |
| render/profit_*.html | periods[k].profit_rankings（待 P3） |
| render/rc_*.html | receipt_card（待 P4） |
| render/dual_*.html | **rankings_view[k]**（P0） |
| render/period_*.html | period_bar（待 P2） |
| partials/* | shell chrome（静态） |
| login.html / view_login.html | 登录（服务端） |
| charts/* | chart fragments |

## 验收
- 模板文件清单 vs 上表 diff 为空（tests/test_b_p1_contract.py）
- rankings_view 显示串 == 旧 HTML 对应位置
