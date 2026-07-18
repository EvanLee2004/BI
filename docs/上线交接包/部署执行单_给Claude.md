# 部署执行单 · 给 Claude / 部署执行方（v2.0.0-rc1）

> 仅在**明昊人审签字**后执行。本单**不**代替人审。  
> 工作目录：`程序/看板正式程序/`。双远端：GitHub `origin` + Gitee（见 README / config `update_remote`）。

---

## A. Push 前安全检查（必做）

```bash
cd 程序/看板正式程序
git status
git log -1 --oneline
git tag -l stage55_rc1

# 1) 无未提交必交物
# 2) diff 无真实客户名 / 真实金额明细 / 内网账号密码（种子默认账号 README 除外）
git diff origin/main..HEAD --stat | head -40

# 3) 禁止：push --tags 误推开发 tag 策略按项目规矩——本项目只推 main 内容，tag 是否推送以明昊当次指示为准
# 4) 确认 VERSION 为 2.0.0-rc1
cat VERSION
```

**不通过则只 commit 不 push，并写原因。**

---

## B. Push 命令（签字后）

```bash
# 推 main（示例；实际 remote 名以机器为准）
git push origin main
# 若需双推 Gitee：
# git push gitee main

# tag（若当次授权推 tag）
# git push origin stage55_rc1
```

---

## C. 部署机步骤（Ubuntu · 摘要）

权威细节：`docs/Ubuntu部署手册.md` · `docs/Runbook.md` · `deploy/linux/` · `deploy/healthcheck_cron说明.md`。

1. **备份**：数据目录与当前 `看板.db`（路径在 `数据/` 或部署约定目录）  
2. **拉取**：`git pull` 到含 `2.0.0-rc1` 的 commit / 或 checkout `stage55_rc1`  
3. **venv**：`pip install -r requirements.txt`（可走国内镜像）  
4. **前端**：若部署用 dist，确认 `frontend/dist` 已随仓或本机 `npm run build`  
5. **systemd / 服务**：重启看板服务（`run.py --serve` 或 unit 文件）  
6. **nginx**：按 `deploy/linux/nginx-kanban.conf` 反代（若生产模式）  
7. **cron**：  
   - 健康检查：`deploy/healthcheck.sh`（见 `healthcheck_cron说明.md`）  
   - 日更：管理端设置的计划时间  
8. **BIOS 来电自启**：提醒机房/IT 确认（防断电不回）  

---

## D. 冒烟清单（部署后 5 分钟）

| # | 项 |
|---|-----|
| 1 | 登录页 200；看端整体账号能进 |
| 2 | 管理端进入；下单未填部门秒开 |
| 3 | 管理端「更新数据」能跑通或黄条降级可解释 |
| 4 | `bash deploy/healthcheck.sh` EXIT 0 |
| 5 | 版本显示 `2.0.0-rc1` / 发布候选 |

---

## E. 回滚锚点

| tag | 含义 |
|-----|------|
| **`stage55_rc1`** | 本封板点（先回到这里再诊断） |
| `stage54p9` | 美学终修末 |
| `stage54p7` | 终验上线就绪 |
| **`stage54p3`** | 较早稳点（任务书示例回滚锚） |

```bash
# 示例：回退代码到封板前一版（数据目录勿删）
git fetch
git checkout stage54p7   # 或 stage54p3
# 重启服务
```

**数据**：回滚代码后用备份 `看板.db` 恢复；勿把真实数据推 git。

---

## F. 非目标

本单执行方**不**改业务口径、不扩功能、不定稿陆总公告。
