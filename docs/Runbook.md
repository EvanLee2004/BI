# Runbook：三张处方卡

## 1. 服务挂了

1. 看进程：`ps aux | grep run.py` / systemd `systemctl status kanban`
2. 看日志：`数据/日志/kanban.log` 或 nohup 日志
3. 健康：`curl -s http://127.0.0.1:8018/api/health | head`
4. 重启：`.venv/bin/python run.py --serve`（或 systemd restart）
5. 若 503 数据未生成：`POST /api/refresh`（管理员）或本地 `python run.py`

## 2. 回滚版本

1. `git tag -l 'stage46-*'` / 业务 tag
2. `git checkout <tag>`（或部署包切版本）
3. 恢复 `数据/看板.db` 与 `数据/看板账号.json` 备份
4. 重启服务，curl `/api/health` 绿/黄可接受
5. 口径配置：任务书54 起管理端 UI/API 已下线；引擎默认直通。紧急改口径仅运维层（代码默认值 / DB `cfg_口径配置`，见 MADR-0011）

## 3. 备份恢复

1. 备份位置：`数据/备份/`（日更管道产出）
2. 恢复：拷贝 `看板.db` 到 `数据/`（先停服务）
3. 演练：`python tests/run_test.py tests/test_backup_restore.py`
4. 起服后 `/api/health` + 登录抽查 KPI
