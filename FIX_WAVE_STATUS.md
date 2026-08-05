# FIX WAVE 状态板（Agent 每 Phase 更新）

| Phase | 内容 | 状态 | commit | VERIFY? | 备注 |
|-------|------|------|--------|---------|------|
| 0 | 环境+基线 | done | c02ba6d | BASELINE_VERIFY:1 | HEAD=c02ba6d 祖先 OK；无 audit 包；.venv+npm 已装；全量红因 test_datalayer 并行污染假红（TEST-ENV-001） |
| P1 | FE-001/002/003 | done | bf74fa2 | typecheck 0; fe001+arch 0 | clearDaily 在线路径；顶栏收紧；F-2 扫图表 TS |
| P2 | BE-001~007/011 | done | 2e7fb0a | targeted OK | atomic reapply; 503 recompute; restore gate; schedule on_complete |
| P3 | OPS+TEST-005 | done | e30725a | publish tests OK | runtime align default; KANBAN_PORT; restore PID gate; reload scope; rollback wait |
| P4 | AUTH/SEC | done | b67b9b4 | targeted OK | empty bu_names; cifs env; 403 detail; csrf cookie |
| P5 | FIN | done | c718d09 | money/alloc OK | dual float doc; invalid raise; residual; over100; ledger age; log |
| P6 | TEST 债 | done | 2c07ccc | | verify lock; write-lock false-green removed |
| P7 | docs 对齐 | done | b9173c4 | | VERSION 3.7.16 pointers; Runbook restore note |
| FINAL | 三门禁 | done | 9ad85e1 | TYPECHECK:0 BUILD:0 VERIFY:0 | passed=1508 |

状态枚举：`pending` | `in_progress` | `done` | `blocked`
