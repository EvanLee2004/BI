# 2.7.2 live

- BASE: `http://127.0.0.1:8018`
- viewer has_num: **True**
- health v1 status: **200** old /api/health: **404**
- refresh_status v1: **200**

## log
```
viewer url=http://127.0.0.1:8018/ has_num=True
health_v1={'status': 200, 'body': {'result': '黄', 'run_time': '2026-07-28 18:40:03', 'built_at': '2026-07-28 18:40:28', 'sources': [{'name': '项目明细(智云)', 'rows': 5447, 'months': [1, 2, 3, 4, 5, 6, 7]}, {'name': '下单(智云)', 'rows': 4467, 'months': [1, 2, 3, 4, 5, 6, 7]}, {'name': '回款(智云)', 'rows': 1098, 'months': [1, 2, 3, 4, 5, 6, 7]}, {'name': '内部译员·IN-HOUSE(智云)', 'rows': 3805, 'months': [1, 2, 3, 4, 5, 6, 7, 10]}, {'name': '收单台账', 'rows': 1473, 'months': [1, 2, 3, 4, 5, 6, 7]}], 'warnings': ['内部译员(智云) 有 1 行归属日期晚于今天（样例 2026-10-31），已计入对应未来月、不拦截'], 'run_reasons': ['2 名销售未归属 BU（业务不进任何 BU 页，各 BU 合计小于全公司）'], 'fetch_banners': [], 'metrics': {'built_at': '2026-07-28 18:40:28', 'version': '2.7.2', 'update_ms': 0, 'fetch_fail_rate': 0}, 'schedule': {'date': '2026-07-28', 'planned': ['09:30'], 'success': [], 'pending': [], 'missed': [], 'last_tick': '2026-07-28 18:40', 'last_fire': '2026-07-28 18:40 started→09:30', 'last_busy': ''}, 'business_gaps': {'manual_missing_months': [], 'manual_missing_count': 0, 'manual_impact': '缺月按 0 计：生产成本手填、营销/管理/研发人力、财务费用补充、其他损益等偏低，税前利润可能偏高；补录后请点「更新数据」。', 'manual_owner': '管理会计 · 管理端「人工填写」按月补录', 'unassigned_count': 2, 'unassigned_orders_by_period': {'2026年': '¥0.1万', '2026年Q1': '¥0.0万', '2026年Q2': '¥0.0万', '2026年Q3': '¥0.1万', '2026年1月': '¥0.0万', '2026年2月': '¥0.0万', '2026年3月': '¥0.0万', '2026年4月': '¥0.0万', '2026年5月': '¥0.0万', '2026年6月': '¥0.0万', '2026年7月': '¥0.1万', '2026年1-2月': '¥0.0万', '2026年1-3月': '¥0.0万', '2026年1-4月': '¥0.0万', '2026年1-5月': '¥0.0万', '2026年1-6月': '¥0.0万', '2026年1-7月': '¥0.1万', '2026年2-3月': '¥0.0万', '2026年2-4月': '¥0.0万', '2026年2-5月': '¥0.0万', '2026年2-6月': '¥0.0万', '2026年2-7月': '¥0.1万', '2026年3-4月': '¥0.0万', '2026年3-5月': '¥0.0万', '2026年3-6月': '¥0.0万', '2026年3-7月': '¥0.1万', '2026年4-5月': '¥0.0万', '2026年4-6月': '¥0.0万', '2026年4-7月': '¥0.1万', '2026年5-6月': '¥0.0万', '2026年5-7月': '¥0.1万', '2026年6-7月': '¥0.1万'}, 'unassigned_impact': '未归属销售的下单/收入只在整体页，不进任何 BU 页；整体合计会大于各 BU 之和。', 'unassigned_owner': '设置 · 销售归属 BU', 'ledger_fallback': False, 'ledger_fallback_as_of': '', 'ledger_fallback_data_end': '', 'ledger_fallback_text': '', 'ledger_fallback_owner': ''}, 'info': []}}
old_health_status=404
refresh_status_v1={'status': 200, 'text': '{"running":true,"refreshing":{"started_at":"2026-07-28 18:40:28","trigger":"schedule"},"last":null,"built_at":"2026-07-28 18:40:28","zhiyun_auto_fetch":true}'}
found refresh control text=更新数据
admin ledger url=http://127.0.0.1:8018/admin/review/ledger
```
