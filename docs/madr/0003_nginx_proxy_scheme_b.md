# MADR 0003：前后端分离用 nginx 反代（方案 B），不用双端口跨域

- **状态**：已采纳（2026-07-16 · 任务书43）
- **上下文**：长期生产部署在 Ubuntu 台式机；需静态与 API 进程分离、仅对外开 80。

## 决策

采用 **nginx :80 伺服 static + 反代动态路径到 127.0.0.1:8018**；后端进程只绑回环。  
保留 **直连模式**（`server_host=0.0.0.0` + `serve_static=true`，FastAPI 自挂 `/static`）作开发/无 nginx 环境兼容。

## 理由

1. 同源：浏览器只打 80，无 CORS / 双端口跨域配置。
2. 发行版 nginx 标配（gzip、缓存、真实 IP），不造轮子。
3. 后端不暴露局域网 8018，攻击面缩小。
4. 双模：config 可切回直连，测试与 Windows legacy 不破。

## 后果

- 部署多一步 `nginx` 安装与 `nginx -t`；手册已写。
- `serve_static=false` 时本机直连 8018 仅 API/壳路由，静态由 nginx 负责。

## 未选

- **双端口跨域**（8018 API + 另一端口静态）：需 CORS、cookie 域复杂。  
- **Docker/K8s**：现阶段裸机 systemd 最简。
