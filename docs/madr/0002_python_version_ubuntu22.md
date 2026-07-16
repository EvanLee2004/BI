# MADR 0002：Ubuntu 22.04 上 Python 版本

- **状态**：已采纳（2026-07-16 · 任务书40）
- **上下文**：开发机与现网 CI 为 **Python 3.12**；Ubuntu 22.04 系统自带 3.10。

## 决策

部署机用 **deadsnakes 安装 Python 3.12**，与开发/CI 一致（选项 a）。不强制证明 3.10 全量兼容。

## 理由

1. `requirements.txt` 与运行时在 3.12 上锁定与验收；跨小版本（3.10 vs 3.12）类型注解/`|` 联合类型等已在代码中使用，降级成本高。
2. CI（`.github/workflows/verify.yml`）已是 `python-version: "3.12"`——**CI 绿 ≈ 目标平台绿**。
3. deadsnakes 为社区常用路径，手册给可复制命令。

## 后果

- 手册必含：`ppa:deadsnakes/ppa` → `python3.12` + `python3.12-venv`。
- 不引入 Docker；裸机 venv 即可。
- 将来若官方镜像统一 3.12，可删 deadsnakes 步骤。

## 未选

- **(b) 证明 3.10 兼容**：本任务书时限内不硬证；若业务强制系统 Python，另开兼容批次。
