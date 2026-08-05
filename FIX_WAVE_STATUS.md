# FIX WAVE 状态板（Agent 每 Phase 更新）

| Phase | 内容 | 状态 | commit | VERIFY? | 备注 |
|-------|------|------|--------|---------|------|
| 0 | 环境+基线 | done | c02ba6d | BASELINE_VERIFY:1 | HEAD 祖先 c02ba6d；无 audit 包 |
| P1 | FE-001/002/003 | done | 73e8b67 | typecheck 0 | clearDaily；TopBar；F-2 图表 TS |
| P2 | BE-001~007/011 | done | 9b6c990 | targeted | atomic reapply；503 recompute；restore gate |
| P3 | OPS+TEST-005 | done | 5b21ddc | publish OK | runtime align 默认；KANBAN_PORT |
| P4 | AUTH/SEC | done | d10deb1 | targeted | empty bu_names；CIFS env；403；csrf |
| P5 | FIN | done | 5ed3f45 | money OK | as_fen 拒 float；非法金额 raise；分摊边 |
| P6 | TEST 债 | done | 4f8c71f | | verify lock；write-lock 假绿消除 |
| P7 | docs 对齐 | done | f2b3e2b | | VERSION 3.7.16 指针；无 audit 包 |
| FINAL | 三门禁 | pending | | TYPECHECK/BUILD/VERIFY | 修 skeptic 后重跑 |

状态枚举：`pending` | `in_progress` | `done` | `blocked`

## 真实 lineage（c02ba6d..HEAD）

```
913af26 build: refresh frontend dist after fix wave FE changes
3869f3c docs: mark FIX WAVE FINAL gates green
9ad85e1 fix(be): order serve helpers for create_app and turn_off contracts
af3507b fix(be): keep schedule start only in serve(); update catchup mocks
6fb0274 fix(be): use db.commit_immediate for rebuild+adj (no bare SQL)
6e3a9e5 refactor: lower C901 complexity for apply_adjustments and serve
f2b3e2b docs: align version pointers after fix wave
4f8c71f test: eliminate false-green write-lock and gate races
5ed3f45 fix(fin): money ingress, bad amounts, alloc edges, ingest honesty
d10deb1 fix(sec): bu meta isolation and cifs secret channel
5b21ddc fix(ops): candidate gate align and publish safety
9b6c990 fix(be): atomic reapply, honest errors, safe restore, concurrency
73e8b67 fix(fe): clear daily dual across scopes and harden chrome defaults
```
