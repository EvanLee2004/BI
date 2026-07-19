# MADR-0018：管理端 Element Plus 对齐深空主题（补录）

- **状态**：Accepted（补录）
- **日期**：2026-07-18 · 补录 2026-07-19
- **背景**：管理端 Vue 选型后默认亮色与看端 SciFi 深空割裂。
- **决策**：Element Plus 仅 `/admin` 动态加载；CSS 变量/主题覆盖对齐深空指挥舱；看端不引入 EP。
- **备选**：Naive UI；自写组件（违背不造轮子）。
- **后果**：admin chunk 体积大（可接受）；主题 token 须双端同步改。
- **关联**：`0013_admin_element_plus.md` · MADR-0013 全文在方案与文档。
