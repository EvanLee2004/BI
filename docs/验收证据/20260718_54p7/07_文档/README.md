# 07 文档终验（抽查命令）

在 `程序/看板正式程序/` 执行：

```bash
# 1) 54.6 交付报告在仓
test -f docs/历史批次/20260718_任务书54.6交付报告.md && echo OK_54p6_report

# 2) README 跑法关键字
rg -n "run_verify|KANBAN_OFFLINE|--serve" README.md | head

# 3) 接口清单路径（项目树，仓外）
test -f ../../方案与文档/软件工程文档/2_设计/07_HTTP接口清单_全端点.md && echo OK_http_list

# 4) CHANGELOG 镜像
test -f docs/CHANGELOG_stage54系列补记.md && echo OK_changelog_mirror

# 5) 像素证据
test -d docs/pixel/vue54p5 && echo OK_vue54p5
```

本环境复跑结果见 [doc_spotcheck.log](./doc_spotcheck.log)。
