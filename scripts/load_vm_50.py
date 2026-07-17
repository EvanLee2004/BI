#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书50·E：已登录 50 并发 × 2 分钟打 /api/v1/vm/cockpit，报告 P95/错误率/QPS。

用法（服务须已起且 KANBAN_OFFLINE=1 推荐）：
  .venv/bin/python scripts/load_vm_50.py --base http://127.0.0.1:8018 \\
      --user overall --password 8888 --concurrency 50 --seconds 120 \\
      --out docs/20260717_负载报告_50并发.md
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from pathlib import Path

import httpx


async def worker(
    client: httpx.AsyncClient,
    cookie: str,
    url: str,
    stop_at: float,
    latencies: list[float],
    codes: list[int],
):
    headers = {"Cookie": cookie}
    while time.perf_counter() < stop_at:
        t0 = time.perf_counter()
        try:
            r = await client.get(url, headers=headers, timeout=30.0)
            codes.append(r.status_code)
        except Exception:
            codes.append(0)
        latencies.append((time.perf_counter() - t0) * 1000.0)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8018")
    ap.add_argument("--user", default="overall")
    ap.add_argument("--password", default="8888")
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--out", default="docs/20260717_负载报告_50并发.md")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    async with httpx.AsyncClient() as client:
        lr = await client.post(
            f"{base}/api/v1/login",
            json={"account": args.user, "password": args.password},
            timeout=30.0,
        )
        if lr.status_code != 200:
            raise SystemExit(f"login failed: {lr.status_code} {lr.text}")
        # 取 cookie
        cookie_parts = []
        for k, v in lr.cookies.items():
            cookie_parts.append(f"{k}={v}")
        # 也从 set-cookie 兜底
        cookie = "; ".join(cookie_parts)
        if not cookie:
            # starlette may put in headers
            sc = lr.headers.get("set-cookie") or ""
            cookie = sc.split(";")[0] if sc else ""
        if not cookie:
            raise SystemExit("login ok but no cookie")

        url = f"{base}/api/v1/vm/cockpit"
        latencies: list[float] = []
        codes: list[int] = []
        stop_at = time.perf_counter() + args.seconds
        t0 = time.perf_counter()
        await asyncio.gather(
            *[
                worker(client, cookie, url, stop_at, latencies, codes)
                for _ in range(args.concurrency)
            ]
        )
        elapsed = time.perf_counter() - t0

    n = len(codes)
    ok = sum(1 for c in codes if c == 200)
    err = n - ok
    err_rate = (err / n * 100.0) if n else 100.0
    qps = n / elapsed if elapsed else 0.0
    p50 = statistics.median(latencies) if latencies else 0
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0)
    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else (max(latencies) if latencies else 0)

    lines = [
        f"# 负载报告 · 50 并发 × {args.seconds}s · `/api/v1/vm/cockpit`",
        "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- base：`{base}`",
        f"- 账号：`{args.user}`（已登录拿会话 cookie，**全部请求须 200**）",
        f"- 并发：{args.concurrency}",
        f"- 时长：{args.seconds}s（实测 wall {elapsed:.1f}s）",
        f"- 总请求：{n}",
        f"- HTTP 200：{ok}",
        f"- 非 200 / 异常：{err}",
        f"- 错误率：{err_rate:.3f}%",
        f"- QPS：{qps:.1f}",
        f"- 延迟 P50：{p50:.1f} ms",
        f"- 延迟 P95：{p95:.1f} ms",
        f"- 延迟 P99：{p99:.1f} ms",
        "",
        "## 判定",
        "",
        f"- {'✅ 全部 200' if err == 0 and n > 0 else '❌ 存在失败（不可用 401 串行 curl 冒充）'}",
        "",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    if err or n == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
