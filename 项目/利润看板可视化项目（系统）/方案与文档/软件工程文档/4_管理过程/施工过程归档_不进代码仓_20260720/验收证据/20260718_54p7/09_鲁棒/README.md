# 09 鲁棒（证据路径）

## 本轮实测
- 深链 `/admin/review/orderdept` 直开可加载 + 分页：见 `../04_交互/R00a_results.json`

## 既有单测覆盖（run_verify 日志行）

来源：`../01_红线/run_verify.log`

| 能力 | 测试文件 | 日志命中 |
|------|----------|----------|
| 登录/会话/改密踢会话 | `tests/test_auth.py` | `OK  tests/test_auth.py` |
| 鉴权矩阵 | `tests/test_authz.py` | `OK  tests/test_authz.py` |
| 管理端写/调整 | `tests/test_admin_edit.py` | `OK  tests/test_admin_edit.py` |

完整摘录：[tests_cited.log](./tests_cited.log)

## 未做全量 E2E 的项（诚实）

| 项 | 状态 |
|----|------|
| 表单 XSS 真浏览器注入 | **未测**（依赖后端转义 + 前端无 v-html；无单独 Playwright XSS 脚本） |
| 双击保存幂等 | **未测**真浏览器；依赖调整 API 单测 |
| 双窗并发改数 | **未测** |

技术项未测不假勾为「已手测通过」；以单测绿 + 深链可加载为替代证据。
