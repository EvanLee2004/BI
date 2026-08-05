# FIX WAVE 状态板（Agent 每 Phase 更新）

| Phase | 内容 | 状态 | commit | VERIFY? | 备注 |
|-------|------|------|--------|---------|------|
| 0 | 环境+基线 | done | c02ba6d | BASELINE_VERIFY:1 | HEAD=c02ba6d 祖先 OK；无 audit 包；.venv+npm 已装；全量红因 test_datalayer 并行污染假红（TEST-ENV-001） |
| P1 | FE-001/002/003 | done | bf74fa2 | typecheck 0; fe001+arch 0 | clearDaily 在线路径；顶栏收紧；F-2 扫图表 TS |
| P2 | BE-001~007/011 | pending | | | |
| P3 | OPS+TEST-005 | pending | | | |
| P4 | AUTH/SEC | pending | | | |
| P5 | FIN | pending | | | 口径敏感 |
| P6 | TEST 债 | pending | | | |
| P7 | docs 对齐 | pending | | | 无 audit 包 |
| FINAL | 三门禁 | pending | | TYPECHECK/BUILD/VERIFY | 全 0 才算完 |

状态枚举：`pending` | `in_progress` | `done` | `blocked`
