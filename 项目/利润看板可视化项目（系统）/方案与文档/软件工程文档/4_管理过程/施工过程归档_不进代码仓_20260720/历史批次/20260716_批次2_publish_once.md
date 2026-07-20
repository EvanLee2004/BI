# 批次 2 · publish-once（2026-07-16）

## 问题
此前 HTTP `/api/v1/cockpit/fragments` 路径：取 publish 全量 fragments → strip 卡字段 → 再 `build_cockpit_views` 重建 views（build-full→strip→rebuild 双倍渲染）。

## 修法
| 点 | 行为 |
|----|------|
| `core.generate` | 一次产出全量 HTML（导出/快照）+ client-ready `_fragments`（已 strip）+ `_views` |
| `core.build_bu_pages` | 每 BU 挂已 strip `fragments` + `views` |
| `refresh_pipeline.publish` | 写入 `_state.fragments` + `_state.views` |
| HTTP 整体/BU fragments | **直接取缓存**；strip 幂等 no-op；仅冷启动缺缓存时现建 |
| `client_strip_fragments` | 幂等；`assert_clean=True` 可抓回潮 |

## 行为不变
golden / 红线 / node-assemble 契约不变；payload 形状不变。

## 测试
`tests/test_publish_once.py`
