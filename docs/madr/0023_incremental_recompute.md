# MADR-0023 手填增量重算（跳过 std 重建）

- Status: Accepted
- Date: 2026-07-21
- Decision: 源文件指纹未变时 `do_recompute(rebuild_std=False)` 只 summary；调整写入 `rebuild_std=True`。
- Consequences: 手填耗时数量级下降；等价性测试锁定数字一致。
