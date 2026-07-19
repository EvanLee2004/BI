# R-41 C901 豁免最终清单（个位数·均为纯分发壳）

| 位置 | 依据 |
|------|------|
| `src/routes/data_api.py:83:def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |
| `src/routes/admin_pages.py:13:def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |
| `src/routes/config_api.py:16:def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |
| `src/routes/manual.py:52:def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |
| `src/routes/export.py:17:def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |
| `src/routes/cockpit.py:71:def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |
| `src/routes/auth.py:16:def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |
| `src/server.py:275:def create_app(cfg, root=None) -> FastAPI:  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler` | 纯路由/装配分发壳，复杂度在子 handler |

计数: 8

ruff check src/ --select C901 → All checks passed
ruff --ignore-noqa 仅剩 8 个 shell（register×7 + create_app）
