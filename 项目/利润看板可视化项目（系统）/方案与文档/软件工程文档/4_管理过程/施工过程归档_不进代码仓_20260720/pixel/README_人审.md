# 像素/人审说明（任务书50）

- 对比对象：Vue 真组件 + ECharts（相对 legacy SVG 预期有图表渲染差异）。
- 可接受差异：趋势/回款/费用/环形/双血条改 ECharts 画布；布局用真组件非 v-html 字符串。
- 不可接受：数字与口径变化（本轮未改 profit 算法）；明细出现隐藏列。
- 截图文件：vue_overall_{light,dark}_{1440,375}.png、vue_bu_dark_1440.png
