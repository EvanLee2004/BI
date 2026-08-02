# G5 交接摘要（EXECUTOR → VERIFIER）

## 候选

- branch: `task/20260802-ui-trust-polish`
- base: `9ca4d456443ec3716da0f26426c1da768b592a87`
- candidate: 805f9e9db0d8fdd9f5a6a9171602a233461ea89e

## 门禁（须 EXIT:0）

```bash
KANBAN_OFFLINE=1 sh tests/run_verify.sh; echo EXIT:$?
cd frontend && npm run typecheck; echo EXIT:$?
cd frontend && npm run build; echo EXIT:$?
git diff --check; echo EXIT:$?
```

## 红→绿

| 主题 | 红 | 绿 |
|------|----|----|
| 凭据 | `cred_red.log` | `cred_green.log` + `test_375_credentials_no_leak.py` |
| 调度 | 旧实现未来槽入 pending/漏跑 | `test_375_schedule_slot_states.py` |
| UI | 组件守卫 | `test_375_ui_components.py` / `test_375_responsive_admin.py` |

## 禁止

- 不 push、不 SSH、不部署、不改生产数据

## 状态

`REVIEW_READY`（门禁全绿后）
