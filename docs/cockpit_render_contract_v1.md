# 驾驶舱渲染就绪 JSON Contract v1（阶段 B）

> 基准=阶段 A 完成后的看端形态。前端只拼 DOM，零金额运算。
> 整页路径：`GET /api/v1/cockpit/fragments` → `static/js/assemble/page.js` 填充模板。

## 顶层（fragments 响应）
| 节点 | 说明 |
|------|------|
| api_version | "v1" |
| mode | "fragments" |
| fragments | 整页显示串/HTML 段字典（见下） |
| chrome_prefix | BU 导航条 / 隐藏改密样式（服务端按会话算好，shell 注入 wrap 前） |
| data_assembled | "1"（导出截图等待 body[data-assembled=1]） |
| views.rankings_view | **P0** 双血条叶子显示串 → rankings.js |
| views.kpi_body / pl_body / donut_body / profit_rank_body | **P2~P3** 各周期卡正文显示串 → page.js wrapPv |
| views.trend_html / receipts_budget / period_bar / daily_html | **P2~P4** 块级显示串 |
| views.year_key / period_keys | 默认周期与 .pv 顺序 |
| fragments 卡字段（client） | **全部为空**；由 page.js applyViews 填入 |

## fragments 字段（与 `render.build_dashboard_fragments` 一致）
| 字段 | 对应模板/卡 |
|------|-------------|
| title | page_shell title |
| particles / logo / version / generated_at / pw_modal | dashboard_body 顶栏 |
| period_bar | render/period_*.html |
| kpi_views | render/kpi_*（全周期 .pv） |
| trend_html | render/trend_* + charts |
| donut_views | render/expense_* |
| pl_views | render/pl_* |
| profit_rank_views | render/profit_* |
| receipts_budget | render/rc_* / period_receipts |
| daily_html | 日段卡 |
| rank_views | render/dual_* 下单回款双血条 |
| drawer | 抽屉 |

## 并行：cockpit JSON（数字/飞书复用）
| 节点 | 说明 |
|------|------|
| rankings_view[period_key] | **P0** 双血条显示串（`rankings.js` 可独立组装） |
| numbers | golden 对照子集 |
| periods / trend / receipt_order_monthly | 全周期数据 |

## 模板清单 ↔ contract 节点（防漏卡）
| static/templates | contract 节点 |
|------------------|---------------|
| render/dashboard_body.html | fragments → page.shell |
| render/page_shell.html | fragments + assemble |
| render/kpi_*.html | fragments.kpi_views |
| render/trend_card.html | fragments.trend_html |
| render/pl_table.html | fragments.pl_views |
| render/expense_*.html | fragments.donut_views |
| render/profit_*.html | fragments.profit_rank_views |
| render/rc_*.html | fragments.receipts_budget |
| render/dual_*.html | fragments.rank_views / rankings_view |
| render/period_*.html | fragments.period_bar |
| partials/* | chrome_prefix / shell chrome |
| static/view_login.html · admin_login.html | 登录 static + `/api/v1/login`（B-P4；错误前端渲染） |
| charts/* | chart fragments 嵌在 trend/donut |
| errors/http_error.html | 54.12 R-14 友好 404/500（Accept:html；非 fragments 路径） |
| export/fallback.html | 2.2.7 导出 HTML 降级壳（`export_html.fallback_export_html`；主路径 Playwright 抓 Vue） |

## 验收
- 模板文件清单 vs 上表 diff 为空（tests/test_b_p1_contract.py）
- Python `assemble_dashboard_html(frags)` == `render_dashboard` 历史路径
- Node `page.js` 组装 == 同上逐字节（tests/test_b_page_assemble.py）
- rankings_view + rankings.js 规范化全等（tests/test_b_p0_rankings_assemble.py）
- 组装 JS 零金额运算守卫
