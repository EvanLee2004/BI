#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经营驾驶舱：更新管道 + 出 HTML；或起内网双端服务。

用法：
  python run.py                 更新一次（跑管道→算利润→写 output/HTML+JSON），默认手动触发
  python run.py --scheduled     同上，触发方式记为 schedule（供 Linux cron 调用）
  python run.py --serve         起 FastAPI 内网服务（用户端 / + 管理员端 /admin），端口见 config
切换测试/正式数据：改 config.json 的 data_dir（+ period_pin），代码不动。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import loaders
import validate  # noqa: E402
import db
import core  # noqa: E402


def run_batch(trigger="manual") -> int:
    """更新一次并写 output/（原 main 行为）。"""
    cfg = loaders.load_config()
    today = loaders.pinned_today(cfg)
    print(f"数据目录：{cfg['data_dir']}  周期基准：{today}")

    # 进门验证：格式不对先拦下，报"哪个源、哪一列、第几行"，不出一份算错的报表
    rep = validate.validate_all(cfg, today.year)
    validate.print_report(rep)
    if rep.errors:
        print(f"\n✗ 数据格式有 {len(rep.errors)} 处问题，先修源文件再跑（定位见上）。本次不生成报表。")
        return 1

    # BU 分页只经 --serve 的 /bu/{token} 出，不落盘 output/（避免 token 命名文件散落）
    summary, html, ing, _bu_pages = core.generate(cfg, today, trigger=trigger)
    print(f"数据库：{db.db_path(cfg)}  台账fetch：{ing['fetch']['status']}（{ing['fetch']['detail']}）")
    print(
        "  标准表："
        + " ".join(f"{k}={v}" for k, v in ing["counts"].items())
        + f"  手填迁移：{ing['migrate_manual']['status']}({ing['migrate_manual']['imported']})"
    )
    _a = ing["adjust"]
    print(f"  运行结果：{ing['result']}  调整：套用{_a['applied']}/过期{_a['expired']}/剔除{_a['removed']}")

    out_dir = ROOT / cfg["output_dir"]
    out_dir.mkdir(exist_ok=True)
    json_path = ROOT / cfg["output_json"]
    json_path.parent.mkdir(exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = out_dir / cfg["output_html"]
    html_path.write_text(html, encoding="utf-8")

    h = summary["meta"]["health"]
    print("\n=== 数据体检 ===")
    for s in h["sources"]:
        ms = "、".join(f"{m}月" for m in s["months"]) or "无"
        print(f"  {s['name']:<24} {s['rows']:>6} 行  覆盖: {ms}")
    if h["warnings"]:
        print("  ⚠ 需注意：")
        for w in h["warnings"]:
            print(f"    - {w}")
    else:
        print("  ✓ 无异常")

    yp = summary["periods"][summary["meta"]["year_key"]]
    print(f"\n=== {yp['label']} 累计 ===")
    print(
        f"  收入 {yp['revenue_net'] / 1e4:,.1f}万  毛利率 {yp['gross_margin_pct']}%  "
        f"税前利润 {yp['pretax_profit'] / 1e4:,.1f}万 ({yp['pretax_margin_pct']}%)"
    )
    print(f"\n✓ HTML → {html_path}  ({html_path.stat().st_size:,} bytes)")
    return 0


def serve() -> int:
    import server

    server.serve()
    return 0


def main(argv) -> int:
    if "--serve" in argv:
        return serve()
    if "--scheduled" in argv:
        return run_batch(trigger="schedule")
    return run_batch(trigger="manual")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
