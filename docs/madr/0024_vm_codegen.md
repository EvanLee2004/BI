# MADR-0024 VM 字段清单自动生成

- Status: Accepted
- Date: 2026-07-21
- Decision: `scripts/gen_vm_ts.py` 从 pydantic `model_fields` 写 vm.ts GEN 块；verify `--check`。
- Consequences: 后端增字段忘记同步前端会红。
