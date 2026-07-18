# 健康监测 · cron 挂载说明（54.8）

## 脚本

- 路径：`deploy/healthcheck.sh`
- 探测：登录页 HTTP 200 + 数据目录最新文件/库是否超过 `MAX_STALE_DAYS`（默认 2 天）
- 失败：写入 `deploy/health_alerts.log`（含时间与原因），exit 1

## 部署机（Ubuntu）示例

```bash
# 每小时整点
0 * * * * BASE=http://127.0.0.1:8018 /path/to/看板正式程序/deploy/healthcheck.sh >>/path/to/看板正式程序/deploy/healthcheck_cron.out 2>&1
```

建议 `BASE` 指向本机反代或直连 API（仅本机环回）。

## 告警日志在哪看

```bash
tail -50 deploy/health_alerts.log
```

## 常见告警

| 日志关键字 | 含义 | 处理 |
|------------|------|------|
| `login_page_not_200` | 服务挂了/端口错 | 看门狗/systemd 是否在跑；`run.py --serve` |
| `data_stale` | 超 2 天没新数据 | 管理端「更新数据」；检查智云/共享盘 |

对应同事话术见 `docs/用户手册/FAQ.md`（黄条/打不开）。
