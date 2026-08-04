> **现网 SSOT 不在本文件**：请先看**项目根** `../progress.md` 顶部（VERSION / tip / 生产）。  
> 本文件只记程序仓内施工流水，可落后于项目 progress。

## 2026-08-04 · 3.7.9 能力矩阵收敛（施工 REVIEW_READY 候选）

- VERSION **3.7.9** · 分支 `task/20260804-caps-simplify` · worktree `kanban-379-caps-simplify`
- 权限管看范围；用户能力仅四导出；管理类绑管理员硬规则；设置页 UI 收敛
- 证据 `docs/验收证据/3_7_9/`；**未** push / SSH / 部署

## 2026-08-03 · 文档 100% 对齐 3.7.7（续 · 工程图+全量 UI）

- 全部 `docs/设计图/*.mmd` 更新为 3.7.7 口径并 mermaid 重渲 SVG → `docs/images/*.png`
- UI 全量：登录/三主题/KC/利润/结构/费用/手机/管理端；手册截图同步
- README / FIGURES 嵌新图；**未改**业务代码

## 2026-08-03 · 文档与配图对齐 3.7.7（DIRECTOR · 只改文档/截图）

- 本机 `KANBAN_PROFILE=dev KANBAN_OFFLINE=1` golden 起服，Playwright 重采 `docs/images/ui/*` + 用户手册截图；证据 `docs/验收证据/3_7_7/`
- 更新：根 README、用户手册三件套、Runbook §0、FIGURES、方案与文档地图、教学说明头、多处 VERSION 指针 → **3.7.7**
- **未改**业务代码 / 未 push / 未部署

## 2026-08-02 · 3.7.7 桌面优先 Logo + cache-bust + P1

- VERSION **3.7.7** · 分支 `task/20260802-desktop-polish-logo`
- Logo 桌面 42 / 窄屏 34；theme.css ?v=；P1 可读；门禁 EXIT:0

## 2026-07-31 · 3.6.1 现状（文档收口 · 已 push · 历史）

- **3.6.2**（2026-07-31）：重点客户双饼六档 + 说明? + 点饼联动 + 导出同源；VERSION=3.6.2
- 当时 VERSION=3.6.1；首屏六段已定型。截图重采已于 **2026-08-03** 完成（见上条）。

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
