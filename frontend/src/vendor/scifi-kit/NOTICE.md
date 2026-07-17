# SciFi Kit vendor notice

- **Upstream**: [soyunomas/Dynamic-SciFi-Dashboard-Kit](https://github.com/soyunomas/Dynamic-SciFi-Dashboard-Kit)
- **License**: MIT (see `LICENSE`)
- **Vendored**: 2026-07-18 · 任务书54·B
- **What we use**: CSS panel chrome (`.dsdk-panel*` variables/classes). Data charts stay **ECharts**; kit Canvas graph widgets are **not** used for money series.
- **JS**: Not vendored — Vue `SciFiPanel.vue` rebuilds the shell markup; kit JS only drives demo panel constructors we do not need.
