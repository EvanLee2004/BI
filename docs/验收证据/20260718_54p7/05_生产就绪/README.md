# 05 生产就绪

## 控制台（AC5）

- **捕获方式**：Playwright `page.on('console')` + `page.on('pageerror')`，管理端走查（七 tab 暗/亮 + orderdept）
- **文件**：[console_capture.json](./console_capture.json)
- **结论**：
  - `page_errors` = **0**
  - JS 级 console.error = **0**（`console_js_clean=true`）
  - 另有 5 条 `Failed to load resource: 401/404` 网络噪声（未登录资源/缺资源），**归因：鉴权/静态 404，非业务脚本异常**

## 鉴权矩阵（未登录 / 整体 / BU / 管理员）

- **文件**：[auth_matrix_full.json](./auth_matrix_full.json) · [auth_matrix.log](./auth_matrix.log)
- **摘要**：
  - noauth：accounts/cockpit/detail → **401**
  - overall：cockpit **200**；accounts/detail/settings → **401**
  - bu：cockpit **403**；accounts/settings **401**；他 BU **403**
  - admin：accounts/settings/vm → **200**

## shell 残留

- `static/shell*.html`：**无文件**
