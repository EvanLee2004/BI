# MADR 0004：存储抽象不引 ORM，SQL 收敛到 db 层

- **状态**：已采纳（2026-07-16 · 任务书43）
- **上下文**：长期 SQLite；未来可能换库；业务层曾散落 execute。

## 决策

1. **不引入 SQLAlchemy/其它 ORM**（无新 pip 依赖）。  
2. SQL 只进 `src/db.py` + `src/db_write.py` + `src/schema.py`；`profit`/`routes`/`ingest` 等业务/管道**零裸 SQL**（守卫测试）。  
3. 真换库时再评估 ORM；现阶段函数层 + 方言清单足够。

## 理由

- 现有代码与测试高度绑定 sqlite3 API 与 INTEGER 分存储；ORM 迁移成本高、收益低。  
- 收敛 SQL 已消除业务层字面量，换库时改点集中。

## 后果

- 动态表名/列名必须经白名单（`STD_TABLE_NAMES` / `ADJUSTABLE_FIELDS`）。  
- 新查询优先加 `db`/`db_write` 函数，禁止在 routes 拼 SQL。
