# optional tests

不进默认 `tests/run_verify.sh`。需本机服务 / Playwright / 活体浏览器时手工跑：

```bash
KANBAN_OFFLINE=1 .venv/bin/python -m unittest discover -s tests/optional -v
```

- `test_e2e_auth_isolation_2_6_4.py`：Playwright 鉴权隔离
- `test_task54p14_live_optional.py`：活体可选
