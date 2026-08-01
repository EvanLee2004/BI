# MADR-0031 · 单机候选预热与 nginx 切流（3.7.3）

> 状态：Accepted · 2026-08-01  
> 承接：MADR-0030（半原子备份+门闸）

## 背景

3.7.0 解决了「无备份不上机」和「无 runtime 对齐不宣称成功」，但仍是 **先改磁盘再 kill/restart 主进程**，坏版本会直接顶上现网。完整双机蓝绿不现实（单机 + SQLite）。

## 决策

1. **旁路预热端口**（默认 8019）  
   同工作树新代码以 `KANBAN_CANDIDATE=1` 启动：跳过 `boot_first_refresh` 与 `schedule_loop`，只验证 HTTP 栈 + runtime 标记与磁盘 version/commit 对齐。

2. **失败不碰主流量**  
   候选失败 → 杀旁路；若本次已 `git pull` → `reset --hard` 到 prev；主 8018 进程保持。

3. **切流两档**  
   - 默认：预热 OK → `reload_kanban.sh` 换主进程 → 杀候选（仍有短窗口断连，但坏版本不会启动）。  
   - `--nginx-cutover`：upstream include 先指候选 → reload 主 → 再指回主端口（近零断流；需 sudo nginx）。

4. **nginx**  
   `upstream` 抽到 `deploy/linux/kanban_upstream.inc`；主 conf `include` 该文件。上机需同步 conf + include。

## 非目标

- 双机 / 双 SQLite 写者  
- 自动回滚业务库（仍靠备份脚本人工恢复）  
- P0 HTTPS / 口令

## 后果

- VERSION **3.7.3**  
- 标准发版：`bash deploy/linux/publish_kanban.sh --pull`  
- 可选：`--nginx-cutover`（首次须 conf 已 include）  
