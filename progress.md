> **现网 SSOT 不在本文件**：请先看**项目根** `../progress.md` 顶部（VERSION / tip / 生产）。  
> 本文件只记程序仓内施工流水，可落后于项目 progress。

## 2026-08-05 · 3.7.14 审计全量修复（除密码）

- VERSION **3.7.14** · 分支 `task/20260805-audit-fix-3.7.14` · 基线 `32a6a84e5ff24414ff8bbaaac48d6e97a8a40937`
- 004/003/005/006/007/010/017/H20 + DOC/OPS 仓内；preflight 现网仍 gvfs、无 CIFS
- 守卫 `tests/test_audit_3_7_14_backend.py` · `tests/test_audit_3_7_14_frontend.py`
- **未** push / 生产 mount / 改密码契约 / profit 公式
- 候选 tip **`675d4713086abb95bf08a441d4ee8376d883940f`** · 控制卡 REVIEW_READY · **未 push**

## 2026-08-04 · 3.7.13 管理端 PM + 对账体验 + 隔离加固


- VERSION **3.7.13** · tip **`345e604`**（完整 `345e60434a50af65304029137bb0a3080ad805cd`）· 合 main · 基线 `020f547` / 3.7.12
- A1 项目经理入库+只读；A2 修正列表 SO/客户/销售/定位键/原因可搜；A3 禁连点+recompute 后提示；A4 过期疑似人话；B1 沿用 3.7.11 bu=；B2 同键撤销过期疑似；C1 高亮；C2 原值_* 说明
- 守卫 `tests/test_project_manager_3_7_13.py` · `tests/test_adjust_ux_3_7_13.py`（已入 run_verify）
- push origin+gitee main；上机 `publish_kanban.sh --pull` **SUCCESS** · health **200** · runtime 3.7.13/`345e604`
- **未改** profit 公式 / 手填 / HTTPS

## 2026-08-04 · 3.7.12 期间费用构成展示收敛


- VERSION **3.7.12** · tip **`861504d`**（完整 `861504d23b0054f321ea01488421a53711db9ed1`）· 主仓 main（无新 worktree）；基线 `d5a1a63` / 3.7.11
- 去「按部门」展示；BU 藏「按利润中心」；整体 by_pc = 各 BU 分摊后 expense.total；列表与 total 守恒
- 守卫 `tests/test_expense_views_3_7_12.py`；run_verify EXIT:0（1424）；**未改**利润口径 / DailyQuery / 3.7.11 隔离
- push origin+gitee main；上机 `publish_kanban.sh --pull` **SUCCESS** · health **200** · runtime 3.7.12/`861504d`

## 2026-08-04 · 3.7.11 BU 页时间段查询隔离（ISO-01）

- VERSION **3.7.11** · tip **`80b48bf`**（完整 `80b48bf74f8cd514522fb654bf812f43478bb388`）· 主仓 main（无新 worktree）；基线 `872ad12` / 3.7.10
- DailyQuery：BU→`/api/v1/bu_daily`，整体→`/api/v1/daily`；`buildDailyQueryUrl` 共用
- 守卫 `tests/test_bu_daily_iso_3_7_11.py`；`run_verify` EXIT:0（1414）；**未改**利润口径/业务数据
- push origin+gitee main；上机 `publish_kanban.sh --pull` **SUCCESS** · health **200** · runtime 3.7.11/`80b48bf`

## 2026-08-04 · 3.7.10 导出能力文案收敛（三项内容）

- VERSION **3.7.10** · tip **`b02433d`**（完整 `b02433ddfd18307fe800c195d7081fc0e70441ba`；功能 `2b2d5d2`）· 主仓 main 施工（无新 worktree）
- 设置页能力：全部视图 / 管理利润表 / 收单台账明细；去掉导出PNG 勾选与旧四词标签
- 硬规则/权限列/利润口径不变；门禁 1400 EXIT:0；push origin+gitee；上机 SUCCESS（不再本轮 ssh）

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
