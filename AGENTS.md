# AGENTS.md · 智能经营罗盘（看板正式程序）

> 精简同步自 `CLAUDE.md`（agents.md 开放标准：https://agents.md）。完整铁律与业务口径以 CLAUDE.md 为准。

## 产品
轻量 BI 经营驾驶舱：读 6 数据源 → 算税前利润 → shell + fragments 组装暗色看板。入口 `python run.py`。

## 铁律（摘要）
1. **前端零金额运算**：JS 只拼 DOM/切 CSS；金额/百分比/宽度 Python 算成显示串。
2. **BU 隔离**：BU 页零跨界全公司 API；数据预挂本页 views。
3. **判绿认真实退出码**：`KANBAN_OFFLINE=1 sh tests/run_verify.sh`，禁止 `| tail`。
4. **无新运行时依赖**：禁 React/npm/新 pip 运行时包；存储键不变；`src/` 零内嵌 HTML、零测试框架名。
5. **敏感数据**：`数据/`、账号/密钥不进 git；合成测试数据可用。
6. **铁律6 UNC**：`config.json` 出厂允许内网 UNC 路径。

## 测试
```bash
KANBAN_OFFLINE=1 sh tests/run_verify.sh; echo $?
.venv/bin/python tests/run_test.py tests/test_xxx.py
```

## 质量闸（开发机）
- pre-commit：ruff / gitleaks / conventional commits（见 `.pre-commit-config.yaml`）
- 配置出处：`方案与文档/…/20260716_软工规范落地包_配置与依据.md`
