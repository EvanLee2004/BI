/**
 * 按时间段查询 URL（3.7.11 · ISO-01）
 *
 * BU 页必须走 bu_daily（本 BU 销售过滤）；整体页走 daily（全公司）。
 * 查询 / 昨天 / 本月 共用本纯函数，禁止业务组件各自拼 path。
 */

export type BuildDailyQueryUrlOpts = {
  scope: string
  buName?: string | null
  start: string
  end: string
  top?: number
}

/**
 * @returns 相对 path+query，如 `/api/v1/bu_daily?bu=…&start=…&end=…&top=2000`
 *          或 `/api/v1/daily?start=…&end=…&top=2000`
 */
export function buildDailyQueryUrl(opts: BuildDailyQueryUrlOpts): string {
  const top = opts.top ?? 2000
  const start = encodeURIComponent(opts.start)
  const end = encodeURIComponent(opts.end)
  const t = encodeURIComponent(String(top))
  const bu = (opts.buName || '').trim()
  if (opts.scope === 'bu' && bu) {
    return (
      `/api/v1/bu_daily?bu=${encodeURIComponent(bu)}` +
      `&start=${start}&end=${end}&top=${t}`
    )
  }
  return `/api/v1/daily?start=${start}&end=${end}&top=${t}`
}
