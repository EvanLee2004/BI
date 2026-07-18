# 测试怎么跑

## 日常全量（每个代码批次收口）

```bash
KANBAN_OFFLINE=1 sh tests/run_verify.sh
echo EXIT:$?
# 必须 EXIT:0；禁止 | tail / | head
```

单文件：

```bash
.venv/bin/python tests/run_test.py tests/test_auth.py
```

---

## 批次级大验（大批次收口时 · 54.8 起）

**不**进 `run_verify.sh`（保持日常速度）。服务先起：

```bash
KANBAN_OFFLINE=1 KANBAN_FRONTEND=vue KANBAN_PORT=8018 .venv/bin/python run.py --serve
```

另开终端：

```bash
# 性能（首屏/入口/orderdept；默认跳过 10 分钟长会话）
KANBAN_BASE=http://127.0.0.1:8018 .venv/bin/python tests/perf_check.py
echo EXIT:$?

# 鲁棒（深链 F5 / 坏输入 / 双击）
KANBAN_BASE=http://127.0.0.1:8018 .venv/bin/python tests/robust_check.py
echo EXIT:$?
```

### 结果怎么读

- 控制台打印 `| 指标 | 阈值 | 实测 | 结论 |`
- 同时写 `docs/验收证据/20260718_54p8/perf_check.json` · `robust_check.json`（若目录存在）
- **硬阈值失败** → 脚本 exit 1（例如登录 idle >3s、orderdept >2s、pageerror）
- `PERF_SKIP_LONG=1`（默认）跳过 10 分钟内存项

---

## 证据与前端

- Playwright 像素/任务书证据：`tests/frontend/playwright_*.py`
- 前端结构守卫：`tests/frontend/parity/`
