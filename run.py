#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经营驾驶舱 v6 一键生成：读 6 个数据源 → 算利润 → 出自包含 HTML。

用法：  python run.py
切换测试/正式数据：改 config.json 的 data_dir（+ period_pin）即可，代码不动。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import loaders, profit, render, assets, validate  # noqa: E402


def main() -> int:
    cfg = loaders.load_config()
    today = loaders.pinned_today(cfg)
    ledger_year = today.year

    print(f"数据目录：{cfg['data_dir']}  周期基准：{today}")

    # 进门验证：格式不对先拦下，报"哪个源、哪一列、第几行"，不出一份算错的报表
    rep = validate.validate_all(cfg, ledger_year)
    validate.print_report(rep)
    if rep.errors:
        print(f"\n✗ 数据格式有 {len(rep.errors)} 处问题，先修源文件再跑（定位见上）。本次不生成报表。")
        return 1
    project = loaders.load_project_detail(cfg)
    orders = loaders.load_orders(cfg)
    receipts = loaders.load_receipts(cfg)
    inhouse = loaders.load_inhouse(cfg)
    lheader, lrows = loaders.load_ledger(cfg, str(ledger_year))
    print(f"读入：项目明细{len(project)} 下单{len(orders)} 回款{len(receipts)} 内部译员{len(inhouse)} 台账{len(lrows)}")

    summary = profit.build_summary(cfg, project, orders, receipts, inhouse, lheader, lrows, ledger_year, today)

    out_dir = ROOT / cfg["output_dir"]
    out_dir.mkdir(exist_ok=True)
    json_path = ROOT / cfg["output_json"]
    json_path.parent.mkdir(exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    logo = assets.load_logo_base64(cfg)
    html = render.render_dashboard(summary, cfg, logo)
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
    print(f"  收入 {yp['revenue_net']/1e4:,.1f}万  毛利率 {yp['gross_margin_pct']}%  "
          f"税前利润 {yp['pretax_profit']/1e4:,.1f}万 ({yp['pretax_margin_pct']}%)")
    print(f"\n✓ HTML → {html_path}  ({html_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
