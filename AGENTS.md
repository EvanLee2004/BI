# AGENTS.md · 智能经营罗盘（看板正式程序）

> 精简同步自 `CLAUDE.md`（agents.md 开放标准：https://agents.md）。完整铁律与业务口径以 **CLAUDE.md** 为准。

## 产品

轻量 BI 经营驾驶舱：读 6 数据源 → SQLite 分整数 → profit/domain 算账 → **Vue3 看端 + 管理端 SPA** + API v1 VM。  
入口：`python run.py` / `python run.py --serve`。  
**当前版本**：见根目录 `VERSION`（现 **2.6.0**）：统一 `/login`、会话 cookie **`kanban_sid`**（旧 cookie 兼容读 21 天）。历史 tag 仅本地、不推远端。

## 架构（摘要）

```
抓数 → 数据/ → ingest → SQLite → profit/domain → viewmodels/API → frontend/dist (nginx 或 /app)
```

- 路由：`src/routes/*`；装配：`server.create_app`
- 费用图/明细默认口径：`domain.expense.chart_whitelist`（剔成本/非利润表）
- 工资大类全端隐藏并入「其他」

## 铁律（摘要）

1. **前端零金额运算**：金额/百分比后端成显示串；`*_disp` 已含单位则禁再拼「万」。
2. **BU 隔离**：BU 页零跨界全公司敏感数据。
3. **判绿认真实退出码**：`KANBAN_OFFLINE=1 sh tests/run_verify.sh; echo $?`，禁止 `| tail`。
4. **依赖**：Python 运行时见 `requirements.txt`；前端 **允许** Vue/npm 构建（产物进 dist）；不引 Docker。
5. **敏感数据**：`数据/`、账号/密钥、前端错误.log 不进 git；合成测试数据可用。
6. **铁律6 UNC**：`config.json` 出厂允许内网 UNC / 智云表 ID；密码/token 绝不进库。
7. **口径计算区禁区**：golden / 32 周期红线零未授权 diff。
8. **C901 豁免仅纯分发壳**（`routes/*/register`、`create_app`）。

## 测试

```bash
KANBAN_OFFLINE=1 sh tests/run_verify.sh; echo $?
.venv/bin/python tests/run_test.py tests/test_xxx.py
```

## 质量闸

- pre-commit：ruff / gitleaks / conventional commits（`.pre-commit-config.yaml`）
- 安全扫证据：`docs/验收证据/57_安全/`
- 断点续跑：`docs/57_总控勾选.md`
