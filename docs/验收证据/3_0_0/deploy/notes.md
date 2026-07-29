# 3.0.0 G6 部署机浏览器 notes

环境：http://192.168.30.46 · VERSION=3.0.0 · tip=9e90fbc · 账号 liminghao（管理员）

## 轮次 1
| 图 | 看到了什么 | 合格 |
|----|------------|------|
| r1_overall.png | 整体 KPI 万级 + v3.0.0 | 是 |
| r1_bu_data.png | BU 数据有数 | 是 |
| r1_bu_game.png | BU 游戏有数 | 是 |
| export.html/png | ~10MB HTML · ~6MB PNG | 是 |

## 轮次 2
同轮次 1 再绿。

## 结论
部署机浏览器两轮合格。

## log
```
BASE=http://192.168.30.46 cookie_len=145 VERSION=3.0.0 tip=9e90fbc user=liminghao
health=黄 built_at=2026-07-29 11:07:06
session=b'{"account":"liminghao","display":"liminghao","perm":"\xe7\xae\xa1\xe7\x90\x86\xe5\x91\x98","bus":[],"is_admin":true,"can_main":true}'
=== ROUND 1 ===
r1_overall.png: kpi_wan=True version=True len=5178
r1_bu_data.png: kpi_wan=True version=True len=4432
r1_bu_game.png: kpi_wan=True version=True len=4518
r1_export_html: bytes=10185290 ok=True
r1_export_png: bytes=6127867 ok=True
=== ROUND 2 ===
r2_overall.png: kpi_wan=True version=True len=5178
r2_bu_data.png: kpi_wan=True version=True len=4432
r2_bu_game.png: kpi_wan=True version=True len=4518
r2_export_html: bytes=10185290 ok=True
r2_export_png: bytes=6126194 ok=True
```
