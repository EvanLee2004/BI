## 2026-07-31 · 3.6.1 现状（文档收口 · 已 push）
- **3.6.2**（2026-07-31）：重点客户双饼六档 + 说明? + 点饼联动 + 导出同源；VERSION=3.6.2

- **VERSION**=**3.6.1** · tip=`4cb06e1`（docs；其下功能 tip `8ae1796`）· origin=gitee=main
- **已进 main**：首屏六段顺序 一基本情况 → 二下单与回款 → 三重点客户下单情况追踪 → 四经营利润 → 五收入与毛利结构 → 六费用明细；重点客户独立 sec；日查「昨天」；dist 门禁与 3.6.1 交付
- **人看见的文档**：用户手册/FAQ/管理端手册/README/Runbook 对齐 3.6.1；截图仍可能是旧演示批次（诚实标注，待重截）
- **本条=文档收口**，非生产发布

## 2026-07-31 · S-13 CSRF/:8001 Host 端口

仓库：nginx $http_host + XFH；csrf scheme/host/port 规范化；仅 loopback 信转发头；
tests/test_s13_csrf_proxy_host_port.py 入 run_verify。**只 commit 不 push/部署**；生产 nginx-t/reload 待 RELEASER。

## 2026-07-31 · 3.6.0 小修补洞（pending/coalesce + 门禁）

tip 在 bbf5e03 之上：day_summary 未来槽不计 pending；any_success 合并全部 due（含最新）；
test_g4_key_customers_ui 入 run_verify 串行闸；run_verify EXIT:0

## 2026-07-31 · 3.6.0 小修（S-01~S-08 接线 + 重点客户 UI）

基线 tip=`426bebc` 增量施工 · 版本仍 3.6.0
- 调度：ScheduleLoop 读磁盘账本 + plan_catchup；health 传 cfg/root + build_layered_health
- reload：disk commit 非空而 runtime 空 → no_runtime_commit
- 密码：明文 SSOT（set/change/public_row）；verify 可读遗留 PBKDF2
- CSRF：fail-closed；TestClient/ops 白名单；异常 403
- LKG：checksum 校验；save 写 SCHEMA_VERSION；None schema 不兼容
- 重点客户：5 系列样式；无 fen 换算；明细查看/清空筛选；删「年累计仍可很大」；区/图略放大
- `KANBAN_OFFLINE=1 sh tests/run_verify.sh` → EXIT:0

## 2026-07-30 · 3.4.2 重点客户下单分析体验定稿

VERSION=3.4.2 · tip=`f2ec6e1` · tag stage_3_4_2（不推）· 只 commit 不 push
L-A 饼→名单→折线；全开限高；多销售；不预选；去主销售；月高亮；静默文案；run_verify EXIT:0；活体 L1–L9

## 2026-07-30 · 3.4.0 重点客户分析交付
VERSION=3.4.0 · tag stage_3_4_0（不推）· 只 commit 不 push
重点客户：自然年下单预估六档 + 双饼 + 四底；整体+BU；run_verify EXIT:0
