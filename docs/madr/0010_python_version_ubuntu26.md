# MADR-0010：Ubuntu 26.04 上 Python 版本

- **状态**：Accepted · 2026-07-17 · 任务书50·D.6（明昊拍板部署目标 Ubuntu 26.04）
- **取代**：`0002_python_version_ubuntu22.md`（SUPERSEDED）

## 上下文

- 开发机 / CI = **Python 3.12**（`requirements.txt` 与类型注解按 3.12 锁定）。
- 部署机已定为 **Ubuntu 26.04 LTS**（2026-07-17 明昊拍板；此前「按 22.04 做」作废）。
- Ubuntu 26.04 **系统 `python3` 已 ≥ 3.12**，无需再默认走 deadsnakes PPA（新发行版上 deadsnakes 常无对应包）。

## 决策

1. **优先系统 Python**：`python3 --version` 主版本 ≥ 3.12 时，直接：
   ```bash
   python3 -m venv .venv
   ```
2. **判定命令（装依赖前必跑）**：
   ```bash
   python3 --version   # 期望 Python 3.12.x 或更高 3.x
   ```
   若输出 < 3.12：先 `sudo apt install -y python3 python3-venv python3-dev` 再验；仍不够再查发行版包（**不默认** `ppa:deadsnakes`）。
3. CI 继续 `actions/setup-python` 的 `3.12`（与产品锁定一致）；**不**把 CI runner 强绑 26.04 镜像号（`ubuntu-latest` 即可，解释器版本对齐即可）。

## 理由

- 少一层 PPA = 少一层供应链与 apt 失败面。
- 系统 python3 已满足产品下限，与「裸机 venv、不 Docker」一致。
- 22.04 旧文档/脚本中的 deadsnakes 步骤仅作历史；新部署一律按本 MADR。

## 后果

- `docs/Ubuntu部署手册.md`、`docs/opencode部署提示词_Ubuntu_*.md`、`deploy/linux/*` 注释统一写 **26.04 + 系统 python3**。
- Playwright 系统库：**优先** `.venv/bin/playwright install-deps chromium`（不硬编码 22.04 包名/t64 清单）。

## 未选

- 继续默认 deadsnakes：在 26.04 上多余且易失败。
- 降级兼容 3.10：成本高，不在本批次范围。
