# MADR 0002：Ubuntu 22.04 上 Python 版本

- **状态**：**SUPERSEDED（2026-07-17 · 任务书50·D.6）** · 原已采纳 2026-07-16 · 任务书40  
- **取代决策**：见 **`0010_python_version_ubuntu26.md`**（部署目标改为 Ubuntu 26.04；系统 python3≥3.12 建 venv，不再默认 deadsnakes）。

---

## 原决策（历史，勿再执行）

- **上下文**：开发机与现网 CI 为 **Python 3.12**；Ubuntu 22.04 系统自带 3.10。
- **决策**：部署机用 **deadsnakes 安装 Python 3.12**，与开发/CI 一致。
- **理由**：requirements 在 3.12 锁定；CI 已是 3.12。
- **后果**：手册曾含 `ppa:deadsnakes/ppa` → `python3.12-venv`。

## 为什么废

1. 明昊拍板部署机 = **Ubuntu 26.04**（系统 python3 已 ≥3.12）。  
2. deadsnakes 对新发行版常无包 / 维护负担。  
3. 统一策略：能系统就系统（见 0010）。
